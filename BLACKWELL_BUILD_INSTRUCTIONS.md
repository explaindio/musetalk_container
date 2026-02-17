# Building a Blackwell-Compatible MuseTalk Worker Container

## Problem

The current `explaindio/musetalk-worker:unified-v4` image uses **CUDA 11.8 + PyTorch 2.0.1**, which only supports GPU architectures up to **sm_90** (Ada Lovelace / RTX 40xx). The RTX 5060 Ti (Blackwell, **sm_120**) fails with:

```
NVIDIA GeForce RTX 5060 Ti with CUDA capability sm_120 is not compatible
with the current PyTorch installation.
RuntimeError: CUDA error: no kernel image is available for execution on the device
```

## Goal

Create a **separate** Docker image (e.g., `explaindio/musetalk-worker:unified-v4-blackwell`) that runs on RTX 50xx GPUs. **Do NOT modify the existing working image.**

## Architecture

The current working image supports: RTX 2070, 2080, 3060 Ti, 3090, 4090 (sm_75 → sm_89).
The new Blackwell image will support: RTX 5060 Ti, 5070, 5080, 5090 (sm_120).

> [!IMPORTANT]
> Both images use **identical worker code** (`main.py`, `unified_worker.py`, `inference.py`). Only the CUDA/PyTorch base layer changes.

---

## Current Stack vs Required Stack

| Component | Current (unified-v4) | Required (Blackwell) |
|:---|:---|:---|
| CUDA base | `nvidia/cuda:11.8.0-runtime-ubuntu22.04` | `nvidia/cuda:12.8.0-runtime-ubuntu22.04` |
| PyTorch | `torch==2.0.1+cu118` | `torch==2.7.0+cu128` |
| torchvision | `0.15.2+cu118` | `0.22.0+cu128` |
| torchaudio | `2.0.2+cu118` | `2.7.0+cu128` |
| mmcv | `2.0.1` (pre-built) | Latest compatible (may need source build) |
| mmdet | `3.1.0` | `3.1.0` or latest compatible |
| mmpose | `1.1.0` | `1.1.0` or latest compatible |
| GPU archs | sm_37 → sm_90 | sm_50 → sm_120 |

---

## Prerequisites

### System Requirements (brand new computer)

1. **Docker** — install from https://docs.docker.com/engine/install/
2. **NVIDIA drivers** — version 570+ recommended for CUDA 12.8 compatibility
3. **NVIDIA Container Toolkit** — needed for `--gpus all` in Docker:
   ```bash
   # Ubuntu/Debian:
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```
4. **Docker Hub access** — login before pushing:
   ```bash
   docker login -u explaindio
   # Enter the Docker Hub Personal Access Token when prompted
   ```

> [!NOTE]
> A Blackwell GPU is **NOT required** to build the image. You can build on any machine with Docker. A Blackwell GPU is only needed for local testing (Step 4).

### Step 0: Clone the repo

```bash
git clone https://github.com/explaindio/musetalk_container.git
cd musetalk_container
```

This repo contains everything needed:

```
musetalk_container/               ← Build context
├── MuseTalk/                     ← MuseTalk source code + model configs
│   ├── requirements.txt          ← Python dependencies
│   ├── scripts/inference.py      ← Inference script (our fixed version)
│   ├── download_weights.sh       ← Downloads ~15GB of model weights during build
│   └── musetalk/                 ← Core MuseTalk Python package
├── worker_app/                   ← FastAPI worker application
│   ├── __init__.py
│   └── main.py                   ← /generate, /health endpoints + buffer worker
├── unified_worker.py             ← Polling loop (heartbeat + job claiming)
├── run_worker.sh                 ← Worker startup script
├── Dockerfile.unified            ← Current working Dockerfile (DO NOT MODIFY)
└── Dockerfile.blackwell          ← NEW — create this in Step 1
```

---

## Step-by-Step Build Instructions

### Step 1: Create `Dockerfile.blackwell`

