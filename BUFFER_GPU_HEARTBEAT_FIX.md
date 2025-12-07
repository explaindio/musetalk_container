## Buffer GPU heartbeat fix for local machine 2

This note is for the next assistant running on **local buffer GPU machine 2**. It explains what was wrong with the buffer worker heartbeats and exactly how to apply the same fix that was done here on machine 1.

The goal: make sure the local buffer worker container (`buffer-orch-local-*`) sends a heartbeat to the VPS orchestrator every few seconds so the orchestrator always sees it as **online** and can route jobs to it.

---

### 1. What was broken

- The buffer worker loop lives in `worker_app/main.py`, function `_buffer_worker_loop`.
- It was using an `httpx.AsyncClient` to post heartbeats to:
  - `POST {BUFFER_ORCHESTRATOR_BASE_URL}/internal/buffer/workers/{worker_id}/heartbeat`
- But it **never called `raise_for_status()`** on the heartbeat response and didn’t log anything about heartbeats.
- Result: if the orchestrator ever returned 4xx/5xx (bad key, wrong URL, etc.), the loop would quietly keep running, but the orchestrator would stop updating `last_heartbeat`. From the orchestrator’s DB it looked like the worker went offline, even though the container kept running.

On machine 1, we fixed this by:

1. Making the heartbeat call **fail fast** on any non‑200 status.
2. Adding a startup log so we can see when the buffer loop actually starts.
3. Rebuilding the worker image and restarting the buffer container with correct env.

You should repeat those exact steps on local machine 2.

---

### 2. Code changes to `_buffer_worker_loop`

File: `worker_app/main.py`

#### 2.1. Enforce success on heartbeats

Inside `_buffer_worker_loop`, the heartbeat section must look like this (key line is `hb_resp.raise_for_status()`):

```python
    headers = {"X-Internal-API-Key": internal_key}

    async with httpx.AsyncClient(timeout=10.0) as client:
        status = "idle"
        last_error: Optional[str] = None
        while True:
            try:
                # Heartbeat
                hb_body: Dict[str, Any] = {
                    "status": status,
                    "gpu_class": gpu_class,
                    "capacity": capacity,
                    "error": last_error,
                }
                hb_resp = await client.post(
                    f"{base_url.rstrip('/')}/internal/buffer/workers/{worker_id}/heartbeat",
                    json=hb_body,
                    headers=headers,
                )
                hb_resp.raise_for_status()

                if status == "idle":
                    # Try to claim a job
                    ...
```

If your copy is still using `await client.post(...)` without assigning to `hb_resp` and without `hb_resp.raise_for_status()`, update it to match the snippet above.

#### 2.2. Log when the buffer loop starts

At the bottom of the file, the FastAPI startup hook must log when the buffer loop is enabled:

```python
@app.on_event("startup")
async def _start_buffer_worker_loop() -> None:
    """
    Optionally start the buffer worker loop when configured.

    This is enabled only when BUFFER_WORKER_ID is set, so Salad queue
    workers are unaffected.
    """

    worker_id = os.environ.get("BUFFER_WORKER_ID")
    if worker_id:
        logger.info(
            "buffer_worker_loop_starting",
            extra={"BUFFER_WORKER_ID": worker_id},
        )
        asyncio.create_task(_buffer_worker_loop())
```

If you still have the older version that just did:

```python
    if os.environ.get("BUFFER_WORKER_ID"):
        asyncio.create_task(_buffer_worker_loop())
```

replace it with the new version above so you can see a clear `buffer_worker_loop_starting` line in the container logs.

---

### 3. Rebuild the worker image

From the repo root on local machine 2 (same level as `Dockerfile.worker`):

```bash
docker build -f Dockerfile.worker -t explaindio/musetalk-queue-worker:progress .
```

This bakes the updated `worker_app/main.py` into the `explaindio/musetalk-queue-worker:progress` image.

---

### 4. Restart the buffer worker container

Stop any existing buffer container:

```bash
docker rm -f buffer-orch-local-1 || true
```

