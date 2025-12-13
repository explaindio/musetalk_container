# MuseTalk Worker Documentation

## Overview
This worker runs the **MuseTalk** model (Avatar Talking Head generation). It is capable of acting as both a **Salad Cloud Worker** (ephemeral) and a **Local Buffer Worker** (persistent GPU).

## Architecture

### 1. Code Location
- **Source:** `worker_app/` (FastAPI application)
- **Entrypoint Script:** `run_worker.sh`
- **Dockerfile:** `Dockerfile.worker`

### 2. Docker Image
- **Tag:** `explaindio/musetalk-queue-worker:progress`
- **Base:** `nvidia/cuda:11.8.0-runtime-ubuntu22.04`
- **Python:** 3.10 (via venv)

### 3. Key Components
- **Salad Worker Binary:** `/usr/local/bin/salad-http-job-queue-worker`
  - Runs in background, polls Salad Queue (or Mock queue).
  - Forwards jobs to `localhost:8000/generate`.
- **FastAPI App (`worker_app.main:app`):**
  - Listens on port 8000.
  - Endpoint: `POST /generate`
  - Logic: Downloads -> MuseTalk Inference -> Uploads to B2.
- **Buffer Logic:**
  - If `BUFFER_WORKER_ID` is set, runs a background loop (`_buffer_worker_loop`) to poll orchestrator for "buffer" jobs directly, bypassing Salad Queue.

### 4. API & Integration
- **Orchestrator Endpoint Scope:** `/internal/jobs/...`
- **Progress Reporting:**
  - `POST {ORCHESTRATOR_BASE_URL}/internal/jobs/{id}/progress`
  - Payload: `{ "status": "running", "progress": 0.5 }`

### 5. Running Locally (Buffer Mode)
See `.agent/workflows/setup-buffer-worker.md` for setup.
Currently running on this machine as `buffer-orch-local-1` (Paused/Running).

### 6. Deployment to Salad
1.  Build: `docker build -f Dockerfile.worker -t explaindio/musetalk-queue-worker:progress .`
2.  Push: `docker push explaindio/musetalk-queue-worker:progress`
3.  Configure Salad Queue to pull this image.