Create this file in the repo root (`/home/code10/musetalk/Dockerfile.blackwell`). **Do not modify any existing Dockerfiles.**

```dockerfile
# ==============================================================================
# MuseTalk Blackwell Worker (RTX 50xx support)
# ==============================================================================
# Identical to Dockerfile.unified but with CUDA 12.8 + PyTorch 2.7
# for Blackwell architecture (sm_120) support.
# ==============================================================================

FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04

# 1. System Dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3-dev \
    git \
    ffmpeg \
    wget \
    curl \
    time \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# 2. Copy MuseTalk source and requirements
COPY MuseTalk/requirements.txt /app/requirements.txt

# 3. Install PyTorch 2.7 with CUDA 12.8 (Blackwell support)
RUN pip install --upgrade pip && \
    pip install torch==2.7.0+cu128 torchvision==0.22.0+cu128 torchaudio==2.7.0+cu128 \
    --index-url https://download.pytorch.org/whl/cu128

# 4. Install Python dependencies from requirements.txt
#    NOTE: tensorflow may conflict — install CPU-only version or skip if not needed
RUN pip install --no-cache-dir -r requirements.txt

# 5. Install MMLab stack
#    mmcv may not have pre-built wheels for PyTorch 2.7+cu128 yet.
#    Try pre-built first, fall back to source build if needed.
RUN pip install --no-cache-dir -U openmim && \
    mim install mmengine && \
    mim install "mmcv>=2.0.1" && \
    mim install "mmdet>=3.1.0" && \
    pip install --no-build-isolation chumpy==0.70 && \
    mim install "mmpose>=1.1.0"

# 6. Copy MuseTalk source code
COPY MuseTalk/ /app/

# 7. Download model weights
#    IMPORTANT: download_weights.sh sets HF_ENDPOINT=https://hf-mirror.com (Chinese mirror)
#    Override it to use the real HuggingFace endpoint for non-China builds.
RUN chmod +x /app/download_weights.sh && \
    HF_ENDPOINT=https://huggingface.co /app/download_weights.sh

# 8. Copy worker application code
COPY worker_app /app/worker_app/
COPY unified_worker.py /app/unified_worker.py
COPY run_worker.sh /app/run_worker.sh
RUN chmod +x /app/unified_worker.py /app/run_worker.sh

# 9. Copy fixed inference script
COPY MuseTalk/scripts/inference.py /app/scripts/inference.py

# 10. Create startup script (identical to unified-v4)
COPY <<EOF /app/start_unified.sh
#!/bin/bash
set -e

echo "Starting MuseTalk Unified Polling Worker (Blackwell)..."
echo "Worker ID: \${SALAD_MACHINE_ID:-\${VAST_CONTAINERLABEL:-\${WORKER_ID:-unknown}}}"
echo "Provider: \${PROVIDER:-unknown}"
echo "GPU Class: \${GPU_CLASS_NAME:-unknown}"
echo "Orchestrator: \${ORCHESTRATOR_BASE_URL:-https://orch.avatargen.online}"

# Start uvicorn in background
uvicorn worker_app.main:app --host 0.0.0.0 --port 8000 &
UVICORN_PID=\$!

# Wait for uvicorn to be ready
echo "Waiting for uvicorn to start..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "Uvicorn ready!"
        break
    fi
    sleep 1
done

# Start unified worker polling loop
python3 /app/unified_worker.py

kill \$UVICORN_PID 2>/dev/null || true
EOF

RUN chmod +x /app/start_unified.sh

ENV PYTHONPATH=/app
ENTRYPOINT ["/bin/bash", "/app/start_unified.sh"]
```

### Step 2: Build the Image

```bash
cd musetalk_container

docker build -f Dockerfile.blackwell \
  -t explaindio/musetalk-worker:unified-v4-blackwell .
```

> [!WARNING]
> This build downloads ~15GB of model weights and will take 30-60 minutes.

### Step 3: Troubleshooting — Common Build Issues

#### Issue 1: mmcv fails to install (no pre-built wheel)

