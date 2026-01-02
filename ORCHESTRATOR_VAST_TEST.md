# Orchestrator Instructions: Test Vast.ai Worker Image

## New Docker Image Available
`explaindio/musetalk-worker:vast-v1`

This image uses a "Push" architecture for Vast.ai and similar providers where the container must actively contact the orchestrator.

---

## Test Instructions

### 1. Provision a Vast.ai Instance
- **Image**: `explaindio/musetalk-worker:vast-v1`
- **GPU**: Any CUDA-capable GPU (RTX 3090, 4090, etc.)
- **Disk**: 100GB minimum

### 2. Required Environment Variables
```
ORCHESTRATOR_BASE_URL=https://orch.avatargen.online
INTERNAL_API_KEY=<your-api-key>
GPU_CLASS=<e.g., RTX_4090>
```

### 3. Expected Behavior
The container should:
1. Start uvicorn on `127.0.0.1:8000` (internal only)
2. Log `[Supervisor] Starting MuseTalk API...`
3. Begin sending heartbeats to `/internal/buffer/workers/{worker_id}/heartbeat`
4. Poll for jobs at `/internal/buffer/jobs/claim`

### 4. Verification Steps
- [ ] Check orchestrator logs for heartbeat from this worker
- [ ] Submit a test job via orchestrator
- [ ] Verify worker claims and processes the job
- [ ] Confirm job completion in orchestrator database

### 5. Troubleshooting
- If no heartbeats: Check `INTERNAL_API_KEY` and `ORCHESTRATOR_BASE_URL`
- If job not claimed: Ensure there are queued buffer jobs
- If processing fails: Check worker logs for uvicorn errors
