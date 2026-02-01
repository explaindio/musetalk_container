#!/bin/bash
# Command to restore the buffer-local-unified-1 worker
# Use this when you are done testing the other model.

docker run -d --gpus all --shm-size=8g \
  --restart=always \
  --network host \
  --env-file /home/code10/musetalk/.env \
  --name buffer-local-unified-1 \
  -e WORKER_ID=buffer-local-unified-1 \
  -e BUFFER_WORKER_ID=buffer-local-unified-1 \
  -e WORKER_TYPE=main \
  -e PROVIDER=local \
  -e GPU_CLASS_NAME=RTX-local-buffer \
  -e ORCHESTRATOR_BASE_URL=https://orch.avatargen.online \
  -e POLL_INTERVAL_SEC=5 \
  -e CONFIG_LABEL=batch8-local-buffer \
  -e BATCH_SIZE=8 \
  explaindio/musetalk-worker:unified-v1

echo "Buffer worker restored!"