If `mim install "mmcv>=2.0.1"` fails because there's no pre-built wheel for PyTorch 2.7 + CUDA 12.8:

```dockerfile
# Replace the mim install line with a source build:
RUN pip install --no-cache-dir -U openmim && \
    mim install mmengine && \
    pip install mmcv==2.2.0 -f https://download.openmmlab.com/mmcv/dist/cu128/torch2.7.0/index.html && \
    mim install "mmdet>=3.1.0" && \
    pip install --no-build-isolation chumpy==0.70 && \
    mim install "mmpose>=1.1.0"
```

If the OpenMMLab index doesn't have `cu128/torch2.7.0` yet, build mmcv from source:

```dockerfile
RUN pip install --no-cache-dir -U openmim && \
    mim install mmengine && \
    pip install --no-cache-dir "mmcv>=2.0.1" --no-binary mmcv && \
    mim install "mmdet>=3.1.0" && \
    pip install --no-build-isolation chumpy==0.70 && \
    mim install "mmpose>=1.1.0"
```

> [!NOTE]
> Building mmcv from source requires `nvidia/cuda:12.8.0-devel-ubuntu22.04` instead of `runtime`. This adds ~4GB to the base image but includes the CUDA compiler needed for building C++/CUDA extensions.

#### Issue 2: tensorflow conflict

The `requirements.txt` includes `tensorflow==2.12.0` which may not support CUDA 12.8. Options:
- Install CPU-only: `pip install tensorflow-cpu==2.12.0`
- Skip it if only used for TensorBoard logging
- Use newer version: `pip install tensorflow==2.18.0`

#### Issue 3: torchvision/torchaudio version mismatch

If `torchvision==0.22.0+cu128` doesn't exist, check the [PyTorch version compatibility table](https://pytorch.org/get-started/previous-versions/). Use:
```bash
pip install torch==2.7.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```
This lets pip resolve the matching versions automatically.

#### Issue 4: numpy version conflict

`numpy==1.23.5` in requirements.txt may conflict with PyTorch 2.7 (which requires numpy>=1.24). Update to `numpy>=1.24`.

### Step 4: Test Locally (if you have a Blackwell GPU)

```bash
docker run --rm --gpus all explaindio/musetalk-worker:unified-v4-blackwell \
  python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0)}, Arch: {torch.cuda.get_device_capability(0)}')"
```

Expected output: `CUDA: True, GPU: NVIDIA GeForce RTX 5060 Ti, Arch: (12, 0)`

### Step 5: Push to Docker Hub

```bash
# Must be logged in first: docker login -u explaindio
docker push explaindio/musetalk-worker:unified-v4-blackwell
```

### Step 6: Deploy on Salad

**Salad API base URL:** `https://api.salad.com/api/public`
**Organization:** `explaindiolls`
**Project:** `testing-gpus-musetalk`
**Auth header:** `Salad-Api-Key: <your key>`
**API docs:** https://docs.salad.com/reference/saladcloud-api/container-groups/create-container-group

**Required credentials** (get from the project owner or `.env` on the VPS at `/home/code10/musetalk/.env`):

| Variable | Description |
|:---|:---|
| `SALAD_API_KEY` | Salad Cloud API key |
| `DOCKER_HUB_PAT` | Docker Hub Personal Access Token for `explaindio` account |
| `INTERNAL_API_KEY` | Orchestrator internal API key |
| `B2_KEY_ID` | Backblaze B2 key ID |
| `B2_APP_KEY` | Backblaze B2 app key |

#### 6a. Look up GPU class UUID (if deploying to a different GPU)

```bash
curl -s "https://api.salad.com/api/public/organizations/explaindiolls/gpu-classes" \
  -H "Salad-Api-Key: $SALAD_API_KEY" | python3 -m json.tool
```

