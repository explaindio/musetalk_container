#!/bin/bash
set -e

echo "=========================================================="
echo " Building MuseTalk Self-Contained Images"
echo "=========================================================="

echo "[1/2] Building Base Image (Code + Dependencies + Weights)..."
echo "      This step downloads heavy weights (~10GB+). Be patient."
docker build -f Dockerfile.base -t musetalk-base:local .

echo ""
echo "[2/2] Building Unified Worker Image..."
docker build -f Dockerfile.unified \
  --build-arg BASE_IMAGE=musetalk-base:local \
  -t explaindio/musetalk-worker:unified-v1-selfcontained .

echo ""
echo "✅ Build Complete!"
echo "Image: explaindio/musetalk-worker:unified-v1-selfcontained"
echo ""
echo "To push this image:"
echo "  docker push explaindio/musetalk-worker:unified-v1-selfcontained"
