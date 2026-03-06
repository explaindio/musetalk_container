# MuseTalk Worker — Full Handoff Guide

**Date:** March 5, 2026
**Repository:** `https://github.com/explaindio/musetalk_container`
**Docker Image:** `explaindio/musetalk-worker:unified-v6`
**Digest:** `sha256:3131259df1cb61525e240bfee67be1ff851f155ea86720fb3fd83f92ecc89851`

---

## Quick Start (New Machine)

```bash
# 1. Install Docker + NVIDIA Container Toolkit (if not installed)
./setup_docker_gpu.sh

# 2. Pull the image (~17.7 GB)
docker pull explaindio/musetalk-worker:unified-v6

# 3. Start the worker
source .env && docker run -d --gpus all --shm-size=8g \
  --restart=unless-stopped \
  --network host \
  --name buffer-local-unified-1 \
  -e WORKER_ID=buffer-local-unified-1 \
  -e BUFFER_WORKER_ID=buffer-local-unified-1 \
  -e WORKER_TYPE=main \
  -e PROVIDER=local \
  -e GPU_CLASS_NAME=RTX-3090-Local-Buffer-1 \
  -e ORCHESTRATOR_BASE_URL=https://orch.avatargen.online \
  -e INTERNAL_API_KEY=$INTERNAL_API_KEY \
  -e B2_KEY_ID=$B2_KEY_ID \
  -e B2_APP_KEY=$B2_APP_KEY \
  -e B2_BUCKET_NAME=$B2_BUCKET_NAME \
  -e POLL_INTERVAL_SEC=5 \
  -e CONFIG_LABEL=batch8-local-buffer \
  -e BATCH_SIZE=8 \
  -e USE_OPTIMIZED_INFERENCE=true \
  explaindio/musetalk-worker:unified-v6

# 4. Verify
docker logs -f buffer-local-unified-1
# Should see: [buffer_hb] Sent successfully. HTTP 200
```

---

## 1. Docker + NVIDIA GPU Setup

A setup script is included. Run it on the new machine:

```bash
chmod +x setup_docker_gpu.sh && ./setup_docker_gpu.sh
```

**What it does:**
1. Installs Docker Engine (if missing)
2. Installs NVIDIA Container Toolkit (for GPU passthrough)
3. Configures Docker to use the NVIDIA runtime
4. Verifies GPU access inside containers

**Manual install (if script fails):**

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

---

## 2. Container Management

```bash
# Pause (keeps VRAM allocated, instant resume)
docker pause buffer-local-unified-1

# Unpause
docker unpause buffer-local-unified-1

# Stop (frees VRAM, takes 10-30s to restart)
docker stop buffer-local-unified-1

# Start (after stop)
docker start buffer-local-unified-1

# Force kill (instant, for when stop hangs)
docker kill buffer-local-unified-1

# View logs
docker logs --tail 50 buffer-local-unified-1

# Check heartbeats
docker logs --since 30s buffer-local-unified-1

# Remove entirely (need docker run again to recreate)
docker rm -f buffer-local-unified-1
```

---

## 3. What's in unified-v6

| Feature | Details |
|---------|---------|
| **Base** | `nvidia/cuda:11.8.0-runtime-ubuntu22.04` |
| **Size** | 17.7 GB (down from 95.5 GB in v1-v5) |
| **Models** | Baked in (~8.7 GB weights) |
| **Inference** | Optimized pipe-based FFmpeg encoding |
| **Heartbeat** | Resilient — recreates HTTP client each cycle |
| **Health** | `/hc` endpoint on port 8000 |
| **Entrypoint** | `/bin/bash /app/start_unified.sh` |

---

## 4. Required Environment Variables

All stored in `.env` in the repo root. **Do not commit this file.**

| Variable | Purpose |
|----------|---------|
| `INTERNAL_API_KEY` | Auth for orchestrator API |
| `B2_KEY_ID` | Backblaze B2 access key |
| `B2_APP_KEY` | Backblaze B2 secret key |
| `B2_BUCKET_NAME` | B2 bucket for video uploads |
| `SALAD_API_KEY` | SaladCloud API key |
| `SALAD_ORG_NAME` | Salad org (`explaindiolls`) |
| `SALAD_PROJECT_NAME` | Salad project (`project2`) |
| `DOCKER_USERNAME` | Docker Hub username |
| `DOCKER_PAT` | Docker Hub personal access token |

---

## 5. Key Files

| File | Purpose |
|------|---------|
| `Dockerfile.unified-v6` | Clean single-stage build (current production) |
| `unified_worker.py` | Main worker polling loop + heartbeat |
| `worker_app/main.py` | FastAPI app, buffer heartbeat loop, `/hc` endpoint |
| `start_unified.sh` | Container entrypoint (uvicorn + worker) |
| `scripts/inference_optimized.py` | Pipe-based FFmpeg inference |
| `refresh_salad_pricing.py` | Generates `SALAD_GPU_PRICING.md` from Salad API |
| `.env` | Secrets (not committed) |

---

## 6. Building a New Image

```bash
# From the repo root
docker build -t explaindio/musetalk-worker:unified-v7 -f Dockerfile.unified-v6 .

# Push to Docker Hub
docker login -u $DOCKER_USERNAME -p $DOCKER_PAT
docker push explaindio/musetalk-worker:unified-v7
```

---

## 7. Salad Cloud Deployment

To check GPU availability:
```bash
export $(grep -v '^#' .env | grep -v '^$' | xargs) && python3 refresh_salad_pricing.py
```

To deploy on Salad, use the Salad Portal or API. See `DEPLOY_V5_OPTIMIZED.md` and `BLACKWELL_BUILD_INSTRUCTIONS.md`.

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `docker: command not found` | Run `setup_docker_gpu.sh` |
| `could not select device driver "nvidia"` | Install NVIDIA Container Toolkit (see Section 1) |
| Container exits immediately | Check `docker logs buffer-local-unified-1` |
| No heartbeats in logs | Verify `ORCHESTRATOR_BASE_URL` and `INTERNAL_API_KEY` in `.env` |
| `docker stop` hangs | Use `docker kill buffer-local-unified-1` |
| Salad API times out | Try again later or from a different machine |
| VRAM not freed after pause | Use `docker stop` instead (pause keeps VRAM) |