Known UUIDs:
| GPU | UUID | VRAM |
|:---|:---|:---|
| RTX 5060 Ti | `5d6b104d-c029-4357-b179-8b662d0a76b2` | 16GB |
| RTX 4070 | `0798d5aa-2d17-42ee-81b8-ea92e3bc088e` | 12GB |
| RTX 3090 | `e3f0eea1-05e9-4976-88e1-c3a85cfc3cfa` | 24GB |
| RTX 2080 | `ffc51032-64d2-4df3-855a-f3a649895c0f` | 8GB |
| RTX 2070 | `2aec4fc1-2270-4e40-b8cc-6e69fae61d4f` | 8GB |

#### 6b. Create the container group

```bash
curl -s -X POST \
  "https://api.salad.com/api/public/organizations/explaindiolls/projects/testing-gpus-musetalk/containers" \
  -H "Salad-Api-Key: $SALAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mt-rtx5060ti-blackwell",
    "display_name": "MuseTalk RTX 5060 Ti Blackwell",
    "autostart_policy": true,
    "container": {
      "image": "explaindio/musetalk-worker:unified-v4-blackwell",
      "resources": {
        "cpu": 4,
        "memory": 16384,
        "gpu_classes": ["5d6b104d-c029-4357-b179-8b662d0a76b2"],
        "shm_size": 8192
      },
      "priority": "batch",
      "registry_authentication": {
        "docker_hub": {
          "username": "explaindio",
          "personal_access_token": "<DOCKER_HUB_PAT>"
        }
      },
      "environment_variables": {
        "WORKER_TYPE": "main",
        "PROVIDER": "salad",
        "GPU_CLASS_NAME": "RTX-5060Ti-16GB",
        "ORCHESTRATOR_BASE_URL": "https://orch.avatargen.online",
        "POLL_INTERVAL_SEC": "10",
        "BATCH_SIZE": "4",
        "INTERNAL_API_KEY": "<INTERNAL_API_KEY>",
        "B2_KEY_ID": "<B2_KEY_ID>",
        "B2_APP_KEY": "<B2_APP_KEY>",
        "B2_BUCKET_NAME": "talking-avatar"
      }
    },
    "replicas": 1,
    "restart_policy": "always"
  }'
```

#### 6c. Check deployment status

```bash
curl -s \
  "https://api.salad.com/api/public/organizations/explaindiolls/projects/testing-gpus-musetalk/containers/mt-rtx5060ti-blackwell" \
  -H "Salad-Api-Key: $SALAD_API_KEY" | python3 -m json.tool
```

Or check the portal: https://portal.salad.com/organizations/explaindiolls/projects/testing-gpus-musetalk/containers

#### 6d. Stop/Delete the group

```bash
# Stop (keeps group, stops replicas):
curl -s -X POST \
  "https://api.salad.com/api/public/organizations/explaindiolls/projects/testing-gpus-musetalk/containers/mt-rtx5060ti-blackwell/stop" \
  -H "Salad-Api-Key: $SALAD_API_KEY" -H "Content-Length: 0"

# Delete (permanent — name cannot be reused):
curl -s -X DELETE \
  "https://api.salad.com/api/public/organizations/explaindiolls/projects/testing-gpus-musetalk/containers/mt-rtx5060ti-blackwell" \
  -H "Salad-Api-Key: $SALAD_API_KEY"
```

> [!CAUTION]
> **Salad API gotchas learned from testing:**
> - **Always set `autostart_policy: true`** — the `/start` endpoint hangs and often doesn't work
> - **No parentheses in `display_name`** — Salad rejects them
> - **Deleted group names cannot be reused** — pick unique names (e.g., include date)
> - **Use image tag only** — Salad rejects `@sha256:` digests
> - **`registry_authentication`** goes inside `container`, not at top level
> - **Docker Hub auth uses `personal_access_token`**, not `password`
> - **`memory: 16384`** (16GB) and **`shm_size: 8192`** (8GB) are the tested values
> - **`priority: "batch"`** is cheapest ($0.07/hr for most GPUs)

## Orchestrator API Reference

The worker communicates with the orchestrator at `https://orch.avatargen.online`. All requests require the `X-Internal-API-Key` header.

