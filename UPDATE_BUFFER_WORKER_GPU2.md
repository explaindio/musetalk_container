# Update Buffer Worker on GPU Machine 2

**Date**: 2025-12-09  
**Task**: Replace old worker container with new image containing RemoteProtocolError fix  
**Target Machine**: GPU Machine 2 (buffer worker)

---

## What's New in This Update

The new worker image (`explaindio/musetalk-queue-worker:progress`) includes:
- ✅ **Fix for catbox.moe and similar CDN download failures**
- ✅ Immediate curl fallback for `RemoteProtocolError` (saves 5-8 seconds per problematic URL)
- ✅ Better logging for download issues

**Docker Image**:
- Image: `docker.io/explaindio/musetalk-queue-worker:progress`
- Digest: `sha256:f34d4a50f1953b053b35fb6e338d70587ba5a91164fe732ab43375b22f3705b8`
- Size: ~24GB

---

## Step-by-Step Instructions

### Step 1: Check Current Container

First, identify the running buffer worker container:

```bash
docker ps | grep buffer-orch-local
```

**Expected output**: You should see a container named something like `buffer-orch-local-2`

---

### Step 2: Stop and Remove Old Container

Stop and remove the existing buffer worker container:

```bash
# Replace 'buffer-orch-local-2' with your actual container name
docker stop buffer-orch-local-2
docker rm buffer-orch-local-2
```

**Verify removal**:
```bash
docker ps -a | grep buffer-orch-local-2
```
Should return nothing.

---

### Step 3: Pull New Docker Image

Pull the updated worker image from Docker Hub:

```bash
docker pull explaindio/musetalk-queue-worker:progress
```

**This will take a few minutes** (~24GB download).

**Verify the pull**:
```bash
docker images | grep musetalk-queue-worker
```

You should see `explaindio/musetalk-queue-worker:progress` with a recent timestamp.

---

### Step 4: Start New Container with Auto-Restart

Start the new buffer worker container with auto-restart enabled:

```bash
cd ~/musetalk  # Or wherever your .env file is located

docker run -d \
  --gpus all \
  --restart unless-stopped \
  --network host \
  --env-file .env \
  --name buffer-orch-local-2 \
  -e BUFFER_WORKER_ID=buffer-orch-local-2 \
  -e BUFFER_ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e GPU_CLASS_NAME=RTX-local-buffer \
  -e BUFFER_CAPACITY=1 \
  -e BUFFER_POLL_INTERVAL_SEC=5 \
  explaindio/musetalk-queue-worker:progress
```

**Key flags**:
- `-d`: Run in detached mode (background)
- `--restart unless-stopped`: Auto-restart on reboot or crash
- `--network host`: Use host networking for orchestrator communication
- `--env-file .env`: Load credentials from `.env` file

**Important**: Adjust `BUFFER_WORKER_ID` and container `--name` if your machine uses a different ID (e.g., `buffer-orch-local-3`).

---

### Step 5: Verify Container is Running

Check that the new container started successfully:

```bash
docker ps | grep buffer-orch-local-2
```

**Expected output**: Container should show as "Up" with status like "Up 10 seconds"

---

### Step 6: Check Logs

Verify the worker is functioning correctly:

```bash
docker logs --tail 50 buffer-orch-local-2
```

**Look for**:
- ✅ `buffer_worker_loop_starting` - Buffer worker loop started
- ✅ No repeated `buffer_worker_disabled_missing_config` errors
- ✅ No connection errors to orchestrator

**If you see the new fix in action**, you'll see:
```
"event": "download_httpx_protocol_error_fallback_to_curl"
```

---

### Step 7: Test Connectivity

Test that the worker can reach the orchestrator:

```bash
docker exec buffer-orch-local-2 curl -s https://api.avatargen.online/health
```

**Expected output**:
```json
{"status":"ok","salad_ok":true,...}
```

---

### Step 8: Verify Environment Variables

Double-check that all required environment variables are set correctly:

```bash
docker exec buffer-orch-local-2 env | grep -E 'ORCHESTRATOR_BASE_URL|BUFFER_WORKER_ID|INTERNAL_API_KEY' | head -5
```

**Expected**:
```
BUFFER_ORCHESTRATOR_BASE_URL=https://api.avatargen.online
ORCHESTRATOR_BASE_URL=https://api.avatargen.online
BUFFER_WORKER_ID=buffer-orch-local-2
INTERNAL_API_KEY=changeme-internal-key
```

---

## Verification Checklist

After completing all steps, verify:

- [ ] Old container stopped and removed
- [ ] New image pulled from Docker Hub
- [ ] New container running with `--restart unless-stopped`
- [ ] Container shows "Up" status in `docker ps`
- [ ] Logs show `buffer_worker_loop_starting`
- [ ] No connection errors in logs
- [ ] Orchestrator health endpoint returns 200 OK
- [ ] Environment variables are correct

---

## Troubleshooting

### Container Fails to Start

**Check logs**:
```bash
docker logs buffer-orch-local-2
```

**Common issues**:
- Missing `.env` file → Ensure you're in the directory with `.env`
- Wrong `INTERNAL_API_KEY` → Check it matches the orchestrator
- No GPU access → Verify `nvidia-docker` is installed

### Container Keeps Restarting

```bash
docker logs --tail 100 buffer-orch-local-2
```

Look for:
- Connection refused errors → Check `ORCHESTRATOR_BASE_URL`
- Authentication errors → Check `INTERNAL_API_KEY`
- Missing environment variables → Verify `.env` file

### Worker Not Appearing in Orchestrator

**Check heartbeats are being sent**:
```bash
docker logs --tail 20 buffer-orch-local-2 | grep heartbeat
```

If no heartbeat logs, check:
- `BUFFER_WORKER_ID` is set
- `BUFFER_ORCHESTRATOR_BASE_URL` or `ORCHESTRATOR_BASE_URL` is set
- `INTERNAL_API_KEY` matches orchestrator

---

## Rollback (If Needed)

If the new version has issues, you can rollback to the previous image:

```bash
# Stop new container
docker stop buffer-orch-local-2
docker rm buffer-orch-local-2

# Find previous image
docker images | grep musetalk-queue-worker

# Start with old image (use the IMAGE ID from above)
docker run -d \
  --gpus all \
  --restart unless-stopped \
  --network host \
  --env-file .env \
  --name buffer-orch-local-2 \
  -e BUFFER_WORKER_ID=buffer-orch-local-2 \
  -e BUFFER_ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e GPU_CLASS_NAME=RTX-local-buffer \
  -e BUFFER_CAPACITY=1 \
  -e BUFFER_POLL_INTERVAL_SEC=5 \
  <OLD_IMAGE_ID>
```

---

## Auto-Start Configuration

The container will now automatically:
- ✅ Start on system boot
- ✅ Restart if it crashes
- ✅ Stay running until manually stopped

**To disable auto-restart** (if needed):
```bash
docker update --restart no buffer-orch-local-2
```

**To re-enable auto-restart**:
```bash
docker update --restart unless-stopped buffer-orch-local-2
```

---

## Questions?

If you encounter any issues:

1. Check the troubleshooting section above
2. Review container logs: `docker logs --tail 100 buffer-orch-local-2`
3. Verify environment variables are correct
4. Test orchestrator connectivity

---

**Deployment Instructions Created**: 2025-12-09  
**New Image Digest**: `sha256:f34d4a50f1953b053b35fb6e338d70587ba5a91164fe732ab43375b22f3705b8`  
**Next Steps**: Follow steps 1-8 above to apply the update
