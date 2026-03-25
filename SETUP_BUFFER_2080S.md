# Buffer Worker #2 — RTX 2080 Super Setup

**Worker ID:** `buffer-local-unified-2`
**GPU Class:** `RTX-2080S-Local-Buffer-2`
**Image:** `explaindio/musetalk-worker:unified-v7@sha256:41a665ef63d50f7a70a37b0a805fd44335befbb8b6fdaaf8d36107b834634989`

---

## 1. Install Docker + NVIDIA Toolkit

```bash
# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# Install NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify GPU access
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

## 2. Log in to Docker Hub & Pull Image

```bash
# Set these or source from .env
export DOCKER_USERNAME=<your-dockerhub-username>
export DOCKER_PAT=<your-dockerhub-pat>

echo $DOCKER_PAT | docker login -u $DOCKER_USERNAME --password-stdin
docker pull explaindio/musetalk-worker:unified-v7@sha256:41a665ef63d50f7a70a37b0a805fd44335befbb8b6fdaaf8d36107b834634989
```

## 3. Create `.env` File

Create a `.env` file with these secrets (same values as the 3090 machine):

```
INTERNAL_API_KEY=<same-key>
B2_KEY_ID=<same-key>
B2_APP_KEY=<same-key>
B2_BUCKET_NAME=<same-bucket>
```

## 4. Start the Worker

```bash
source .env && docker run -d --gpus all --shm-size=8g \
  --restart=unless-stopped \
  --network host \
  --name buffer-local-unified-2 \
  -e WORKER_ID=buffer-local-unified-2 \
  -e BUFFER_WORKER_ID=buffer-local-unified-2 \
  -e WORKER_TYPE=main \
  -e PROVIDER=local \
  -e GPU_CLASS_NAME=RTX-2080S-Local-Buffer-2 \
  -e ORCHESTRATOR_BASE_URL=https://orch.avatargen.online \
  -e INTERNAL_API_KEY=$INTERNAL_API_KEY \
  -e B2_KEY_ID=$B2_KEY_ID \
  -e B2_APP_KEY=$B2_APP_KEY \
  -e B2_BUCKET_NAME=$B2_BUCKET_NAME \
  -e POLL_INTERVAL_SEC=5 \
  -e CONFIG_LABEL=batch8-local-buffer \
  -e BATCH_SIZE=8 \
  -e USE_OPTIMIZED_INFERENCE=true \
  explaindio/musetalk-worker:unified-v7@sha256:41a665ef63d50f7a70a37b0a805fd44335befbb8b6fdaaf8d36107b834634989
```

> **Note:** BATCH_SIZE=4 (vs 8 on the 3090) — the 2080 Super has 8 GB VRAM vs 24 GB. If CUDA OOM occurs, reduce to BATCH_SIZE=2.

## 5. Verify

```bash
docker logs -f buffer-local-unified-2
# Should see: [buffer_hb] Sent successfully. HTTP 200
```

## 6. Container Management

```bash
docker stop buffer-local-unified-2    # stop, frees VRAM
docker start buffer-local-unified-2   # restart after stop
docker logs --tail 50 buffer-local-unified-2  # view logs
docker rm -f buffer-local-unified-2   # remove entirely
```

---

## VRAM Note

| GPU | VRAM | Batch Size | Expected VRAM Usage |
|-----|------|-----------|-------------------|
| RTX 3090 | 24 GB | 8 | ~7 GB |
| RTX 2080 Super | 8 GB | 4 | ~5-6 GB (estimated) |

If the 2080 Super runs out of VRAM, reduce `BATCH_SIZE` to 2 or 1.
