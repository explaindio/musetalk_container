# FastWan Worker Documentation

## Overview
This worker runs the **FastWan 2.2** model (I2V / Video Generation). It is optimized for **RTX 5090** (Blackwell) and runs primarily on **Salad Cloud**. It does NOT support local buffer mode (due to lack of 5090 HW).

## Architecture

### 1. Code Location
- **Source:** `worker_app_fastwan/` (FastAPI application)
- **Entrypoint Script:** `run_fastwan_worker.sh`
- **Dockerfile:** `Dockerfile.fastwan`

### 2. Docker Image
- **Tag:** `explaindio/fastwan-worker:v1`
- **Base:** `nvcr.io/nvidia/pytorch:24.10-py3` (PyTorch Nightly / cu128)
- **Model:** `FastVideo/FastWan2.2-TI2V-5B-Diffusers` (Cloned/installed at build time)

### 3. Key Components
- **Salad Worker Binary:** `/usr/local/bin/salad-http-job-queue-worker`
  - Runs in background, polls Salad Queue.
  - Forwards jobs to `localhost:8000/generate`.
- **FastAPI App (`worker_app_fastwan.main:app`):**
  - Listens on port 8000.
  - Endpoint: `POST /generate`
  - Logic: Downloads -> FastVideo Inference (1 Image -> Video) -> Uploads to B2.
  - **Defaults:** `num_frames=121`, `width=720`, `height=1280`.

### 4. API & Integration
- **Orchestrator Endpoint Scope:** `/internal/videogen/jobs/...` (NOT `/internal/jobs`)
- **Progress Reporting:**
  - `POST {ORCHESTRATOR_BASE_URL}/internal/videogen/jobs/{id}/progress`
  - Payload: `{ "status": "running", "phase": "inference", "progress": 0.2 }`

### 5. Deployment to Salad
1.  Build: `docker build -f Dockerfile.fastwan -t explaindio/fastwan-worker:v1 .`
2.  Push: `docker push explaindio/fastwan-worker:v1`
3.  Configure Salad Queue to pull this image.

See `FASTWAN_ORCHESTRATOR_DEV_GUIDE.md` for specific integration details.
