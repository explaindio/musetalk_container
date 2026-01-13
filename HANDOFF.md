# MuseTalk Worker System - Session Handoff

**Date:** January 13, 2026  
**Repository:** `https://github.com/explaindio/musetalk_container`  
**Docker Hub Image:** `explaindio/musetalk-worker:unified-v1`

---

## 1. Project Purpose

This project implements a **GPU worker system** for the MuseTalk video generation service. The system:
- Generates lip-synced avatar videos from audio + source video
- Uploads results to Backblaze B2 storage
- Reports progress/completion to a central Orchestrator

### Architecture
```
┌─────────────────────┐    ┌──────────────────┐    ┌─────────────┐
│  Orchestrator       │◄───│  GPU Workers     │───►│  B2 Storage │
│  (orch.avatargen.)  │    │  (Salad/Vast/    │    │             │
│                     │    │   Local Buffer)  │    │             │
└─────────────────────┘    └──────────────────┘    └─────────────┘
```

Workers poll the orchestrator for jobs, process them locally using MuseTalk inference, upload results to B2, and report completion.

---

## 2. Key Components

### Files
| File | Purpose |
|------|---------|
| `unified_worker.py` | Main polling worker loop - heartbeats, claims jobs, calls `/generate`, reports progress |
| `worker_app/main.py` | FastAPI app with `/generate` endpoint - downloads media, runs inference, uploads to B2 |
| `Dockerfile.unified` | Builds the unified worker image (uses base image + overlays local code) |
| `Dockerfile.base` | Builds complete base image from scratch (includes model weights) |
| `start_unified.sh` | Entrypoint script - runs uvicorn + unified_worker.py concurrently |
| `DEPLOY_INSTRUCTIONS.md` | Deployment guide for Salad/Vast.ai |

### Docker Images
| Image | Purpose |
|-------|---------|
| `explaindio/musetalk-worker:unified-v1` | **Production image** - deploy this everywhere |
| `explaindio/musetalk-queue-worker:progress` | Base image on Docker Hub (contains models) |
| `musetalk-base:local` | Local-only base image (built from `Dockerfile.base`) |

---

## 3. Current State

### ✅ Working
- **Local Buffer Worker:** Container `buffer-local-unified-1` running with `--restart=always`
- **Auto-Restart:** Survives computer reboots (verified multiple times)
- **Job Processing:** Claims jobs, runs inference, uploads to B2, reports completion
- **Heartbeat:** Background thread keeps worker visible during long inference

### ✅ Fixed Bugs
1. **Heartbeat Timeout:** Workers went "offline" during inference → Fixed with threaded heartbeat
2. **Success Loop:** Worker expected `"succeeded"` but got `"success"` → Fixed to accept both
3. **Missing Completion Report:** Worker finished but didn't tell orchestrator → Fixed with `report_progress()` call
4. **B2 File Check:** Added explicit file existence check before upload

### ⚠️ Potential Issues
- **Salad Workers:** May be using cached old image. Verify digest matches `sha256:535cadda2f3a40fd962e76d7bc03980b526637332cab543e30153e88ca2ed3dc`
- **Shared Memory:** Salad/Vast MUST set `shm_size=8GB` or inference crashes

---

## 4. Local Buffer Worker Setup

The local buffer worker runs on the user's machine with an RTX GPU.

### Container Details
- **Name:** `buffer-local-unified-1`
- **Image:** `explaindio/musetalk-worker:unified-v1`
- **Restart Policy:** `--restart=always` (Docker auto-restarts on reboot)
- **Port:** 8001 → 8000 (internal)
- **GPU:** Uses all GPUs (`--gpus all`)
- **Shared Memory:** 8GB (`--shm-size=8g`)

