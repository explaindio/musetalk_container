# 🚀 Unified Worker Deployment Instructions

**The unified worker image is ready and tested.**
**Image:** `explaindio/musetalk-worker:unified-v1`
**Digest:** `sha256:16d87df270be3fc21a25edf7a9643ada299d90a37963f60ad3cc73178c2d3879`
*(Updated Jan 2, 2026 with Threaded Heartbeat Fix)*

---

## ⚠️ Critical Update (Jan 2)
**You MUST redeploy all workers.**
A critical bug where workers stopped sending heartbeats during inference has been fixed. The new image uses a background thread to maintain connectivity.
- **Old behavior:** Worker went "offline" in DB during 30s+ jobs.
- **New behavior:** Worker stays "busy" in DB throughout job processing.

---

## 1. Salad Deployment (Main Workers)

Update your Container Group with the following configuration:

| Field | Value |
|-------|-------|
| **Image Source** | `explaindio/musetalk-worker:unified-v1` |
| **Replica Count** | As needed (start with 1-3) |
| **CPU** | 4 vCPU |
| **RAM** | 16 GB |
| **GPU** | RTX 3060, 3080, 4060, 4090 (any) |
| **Batch Priority** | High (optional but recommended) |

### Environment Variables

| Variable | Value |
|----------|-------|
| `ORCHESTRATOR_BASE_URL` | `https://orch.avatargen.online` |
| `INTERNAL_API_KEY` | *(Your Secret Key)* |
| `WORKER_TYPE` | `main` |
| `PROVIDER` | `salad` |
| `GPU_CLASS_NAME` | `RTX_3060` (or match the GPU selected) |
| `B2_KEY_ID` | *(Your Backblaze Key ID)* |
| `B2_APP_KEY` | *(Your Backblaze App Key)* |
| `B2_BUCKET_NAME` | `talking-avatar` |
| `POLL_INTERVAL_SEC` | `5` |

**⚠️ CRITICAL SETTINGS:**
- **Shared Memory:** You MUST set `shm_size` to **8192 MB (8GB)** (default is 64MB which crashes).
- **Probes:**
  - **Liveness:** `http`: port `8000` path `/health` (initial delay 30s)
  - **Readiness:** `http`: port `8000` path `/health`

---

## 2. Vast.ai Deployment (Transient Workers)

Deploy new instances using this On-Start script:

```bash
docker run -d --gpus all --rm --network host --shm-size=8g \
  --name musetalk-worker \
  -e WORKER_ID=vast-${VAST_CONTAINERLABEL} \
  -e WORKER_TYPE=transient \
  -e PROVIDER=vast \
  -e GPU_CLASS_NAME=RTX_4090 \
  -e ORCHESTRATOR_BASE_URL=https://orch.avatargen.online \
  -e INTERNAL_API_KEY=YOUR_KEY_HERE \
  -e B2_KEY_ID=YOUR_KEY_ID \
  -e B2_APP_KEY=YOUR_APP_KEY \
  -e B2_BUCKET_NAME=talking-avatar \
  -e POLL_INTERVAL_SEC=5 \
  explaindio/musetalk-worker:unified-v1
```

---

## 3. Verification

Once deployed, check the orchestrator database or logs. You should see workers registering/heartbeating:

```
POST /internal/main/workers/{id}/heartbeat
{
  "status": "idle",
  "provider": "salad",
  "gpu_class": "RTX_3060", 
  "worker_type": "main"
}
```
