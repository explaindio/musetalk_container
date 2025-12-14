# MuseTalk Worker Documentation

## Overview
This worker runs the **MuseTalk** model (Avatar Talking Head generation). It supports:
- **Queue Mode (Salad):** Ephemeral cloud workers
- **Buffer Mode (Vast.ai/Local):** Persistent workers polling orchestrator

## Architecture

### 1. Code Location
- **Source:** `worker_app/` (FastAPI application)
- **Entrypoint Script:** `run_worker.sh`
- **Dockerfile:** `Dockerfile.worker`

### 2. Docker Image
- **Tag:** `explaindio/musetalk-queue-worker:progress`
- **Base:** `nvidia/cuda:11.8.0-runtime-ubuntu22.04`
- **Python:** 3.10 (via venv)

### 3. Worker Modes

#### Queue Mode (Default - Salad)
Leave `WORKER_MODE` unset or set to `queue`. Don't set `BUFFER_WORKER_ID`.

| Component | Description |
|-----------|-------------|
| Salad Binary | Polls Salad queue, forwards to localhost:8000 |
| FastAPI | Listens on :8000, handles `/generate` requests |
| Progress | Reports to `/internal/jobs/{id}/progress` |

#### Buffer Mode (Vast.ai / Local)
Set `WORKER_MODE=buffer` OR set `BUFFER_WORKER_ID`.

| Component | Description |
|-----------|-------------|
| FastAPI | Runs on :8000 |
| Background Task | Heartbeat + job claim loop |
| Job Claim | `POST /internal/buffer/jobs/claim` |
| Heartbeat | `POST /internal/buffer/workers/{id}/heartbeat` every 10s |
| Completion | `POST /internal/buffer/jobs/{id}/status` |

### 4. Environment Variables

#### Common (Both Modes)
```bash
ORCHESTRATOR_BASE_URL=https://api.avatargen.online
INTERNAL_API_KEY=<key>
B2_KEY_ID=<key>
B2_APP_KEY=<key>
B2_BUCKET_NAME=talking-avatar
```

#### Buffer Mode
```bash
# Option 1: New pattern (Vast.ai)
WORKER_MODE=buffer
GPU_CLASS=RTX 3080

# Option 2: Legacy pattern (Local buffers)
BUFFER_WORKER_ID=buffer-local-1
GPU_CLASS_NAME=RTX 3090 (24 GB)

# Both GPU_CLASS and GPU_CLASS_NAME are supported
```

### 5. API Endpoints
- `GET /hc` - Health check
- `POST /generate` - Generate talking head video

### 6. Deployment

#### Salad (Queue Mode)
1. Build: `docker build -f Dockerfile.worker -t explaindio/musetalk-queue-worker:progress .`
2. Push: `docker push explaindio/musetalk-queue-worker:progress`
3. Configure Salad to pull this image

#### Vast.ai (Buffer Mode)
```bash
docker run --gpus all \
  -e WORKER_MODE=buffer \
  -e GPU_CLASS="RTX 3080" \
  -e ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e INTERNAL_API_KEY=<key> \
  -e B2_KEY_ID=<key> \
  -e B2_APP_KEY=<key> \
  -e B2_BUCKET_NAME=talking-avatar \
  explaindio/musetalk-queue-worker:progress
```

#### Local Buffer (Legacy)
```bash
docker run --gpus all \
  -e BUFFER_WORKER_ID=buffer-local-1 \
  -e GPU_CLASS_NAME="RTX 3090 (24 GB)" \
  -e ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e INTERNAL_API_KEY=<key> \
  -e B2_KEY_ID=<key> \
  -e B2_APP_KEY=<key> \
  -e B2_BUCKET_NAME=talking-avatar \
  explaindio/musetalk-queue-worker:progress
```