### Start Command
```bash
docker run -d --gpus all --shm-size=8g \
  --restart=always \
  -p 8001:8000 \
  --env-file .env \
  --name buffer-local-unified-1 \
  -e WORKER_ID=buffer-local-unified-1 \
  -e WORKER_TYPE=main \
  -e PROVIDER=local \
  -e GPU_CLASS_NAME=RTX-local-buffer \
  -e ORCHESTRATOR_BASE_URL=https://orch.avatargen.online \
  -e POLL_INTERVAL_SEC=5 \
  explaindio/musetalk-worker:unified-v1
```

### Check Status
```bash
docker ps --filter "name=buffer"
docker logs --tail 50 buffer-local-unified-1
```

---

## 5. Environment Variables

Located in `/home/a/musetalk/.env`:

| Variable | Value | Purpose |
|----------|-------|---------|
| `ORCHESTRATOR_BASE_URL` | `https://orch.avatargen.online` | Orchestrator API |
| `INTERNAL_API_KEY` | (secret) | Auth for orchestrator |
| `B2_KEY_ID` | `00580d90663733b...` | Backblaze auth |
| `B2_APP_KEY` | `K005jgPrn8ri...` | Backblaze auth |
| `B2_BUCKET_NAME` | `talking-avatar` | B2 bucket for results |

---

## 6. Common Tasks

### Check if Container is Running
```bash
docker ps --filter "name=buffer"
```

### View Logs
```bash
docker logs --tail 100 buffer-local-unified-1
```

### Restart with Latest Image
```bash
docker rm -f buffer-local-unified-1
docker pull explaindio/musetalk-worker:unified-v1
# Then run the start command from section 4
```

### Build and Push New Image
```bash
cd /home/a/musetalk
docker build -f Dockerfile.unified -t explaindio/musetalk-worker:unified-v1 .
docker push explaindio/musetalk-worker:unified-v1
```

### Commit and Push Code
```bash
cd /home/a/musetalk
git add -A
git commit -m "Your message"
git push
```

---

## 7. What's Next

### Immediate Task
**Verify container auto-start after reboot:**
```bash
docker ps --filter "name=buffer"
```
Expected: `buffer-local-unified-1` should show status like "Up X minutes"

### Pending Issues
1. **Salad Workers:** Need to confirm they're pulling the correct image digest
2. **Old Docker Hub Tags:** Manual cleanup still needed for:
   - `explaindio/musetalk-worker:vast-v1`
   - `explaindio/musetalk-queue-worker:progress` (maybe keep as base?)

---

## 8. Important Digests

**Current Production Digest:**
```
sha256:535cadda2f3a40fd962e76d7bc03980b526637332cab543e30153e88ca2ed3dc
```

Any worker should show this digest. If different, they have an old image.

---

## 9. Old Systemd Service (Disabled)

There was an old systemd user service at `~/.config/systemd/user/buffer-worker.service` that kept respawning an old container. It was:
- Deleted with `sudo rm -f /home/a/.config/systemd/user/buffer-worker.service`
- The current container uses Docker's `--restart=always` instead (works better)

---

## 10. Repository Structure

```
/home/a/musetalk/
├── unified_worker.py      # Polling loop (heartbeat, claim, report)
├── worker_app/
│   └── main.py            # FastAPI /generate endpoint
├── Dockerfile.unified     # Production image build
├── Dockerfile.base        # Full build from scratch
├── build_self_contained.sh # Script to build locally
├── start_unified.sh       # Container entrypoint
├── DEPLOY_INSTRUCTIONS.md # Salad/Vast deployment guide
├── .env                   # Secrets (not in git)
└── MuseTalk/              # MuseTalk source code
```

---

## 11. Quick Debugging

### Job stuck at 0.95?
- Check if upload succeeded in logs
- Verify B2 credentials in `.env`
- Check if `report_progress` was called (look for "Job ... succeeded" in logs)

### Container not starting?
- Check `docker logs buffer-local-unified-1`
- Verify `.env` file exists
- Ensure GPU drivers are working: `nvidia-smi`

### Worker not appearing in orchestrator?
- Check heartbeat logs
- Verify `ORCHESTRATOR_BASE_URL` is correct
- Check `INTERNAL_API_KEY` is set

---

**End of Handoff**
