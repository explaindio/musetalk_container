# FastWan Worker Documentation

## Overview
This worker runs the **FastWan 2.2** model (I2V / Video Generation). It supports:
- **Queue Mode (Salad):** Ephemeral cloud workers
- **Buffer Mode (Vast.ai/Local):** Persistent workers polling orchestrator

## Architecture

### 1. Code Location
- **Source:** `worker_app_fastwan/` (FastAPI application)
- **Entrypoint Script:** `run_fastwan_worker.sh`
- **Dockerfile:** `Dockerfile.fastwan`

### 2. Docker Image
- **Tag:** `explaindio/fastwan-worker:v1`
- **Base:** `nvcr.io/nvidia/pytorch:24.10-py3` + PyTorch Nightly cu128
- **Model:** `FastVideo/FastWan2.2-TI2V-5B-Diffusers`

### 3. Worker Modes

#### Queue Mode (Default - Salad)
Set `WORKER_MODE=queue` (or leave unset)

| Component | Description |
|-----------|-------------|
| Salad Binary | Polls Salad queue, forwards to localhost:8000 |
| FastAPI | Listens on :8000, handles `/generate` requests |
| Progress | Reports to `/internal/videogen/jobs/{id}/progress` |

#### Buffer Mode (Vast.ai / Local)
Set `WORKER_MODE=buffer`

| Component | Description |
|-----------|-------------|
| Job Claim | Polls `POST /internal/buffer/jobs/claim` |
| Heartbeat | Sends `POST /internal/buffer/workers/{id}/heartbeat` every 5s |
| Completion | Reports `POST /internal/buffer/jobs/{id}/status` |

### 4. Environment Variables

#### Common (Both Modes)
```bash
ORCHESTRATOR_BASE_URL=https://api.avatargen.online
INTERNAL_API_KEY=<key>
B2_KEY_ID=<key>
B2_APP_KEY=<key>
B2_BUCKET_NAME=talking-avatar
```

#### Buffer Mode Only
```bash
WORKER_MODE=buffer
BUFFER_WORKER_ID=vast-<instance_id>  # Unique worker ID
GPU_CLASS=RTX 3080                    # GPU type for orchestrator
```

### 5. API Endpoints (Queue Mode)
- `GET /health` - Health check
- `POST /generate` - Generate video from image+prompt

### 6. Deployment

#### Salad (Queue Mode)
1. Build: `docker build -f Dockerfile.fastwan -t explaindio/fastwan-worker:v1 .`
2. Push: `docker push explaindio/fastwan-worker:v1`
3. Configure Salad to pull this image (no special env vars needed)

#### Vast.ai (Buffer Mode)
1. Launch instance with GPU
2. Pull image: `docker pull explaindio/fastwan-worker:v1`
3. Run with buffer env vars:
```bash
docker run --gpus all \
  -e WORKER_MODE=buffer \
  -e BUFFER_WORKER_ID=vast-12345 \
  -e GPU_CLASS="RTX 3080" \
  -e ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e INTERNAL_API_KEY=<key> \
  -e B2_KEY_ID=<key> \
  -e B2_APP_KEY=<key> \
  -e B2_BUCKET_NAME=talking-avatar \
  explaindio/fastwan-worker:v1
```
