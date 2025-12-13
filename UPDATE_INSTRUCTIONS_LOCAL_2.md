# Update Instructions for Buffer Worker (Local 2)

Follow these steps exactly to update the worker, ensure it auto-restarts, and verify it works.

## 1. Stop and Delete Old Container
First, we must remove the running container. This will NOT delete your configuration/env file, only the running instance.

```bash
# Stop the container
docker stop buffer-orch-local-2

# Remove the container (important to free up the name)
docker rm buffer-orch-local-2
```

> **Note**: If the container name is different (e.g., `buffer-orch-gpu2` or just `worker`), use that name instead of `buffer-orch-local-2` in the commands above.

## 2. Pull the New Image
Get the latest version with the error reporting and download fixes.

```bash
docker pull explaindio/musetalk-queue-worker:progress
```

## 3. Start New Container (With Auto-Restart)
This command starts the worker in **production mode**. 
- It uses `--restart unless-stopped` so it comes back up after a reboot.
- It does **NOT** use `--rm`, so the container is not deleted when stopped.

Run this exact command (ensure you are in the directory with your `.env` file):

```bash
docker run --gpus all -d \
  --name buffer-orch-local-2 \
  --restart unless-stopped \
  --network bridge \
  --env-file .env \
  -e BUFFER_WORKER_ID=buffer-orch-local-2 \
  -e ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e BUFFER_ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  explaindio/musetalk-queue-worker:progress
```

**Check that it is running:**
```bash
docker ps
# You should see 'buffer-orch-local-2' in the list with STATUS 'Up X seconds'
```

## 4. Verification Test
Run this `curl` command to verify the worker is healthy and responding correctly to requests (it mimics a bad request to check the new error reporting).

**Find the port:** 
First, find which IP/port the container was assigned (since we used `network bridge`).
```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' buffer-orch-local-2
```
*Assume it returns `172.17.0.X` (e.g., `172.17.0.3`)*.

**Run the test:**
Replace `172.17.0.X` with the actual IP from above.

```bash
curl -X POST http://172.17.0.X:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"musetalk_job_id":"test-check","video_url":"http://httpstat.us/404","audio_url":"http://httpstat.us/404","aspect_ratio":"16:9","resolution":"720p"}'
```

**Expected Result:**
You should see a **JSON response** (not a crash, not a 500 html page) looking like this:
```json
{"status":"failed","error_type":"media_error","stage":"download", ...}
```

If you see this, the worker is **UPDATED** and **RUNNING CORRECTLY**.