Start the new container with **host networking** and the same environment pattern we use on machine 1 (adjust the worker ID if needed, e.g. `buffer-orch-local-2`):

```bash
nohup docker run --gpus all --rm --network host --env-file .env \
  --name buffer-orch-local-2 \
  -e BUFFER_WORKER_ID=buffer-orch-local-2 \
  -e BUFFER_ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e GPU_CLASS_NAME=RTX-local-buffer \
  -e BUFFER_CAPACITY=1 \
  -e BUFFER_POLL_INTERVAL_SEC=5 \
  explaindio/musetalk-queue-worker:progress \
  > buffer_worker.log 2>&1 & echo $! > buffer_worker.pid
```

Requirements:

- `.env` on local machine 2 must include at least:
  - `INTERNAL_API_KEY` — must match the VPS orchestrator `.env`.
  - `B2_KEY_ID`, `B2_APP_KEY`, `B2_BUCKET_NAME`, `B2_PREFIX` — so the worker can upload outputs.
- `BUFFER_ORCHESTRATOR_BASE_URL` and `ORCHESTRATOR_BASE_URL` **must** both be `https://api.avatargen.online` (public VPS endpoint), not `localhost`.

After starting, confirm the container is up:

```bash
docker ps --format '{{.Names}} {{.Status}}' | grep buffer-orch-local-2
```

---

### 5. Verify heartbeats and logs

#### 5.1. Inside the container

Check that the buffer loop actually started and there are no loop errors:

```bash
docker logs --tail 100 buffer-orch-local-2 | grep -i 'buffer_worker' || echo 'NO_BUFFER_LOGS'
```

You want to see **at least**:

- `buffer_worker_loop_starting` once on startup.
- **No** `buffer_worker_disabled_missing_config`.
- **No** `buffer_worker_loop_error`.

If you need to test connectivity manually from inside the container:

```bash
docker exec buffer-orch-local-2 python -c "import os,httpx; base=os.environ.get('BUFFER_ORCHESTRATOR_BASE_URL') or os.environ.get('ORCHESTRATOR_BASE_URL'); key=os.environ.get('INTERNAL_API_KEY'); wid=os.environ.get('BUFFER_WORKER_ID'); r=httpx.post(base.rstrip('/') + f'/internal/buffer/workers/{wid}/heartbeat', json={'status':'idle','gpu_class':os.environ.get('GPU_CLASS_NAME'),'capacity':1,'error':None}, headers={'X-Internal-API-Key':key}, timeout=10.0); print('STATUS', r.status_code); print('BODY', r.text[:200])"
```

You should get `STATUS 200` and `{"detail":"ok"}`.

#### 5.2. On the VPS orchestrator

From the orchestrator machine (already set up on VPS), you can confirm that heartbeats are flowing by querying the `buffer_workers` table, e.g.:

```sql
SELECT worker_id, last_heartbeat, status
FROM buffer_workers
ORDER BY last_heartbeat DESC;
```

For a healthy buffer worker you should see:

- `worker_id = 'buffer-orch-local-2'` (or whatever ID you set).
- `last_heartbeat` updating every few seconds (within ~60s of the current UTC time).

If `last_heartbeat` is stuck or lags by many minutes **and** you see `buffer_worker_loop_error` in the container logs on local machine 2, then the orchestrator is returning an error for heartbeats (wrong key, wrong URL, etc.). Fix the env or orchestrator config, restart the container, and re‑check.

---

### 6. Summary

- The original issue was **silent heartbeat failure**: the worker kept running, but heartbeats were not being recorded, so the orchestrator considered the buffer GPU offline.
- The fix is:
  1. Enforce `hb_resp.raise_for_status()` on the heartbeat POST.
  2. Log when `_buffer_worker_loop` starts so you know it is actually running.
  3. Rebuild `explaindio/musetalk-queue-worker:progress` and restart the buffer container with correct env (public orchestrator URL + matching `INTERNAL_API_KEY`).
- Once this is in place on local machine 2, you should see continuous heartbeats in the VPS DB and the orchestrator will safely treat that machine as an online buffer GPU worker.

