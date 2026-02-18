# 🚀 Deploy `unified-v5-optimized` — Upgrade Instructions

**Date:** February 18, 2026
**New Image:** `explaindio/musetalk-worker:unified-v5-optimized`
**Previous Image:** `explaindio/musetalk-worker:unified-v1`

---

## What Changed

- **Pipe-based FFmpeg encoding** — frames are piped directly to FFmpeg instead of writing to disk, then muxing. ~11% faster end-to-end inference.
- **`inference_optimized.py`** — new optimized inference script, selected via `USE_OPTIMIZED_INFERENCE=true`.
- Worker code is backward-compatible: setting `USE_OPTIMIZED_INFERENCE=false` (or omitting it) uses the original `inference.py`.

---

## 1. Salad — Update Container Groups

For **each** Salad container group running MuseTalk workers:

1. Go to **Salad Portal** → **Container Groups** → select your group.
2. Click **Edit** → **Container Image**.
3. Change the image tag:
   ```
   explaindio/musetalk-worker:unified-v5-optimized
   ```
4. **Add** this new environment variable:
   | Variable | Value |
   |----------|-------|
   | `USE_OPTIMIZED_INFERENCE` | `true` |

5. Keep all other existing env vars unchanged (`ORCHESTRATOR_BASE_URL`, `INTERNAL_API_KEY`, `B2_*`, etc.).
6. Click **Save** → **Redeploy**.

> [!IMPORTANT]
> Salad will do a rolling restart. Existing workers will finish their current job before pulling the new image. Allow 5–10 minutes for all replicas to cycle.

### Full Env Var Reference

| Variable | Value | Notes |
|----------|-------|-------|
| `ORCHESTRATOR_BASE_URL` | `https://orch.avatargen.online` | No change |
| `INTERNAL_API_KEY` | *(your key)* | No change |
| `WORKER_TYPE` | `main` | No change |
| `PROVIDER` | `salad` | No change |
| `GPU_CLASS_NAME` | *(match GPU, e.g. `RTX_3060`)* | No change |
| `B2_KEY_ID` | *(your key)* | No change |
| `B2_APP_KEY` | *(your key)* | No change |
| `B2_BUCKET_NAME` | `talking-avatar` | No change |
| `POLL_INTERVAL_SEC` | `5` | No change |
| `BATCH_SIZE` | `8` (or `16` for 3090/4090) | No change |
| **`USE_OPTIMIZED_INFERENCE`** | **`true`** | **NEW — enables optimized pipeline** |

---

## 2. Vast.ai — Update Launch Command

Replace `unified-v1` with `unified-v5-optimized` and add the new env var:

```bash
docker run -d --gpus all --rm --network host --shm-size=8g \
  --name musetalk-worker \
  -e WORKER_ID=vast-${VAST_CONTAINERLABEL} \
  -e WORKER_TYPE=transient \
  -e PROVIDER=vast \
  -e GPU_CLASS_NAME=RTX_4090 \
  -e ORCHESTRATOR_BASE_URL=https://orch.avatargen.online \
  -e INTERNAL_API_KEY=YOUR_KEY_HERE \
  -e B2_KEY_ID=YOUR_KEY_ID \
  -e B2_APP_KEY=YOUR_APP_KEY \
  -e B2_BUCKET_NAME=talking-avatar \
  -e POLL_INTERVAL_SEC=5 \
  -e USE_OPTIMIZED_INFERENCE=true \
  explaindio/musetalk-worker:unified-v5-optimized
```

---

## 3. Local Buffer Worker

Already updated and running:

```
buffer-local-unified-1  →  unified-v5-optimized  →  USE_OPTIMIZED_INFERENCE=true  ✅
```

If you ever need to recreate it, update `restore_buffer_worker.sh` to use the new image tag and add the env var.

---

## 4. Verification

After redeploying, confirm workers are online:

```bash
# Check orchestrator health
curl -s https://orch.avatargen.online/health

# Check specific worker heartbeats in orchestrator logs/DB
# Workers should show status: "idle" and be heartbeating every 10s
```

In the worker container logs, you should see:
```
[heartbeat] Sent successfully. HTTP 200
```

And when a job runs, you should see the optimized inference being used:
```
DEBUG: Executing Inference Command: ['python', '-m', 'scripts.inference_optimized', ...]
```

---

## 5. Rollback

If needed, revert to the previous image:
```
explaindio/musetalk-worker:unified-v1
```
Remove or set `USE_OPTIMIZED_INFERENCE=false`. No other changes required.
