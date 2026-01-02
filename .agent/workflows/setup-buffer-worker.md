---
description: Set up a buffer GPU worker for the VPS orchestrator
---

# Buffer GPU Worker Setup

This workflow sets up a MuseTalk buffer GPU worker that connects to the VPS orchestrator at `https://orch.avatargen.online`.

## Prerequisites
- Ubuntu/Debian with NVIDIA GPU
- Docker with GPU support (`nvidia-container-toolkit`)
- Network access to `https://orch.avatargen.online`

---

## Step 1: Get worker ID from user

Ask the user what `BUFFER_WORKER_ID` to use (e.g., `buffer-orch-local-2`, `buffer-orch-local-3`).

---

## Step 2: Create working directory

// turbo
```bash
mkdir -p ~/musetalk && cd ~/musetalk
```

---

## Step 3: Create .env file

```bash
cat > ~/musetalk/.env << 'EOF'
SALAD_API_KEY=salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p
SALAD_ORG_NAME=explaindiolls
SALAD_PROJECT_NAME=project2
INTERNAL_API_KEY=changeme-internal-key
B2_KEY_ID=00580d90663733b000000000c
B2_APP_KEY=K005jgPrn8riZCmk5RUYhIzdlj+s0xI
B2_BUCKET_NAME=talking-avatar
B2_PREFIX=avatar/outputs
EOF
```

---

## Step 4: Pull Docker image

// turbo
```bash
docker pull explaindio/musetalk-queue-worker:progress
```

---

## Step 5: Create systemd user service

Create `~/.config/systemd/user/buffer-worker.service`:

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/buffer-worker.service << 'EOF'
[Unit]
Description=Local buffer GPU worker (MuseTalk queue)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=%h/musetalk
ExecStart=/usr/bin/docker run --gpus all --rm --network host \
  --env-file .env \
  --name WORKER_ID_PLACEHOLDER \
  -e BUFFER_WORKER_ID=WORKER_ID_PLACEHOLDER \
  -e BUFFER_ORCHESTRATOR_BASE_URL=https://orch.avatargen.online \
  -e ORCHESTRATOR_BASE_URL=https://orch.avatargen.online \
  -e GPU_CLASS_NAME=RTX-local-buffer \
  -e BUFFER_CAPACITY=1 \
  -e BUFFER_POLL_INTERVAL_SEC=5 \
  explaindio/musetalk-queue-worker:progress \
  uvicorn worker_app.main:app --host 0.0.0.0 --port 8000
ExecStop=-/usr/bin/docker stop WORKER_ID_PLACEHOLDER
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF
```

Then replace `WORKER_ID_PLACEHOLDER` with the actual worker ID:

```bash
sed -i 's/WORKER_ID_PLACEHOLDER/buffer-orch-local-2/g' ~/.config/systemd/user/buffer-worker.service
```

---

## Step 6: Enable user lingering

// turbo
```bash
loginctl enable-linger $USER
```

---

## Step 7: Start the service

// turbo
```bash
systemctl --user daemon-reload
systemctl --user enable buffer-worker.service
systemctl --user start buffer-worker.service
```

---

## Step 8: Verify

// turbo
```bash
sleep 5 && systemctl --user status buffer-worker.service --no-pager
```

// turbo
```bash
docker exec buffer-orch-local-2 env | grep -E 'ORCHESTRATOR_BASE_URL|BUFFER_ORCHESTRATOR'
```

// turbo
```bash
docker exec buffer-orch-local-2 curl -s https://orch.avatargen.online/health
```

Expected:
- `BUFFER_ORCHESTRATOR_BASE_URL=https://orch.avatargen.online`
- `ORCHESTRATOR_BASE_URL=https://orch.avatargen.online`
- `{"status":"ok","salad_ok":true,...}`

---

## Troubleshooting

If container fails to start:
```bash
docker logs buffer-orch-local-2
journalctl --user -u buffer-worker.service -n 50
```

If wrong URLs appear:
```bash
cat ~/.config/systemd/user/buffer-worker.service | grep ORCHESTRATOR
```
