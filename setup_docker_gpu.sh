#!/bin/bash
# MuseTalk Worker — Docker + NVIDIA GPU Setup Script
# Run this on a new machine to install Docker and NVIDIA Container Toolkit

set -e

echo "=== MuseTalk Docker + GPU Setup ==="
echo ""

# 1. Check NVIDIA drivers
echo "[1/5] Checking NVIDIA drivers..."
if ! command -v nvidia-smi &>/dev/null; then
    echo "ERROR: nvidia-smi not found. Install NVIDIA drivers first:"
    echo "  sudo apt install nvidia-driver-535"
    exit 1
fi
GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
echo "  GPU: $GPU ✓"

# 2. Install Docker
echo "[2/5] Checking Docker..."
if ! command -v docker &>/dev/null; then
    echo "  Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "  Docker installed. You may need to log out and back in for group changes."
else
    DOCKER_VER=$(docker --version | awk '{print $3}')
    echo "  Docker $DOCKER_VER ✓"
fi

# 3. Install NVIDIA Container Toolkit
echo "[3/5] Checking NVIDIA Container Toolkit..."
if ! dpkg -l | grep -q nvidia-container-toolkit 2>/dev/null; then
    echo "  Installing NVIDIA Container Toolkit..."
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
        sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    echo "  NVIDIA Container Toolkit installed ✓"
else
    echo "  NVIDIA Container Toolkit already installed ✓"
fi

# 4. Verify GPU access in Docker
echo "[4/5] Testing GPU access in Docker..."
if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
    echo "  GPU accessible in Docker ✓"
else
    echo "  ERROR: GPU not accessible in Docker. Check NVIDIA Container Toolkit installation."
    exit 1
fi

# 5. Pull the worker image
echo "[5/5] Pulling worker image (17.7 GB)..."
docker pull explaindio/musetalk-worker:unified-v6
echo "  Image pulled ✓"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "GPU: $GPU"
echo "Docker: $(docker --version | awk '{print $3}')"
echo "Image: explaindio/musetalk-worker:unified-v6"
echo ""
echo "Next: Start the worker with:"
echo "  source .env && docker run -d --gpus all --shm-size=8g \\"
echo "    --restart=unless-stopped --network host \\"
echo "    --name buffer-local-unified-1 \\"
echo "    -e WORKER_ID=buffer-local-unified-1 \\"
echo "    -e BUFFER_WORKER_ID=buffer-local-unified-1 \\"
echo "    -e WORKER_TYPE=main -e PROVIDER=local \\"
echo "    -e GPU_CLASS_NAME=RTX-3090-Local-Buffer-1 \\"
echo "    -e ORCHESTRATOR_BASE_URL=https://orch.avatargen.online \\"
echo "    -e INTERNAL_API_KEY=\$INTERNAL_API_KEY \\"
echo "    -e B2_KEY_ID=\$B2_KEY_ID -e B2_APP_KEY=\$B2_APP_KEY \\"
echo "    -e B2_BUCKET_NAME=\$B2_BUCKET_NAME \\"
echo "    -e POLL_INTERVAL_SEC=5 -e CONFIG_LABEL=batch8-local-buffer \\"
echo "    -e BATCH_SIZE=8 -e USE_OPTIMIZED_INFERENCE=true \\"
echo "    explaindio/musetalk-worker:unified-v6"