### Environment Variables

| Variable | Required | Description |
|:---|:---|:---|
| `ORCHESTRATOR_BASE_URL` | ✅ | `https://orch.avatargen.online` |
| `INTERNAL_API_KEY` | ✅ | Auth key (sent as `X-Internal-API-Key` header) |
| `WORKER_TYPE` | ✅ | `main`, `transient`, or `expensive` |
| `PROVIDER` | ✅ | `salad`, `octaspace`, `vast`, `tensordock`, `runpod` |
| `GPU_CLASS_NAME` | ✅ | e.g. `RTX-5060Ti-16GB` |
| `B2_KEY_ID` | ✅ | Backblaze B2 key ID |
| `B2_APP_KEY` | ✅ | Backblaze B2 app key |
| `B2_BUCKET_NAME` | ✅ | `talking-avatar` |
| `POLL_INTERVAL_SEC` | ❌ | Seconds between polls (default: `5`) |

Worker ID is auto-detected: `SALAD_MACHINE_ID` → `VAST_CONTAINERLABEL` → `WORKER_ID` → random.

### API Endpoints

#### 1. Heartbeat: `POST /internal/main/workers/{worker_id}/heartbeat`

Sent every `POLL_INTERVAL_SEC` seconds. Worker is marked offline after 30s of no heartbeat.

```json
{
  "status": "idle" | "busy",
  "current_job_id": null | "job-uuid",
  "provider": "salad",
  "gpu_class": "RTX-5060Ti-16GB",
  "worker_type": "main"
}
```

#### 2. Claim Job: `POST /internal/main/jobs/claim`

```json
// Request:
{ "worker_id": "machine-abc", "worker_type": "main", "gpu_class": "RTX-5060Ti-16GB" }

// Response (job available):
{
  "job": {
    "musetalk_job_id": "uuid",
    "video_url": "https://...",
    "audio_url": "https://...",
    "aspect_ratio": "1:1",
    "resolution": "512x512"
  }
}

// Response (no job):
{ "job": null }
```

#### 3. Report Progress: `POST /internal/jobs/{job_id}/progress`

```json
{
  "status": "running" | "succeeded" | "failed",
  "progress": 0.5,
  "phase": "downloading" | "inferring" | "encoding" | "uploading" | "completed",
  "worker_id": "machine-abc",
  "metrics": {
    "GENERATION_TIME_SEC": 11.0,
    "PEAK_VRAM_MIB": 7064.7,
    "gpu_class": "RTX-5060Ti-16GB",
    "stage_times": { "download": 0.37, "inference": 99.3, "upload": 1.1 },
    "total_time": 100.96
  },
  "error": null
}
```

### Success Response (from `/generate` endpoint)

```json
{
  "status": "success",
  "output_url": "https://f000.backblazeb2.com/file/talking-avatar/avatar/outputs/job-123.mp4",
  "musetalk_job_id": "job-123",
  "metrics": { ... }
}
```

### Error Response (422/500)

```json
{
  "status": "failed",
  "error_type": "processing_error",
  "error_message": "Inference failed: CUDA out of memory",
  "stage": "inference",
  "details": { "is_oom": true },
  "retryable": true,
  "stage_times": { "download": 0.37 }
}
```

> [!TIP]
> Full specs are also in the repo: `UNIFIED_WORKER_SPEC.md` and `ORCHESTRATOR_INTEGRATION_GUIDE.md`.

---

## Key Notes

- **This does NOT need a Blackwell GPU to build** — Docker builds don't use the GPU
- **The worker code is 100% identical** — only the CUDA/PyTorch layer changes
- **The main risk is MMLab dependency conflicts** — mmcv/mmdet/mmpose may need version bumps
- **Build on any machine with Docker** — the current VPS (RTX 3090) works fine for building
- **Expected build time:** 30-60 minutes (mostly model weight downloads)
- **Expected image size:** ~15-20GB (similar to unified-v4)

