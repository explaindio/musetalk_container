# MuseTalk Docker Container & Worker System - Project Overview

This document provides a comprehensive reference for the MuseTalk avatar video generation system, its architecture, Docker workflow, and deployment processes.

---

## Table of Contents

1. [Project Architecture](#project-architecture)
2. [Key Components](#key-components)
3. [Docker Images & Build Process](#docker-images--build-process)
4. [Worker Application](#worker-application)
5. [Deployment Workflow](#deployment-workflow)
6. [Environment Configuration](#environment-configuration)
7. [Recent Fixes & Known Issues](#recent-fixes--known-issues)
8. [File Structure](#file-structure)

---

## Project Architecture

This project manages a **MuseTalk v1.5 AI model** for lip-sync avatar video generation with three main components:

1. **Worker Container** - GPU workers that process MuseTalk inference jobs
2. **Orchestrator** - Manages job queues, worker scaling, and job routing
3. **Buffer GPU Workers** - Local GPU machines that supplement cloud (Salad) workers

### High-Level Flow

```
Client → Orchestrator → Job Queue → Worker Container → MuseTalk Inference → B2 Storage → Client
                              ↓
                      Buffer GPU Workers (optional)
```

---

## Key Components

### 1. Docker Images

The project uses two main Docker images pushed to Docker Hub:

#### **Worker Image** (Primary)
- **Image**: `explaindio/musetalk-queue-worker:progress`
- **Size**: ~24.2GB
- **Purpose**: GPU workers that process MuseTalk jobs
- **Dockerfile**: `Dockerfile.worker`

#### **Benchmark Image**
- **Image**: `explaindio/musetalk-salad:bench`
- **Size**: ~24.2GB
- **Purpose**: GPU benchmarking and testing
- **Dockerfile**: `Dockerfile`

---

## Worker Application

### Location
- **Main code**: `worker_app/main.py` (905 lines)
- **Init file**: `worker_app/__init__.py`

### API Endpoints

#### `GET /hc`
Health check endpoint for Salad readiness/startup probes.

**Response:**
```json
{"status": "ok"}
```

#### `POST /generate`
Main endpoint that processes MuseTalk inference jobs.

**Request:**
```json
{
  "musetalk_job_id": "job-123",
  "video_url": "https://example.com/video.mp4",
  "audio_url": "https://example.com/audio.wav",
  "aspect_ratio": "9:16",
  "resolution": "720p",
  "params": {}
}
```

**Response:**
```json
{
  "status": "ok",
  "b2_bucket": "talking-avatar",
  "b2_file_name": "avatar/outputs/job-123.mp4",
  "metrics": {
    "GENERATION_TIME_SEC": 20.63,
    "SCRIPT_WALL_TIME_SEC": 141.62,
    "PEAK_VRAM_MIB": 917.3,
    "PEAK_RAM_KB": 5130911,
    "gpu_class": "RTX-3080"
  }
}
```

### Worker Functionality

1. **Input Processing**
   - Downloads video and audio from provided URLs
   - Validates media files with `ffprobe`
   - Retries on transient failures (up to 3 attempts)
   - Falls back to `curl` for protocol-level issues

2. **MuseTalk Inference**
   - Builds temporary YAML config
   - Runs `python -m scripts.inference` from MuseTalk repo
   - Uses `/usr/bin/time -v` to capture resource metrics
   - Streams stdout for progress updates

3. **Output Handling**
   - Uploads generated video to Backblaze B2
   - Writes JSON metadata sidecar file
   - Returns B2 bucket/file information

4. **Progress Reporting**
   - Sends periodic updates to orchestrator
   - Phases: `preparing` → `inferring` → `encoding` → `uploading` → `completed`
   - Progress mapped to 0.0 - 1.0 range

### Buffer Worker Mode

When `BUFFER_WORKER_ID` is set, the worker runs an additional background loop:

**Function**: `_buffer_worker_loop()`

**Behavior:**
- Sends heartbeats every 5-10 seconds to orchestrator
- Claims buffer jobs when idle
- Processes jobs via local `POST /generate` endpoint
- Reports job completion status

**Heartbeat Payload:**
```json
{
  "status": "idle" | "busy",
  "gpu_class": "RTX-local-buffer",
  "capacity": 1,
  "error": null
}
```

**Endpoint**: `POST {BUFFER_ORCHESTRATOR_BASE_URL}/internal/buffer/workers/{worker_id}/heartbeat`

---

## Docker Images & Build Process

### Building the Worker Image

```bash
# From project root
docker build -f Dockerfile.worker -t explaindio/musetalk-queue-worker:progress .
```

**Build steps:**
1. Base: `nvidia/cuda:11.8.0-runtime-ubuntu22.04`
2. Install system deps: `python3`, `ffmpeg`, `git`, `time`, `curl`
3. Copy MuseTalk code and worker app
4. Create Python venv at `/opt/venv`
5. Install PyTorch with CUDA 11.8 support
6. Install MMLab stack (mmcv, mmdet, mmpose)
7. Download Salad HTTP Job Queue Worker binary (v0.5.0)
8. Set entrypoint to `run_worker.sh`

### Building the Benchmark Image

```bash
# From project root
docker build -f Dockerfile -t explaindio/musetalk-salad:bench .
```

Similar to worker image but simpler (no Salad worker, no FastAPI app).

### Pushing to Docker Hub

```bash
# Login to Docker Hub
docker login

# Push worker image
docker push explaindio/musetalk-queue-worker:progress

# Push benchmark image
docker push explaindio/musetalk-salad:bench
```

---

## Deployment Workflow

### Standard Workflow After Code Changes

```bash
# 1. Edit worker code
vim worker_app/main.py

# 2. Rebuild worker image
docker build -f Dockerfile.worker -t explaindio/musetalk-queue-worker:progress .

# 3. Push to Docker Hub
docker push explaindio/musetalk-queue-worker:progress

# 4. Restart/redeploy workers
# For local buffer workers:
docker rm -f buffer-orch-local-1

docker run --gpus all --rm --network host \
  --env-file .env \
  --name buffer-orch-local-1 \
  -e BUFFER_WORKER_ID=buffer-orch-local-1 \
  -e BUFFER_ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
  -e GPU_CLASS_NAME=RTX-local-buffer \
  -e BUFFER_CAPACITY=1 \
  -e BUFFER_POLL_INTERVAL_SEC=5 \
  explaindio/musetalk-queue-worker:progress

# For Salad cloud workers, update container group to pull new image
```

### Worker Entrypoint (`run_worker.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Start the Salad HTTP Job Queue Worker in the background
/usr/local/bin/salad-http-job-queue-worker &
WORKER_PID=$!

# Start the FastAPI worker app (MuseTalk processor)
uvicorn worker_app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait for either process to exit
wait -n "$WORKER_PID" "$API_PID"

# Exit with the status of the first process that exited
exit $?
```

**Two processes:**
1. **Salad Job Queue Worker** - Receives jobs from Salad Job Queue API
2. **FastAPI app** - Processes MuseTalk inference via `/generate` endpoint

---

## Environment Configuration

### Required Environment Variables

#### Orchestrator Integration
- `ORCHESTRATOR_BASE_URL` - Orchestrator API endpoint (e.g., `https://api.avatargen.online`)
- `BUFFER_ORCHESTRATOR_BASE_URL` - Override for buffer workers (fallback to `ORCHESTRATOR_BASE_URL`)
- `INTERNAL_API_KEY` - Authentication header (`X-Internal-API-Key`)

#### Buffer Worker Mode (Optional)
- `BUFFER_WORKER_ID` - Enables buffer mode (e.g., `buffer-orch-local-1`)
- `GPU_CLASS_NAME` - GPU identifier for metrics (e.g., `RTX-local-buffer`)
- `BUFFER_CAPACITY` - Concurrent job capacity (default: `1`)
- `BUFFER_POLL_INTERVAL_SEC` - Heartbeat interval (default: `10`)

#### Backblaze B2 Storage
- `B2_KEY_ID` - B2 application key ID
- `B2_APP_KEY` - B2 application key
- `B2_BUCKET_NAME` - Target bucket (e.g., `talking-avatar`)
- `B2_PREFIX` - Path prefix within bucket (e.g., `avatar/outputs`)

#### MuseTalk Configuration
- `MUSETALK_WORKDIR` - Working directory (default: `/app`)
- `MUSETALK_RESULT_DIR` - Output directory (default: `results/job_queue`)
- `MUSETALK_UNET_MODEL_PATH` - Model path (default: `models/musetalkV15/unet.pth`)
- `MUSETALK_UNET_CONFIG` - Config path (default: `models/musetalkV15/musetalk.json`)

#### Salad Integration (for cloud workers)
- `SALAD_QUEUE_JOB_ID` - Set by Salad Job Queue Worker
- `SALAD_API_KEY` - Salad cloud API key
- `SALAD_ORG_NAME` - Organization name (e.g., `explaindiolls`)
- `SALAD_PROJECT_NAME` - Project name (e.g., `project2`)

### Example `.env` File

```bash
# Orchestrator
ORCHESTRATOR_BASE_URL=https://api.avatargen.online
INTERNAL_API_KEY=changeme-internal-key

# Salad
SALAD_API_KEY=salad_cloud_user_XXX...
SALAD_ORG_NAME=explaindiolls
SALAD_PROJECT_NAME=project2

# B2 Storage
B2_KEY_ID=00580d90663733b000000000c
B2_APP_KEY=K005jgPrn8riZCmk5RUYhIzdlj+s0xI
B2_BUCKET_NAME=talking-avatar
B2_PREFIX=avatar/outputs
```

---

## Recent Fixes & Known Issues

### Buffer Worker Heartbeat Fix (Dec 2025)

**Documented in**: `BUFFER_GPU_HEARTBEAT_FIX.md`

#### Problem
- Buffer worker heartbeats were silently failing
- Worker container continued running but orchestrator marked it as offline
- Root cause: `httpx` response not checked for HTTP errors

#### Solution
Added in `worker_app/main.py`:

```python
# Inside _buffer_worker_loop()
hb_resp = await client.post(
    f"{base_url.rstrip('/')}/internal/buffer/workers/{worker_id}/heartbeat",
    json=hb_body,
    headers=headers,
)
hb_resp.raise_for_status()  # ← CRITICAL: Fail fast on HTTP errors
```

Also added startup logging:
```python
@app.on_event("startup")
async def _start_buffer_worker_loop() -> None:
    worker_id = os.environ.get("BUFFER_WORKER_ID")
    if worker_id:
        logger.info(
            "buffer_worker_loop_starting",
            extra={"BUFFER_WORKER_ID": worker_id},
        )
        asyncio.create_task(_buffer_worker_loop())
```

#### Verification
Check orchestrator database:
```sql
SELECT worker_id, last_heartbeat, status
FROM buffer_workers
ORDER BY last_heartbeat DESC;
```

Expect `last_heartbeat` to update every 5-10 seconds.

---

## File Structure

```
/home/a/musetalk/
├── Dockerfile                          # Benchmark image
├── Dockerfile.worker                  # Worker image (GPU processing)
├── run_worker.sh                      # Entrypoint script for worker
├── README.md                          # High-level architecture docs
├── BUFFER_GPU_HEARTBEAT_FIX.md       # Recent fix documentation
├── PROJECT_OVERVIEW.md                # This file
│
├── worker_app/                        # Worker application
│   ├── __init__.py
│   └── main.py                        # FastAPI worker (905 lines)
│
├── MuseTalk/                          # Core ML model code (gitignored)
│   ├── app.py
│   ├── requirements.txt
│   ├── scripts/
│   │   └── inference.py               # Main inference script
│   └── models/                        # Model weights
│
├── salad_management_archive/          # Orchestrator (gitignored)
│   └── orchestrator/
│       ├── main.py                    # Orchestrator FastAPI app
│       ├── config.py                  # Configuration
│       ├── salad_client.py           # Salad API client
│       ├── scaling.py                # Auto-scaling logic
│       ├── storage.py                # SQLite database
│       └── b2_utils.py               # B2 utilities
│
├── .agent/workflows/
│   └── setup-buffer-worker.md        # Buffer worker setup guide
│
├── .env                               # Environment config (gitignored)
├── .gitignore
└── gpu_targets.json                   # GPU benchmark targets
```

---

## Common Commands Reference

### Build & Push
```bash
# Build worker
docker build -f Dockerfile.worker -t explaindio/musetalk-queue-worker:progress .

# Build benchmark
docker build -f Dockerfile -t explaindio/musetalk-salad:bench .

# Push to Docker Hub
docker push explaindio/musetalk-queue-worker:progress
docker push explaindio/musetalk-salad:bench
```

### Local Testing
```bash
# Run worker locally (buffer mode)
docker run --gpus all --rm --network host \
  --env-file .env \
  --name test-worker \
  -e BUFFER_WORKER_ID=test-local-1 \
  -e ORCHESTRATOR_BASE_URL=http://localhost:8080 \
  explaindio/musetalk-queue-worker:progress

# Check logs
docker logs -f test-worker

# Test health endpoint
curl http://localhost:8000/hc
```

### Debugging
```bash
# Check running containers
docker ps | grep musetalk

# View worker logs
docker logs --tail 100 buffer-orch-local-1

# Exec into container
docker exec -it buffer-orch-local-1 bash

# Check environment
docker exec buffer-orch-local-1 env | grep -E 'ORCHESTRATOR|BUFFER'

# Test connectivity from container
docker exec buffer-orch-local-1 curl -s https://api.avatargen.online/health
```

---

## Next Steps for Development

When updating worker code:

1. **Edit** `worker_app/main.py` or related files
2. **Test locally** with a test container
3. **Rebuild** the Docker image
4. **Push** to Docker Hub
5. **Update** cloud workers (Salad container groups)
6. **Restart** local buffer workers
7. **Verify** in orchestrator logs/database
8. **Document** significant changes in this file or dedicated MD files

---

**Last Updated**: 2025-12-09  
**Maintainer**: AI Assistant (Antigravity)
