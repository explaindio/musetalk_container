# MuseTalk Unified Polling Worker - Docker Container Specification

## Worker Types (Priority Order)

| Priority | Type | Provider | Purpose |
|----------|------|----------|---------|
| 1 | **Main** | Salad, OctaSpace | Primary processing (deploy to cheaper) |
| 2* | **Transient** | Vast.ai, TensorDock | Scaling overflow |
| 3* | **Expensive** | Runpod | Last resort scaling |
| 4 | **Buffer** | Local GPU | Emergency + scaling buffer |

*Priority 2-4 is default order but can be **dynamic based on current pricing**.

**Buffer Purpose:**
- Emergency fallback when main workers unavailable
- Scaling buffer: handles jobs while scaling is in progress, until new cloud instances are ready and balanced

The new worker should be able to run as **Main**, **Transient**, or **Expensive** - buffer workers have different endpoints.

---

## Current vs New Architecture

### Current (Salad Queue)
```
Job → Salad Queue API → salad-http-job-queue-worker → /generate endpoint
                        (Salad controls routing)
```

### New (Unified Polling)
```
Job → Orchestrator DB → Worker polls /internal/main/jobs/claim
                        (We control everything)
```

---

## Worker Timeout Policy

| Condition | Action |
|-----------|--------|
| No heartbeat for **30 seconds** | Worker marked `offline` |
| Worker `offline` with assigned job | Job returned to queue for reassignment |
| Worker comes back online | Must re-register or send heartbeat to become `idle` |

---

## NEW Endpoints Needed (for main worker polling)

The orchestrator needs these **NEW** endpoints for non-Salad workers:

### 1. `POST /internal/main/workers/{worker_id}/register` (Optional)
```json
{
  "worker_type": "main" | "transient" | "expensive",
  "gpu_class": "RTX_3060",
  "provider": "salad" | "octaspace" | "vast" | "tensordock" | "runpod",
  "capacity": 1
}
```
**Note:** Registration is optional - orchestrator can auto-register on first heartbeat.

### 2. `POST /internal/main/workers/{worker_id}/heartbeat`
```json
{
  "status": "idle" | "busy",
  "current_job_id": null | "job-uuid",
  "provider": "vast",
  "gpu_class": "RTX_3060",
  "worker_type": "transient"
}
```
**Note:** Include `provider`, `gpu_class`, and `worker_type` in heartbeat so orchestrator can track even after worker restart, and allows dynamic priority changes without restart.

### 3. `POST /internal/main/jobs/claim`
```json
Request:
{
  "worker_id": "vast-gpu-123",
  "worker_type": "transient",
  "gpu_class": "RTX_3080"
}

Response (job available):
{
  "job": {
    "musetalk_job_id": "uuid",
    "video_url": "https://...",
    "audio_url": "https://...",
    "aspect_ratio": "1:1",
    "resolution": "512x512"
  }
}

Response (no job):
{
  "job": null
}

Response (error):
{
  "job": null,
  "error": "database_unavailable"
}
```

### 4. Use existing: `POST /internal/jobs/{job_id}/progress`
Same endpoint as current Salad workers.

---

## Existing API Endpoints (for reference)

### Main Worker Progress (`POST /internal/jobs/{job_id}/progress`)

```json
{
  "status": "running" | "succeeded" | "failed",
  "progress": 0.45,
  "phase": "downloading" | "inferring" | "encoding" | "uploading" | "completed",
  "worker_id": "salad-abc123",
  "metrics": {
    "b2_bucket": "talking-avatar",
    "b2_file_name": "avatar/outputs/job-id.mp4",
    "GENERATION_TIME_SEC": 37.2,
    "gpu_class": "RTX_3060"
  },
  "error": null
}
```

### Buffer Worker Endpoints (DIFFERENT - for buffer only)

```bash
POST /internal/buffer/workers/{worker_id}/heartbeat
POST /internal/buffer/jobs/claim  
POST /internal/buffer/jobs/{buffer_job_id}/status
```

---

## Required Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ORCHESTRATOR_BASE_URL` | ✅ | - | `https://orch.avatargen.online` |
| `INTERNAL_API_KEY` | ✅ | - | Auth key |
| `WORKER_TYPE` | ✅ | - | `main`, `transient`, or `expensive` |
| `PROVIDER` | ✅ | - | `salad`, `octaspace`, `vast`, `tensordock`, `runpod` |
| `GPU_CLASS_NAME` | ✅ | - | `RTX_3060`, `RTX_3080`, etc. |
| `B2_KEY_ID` | ✅ | - | Backblaze B2 key |
| `B2_APP_KEY` | ✅ | - | Backblaze B2 secret |
| `B2_BUCKET_NAME` | ✅ | - | Upload bucket name |
| `B2_PREFIX` | ❌ | `""` | Path prefix in bucket |
| `POLL_INTERVAL_SEC` | ❌ | `5` | Seconds between polls |

**Auto-detected (optional):**
- `SALAD_MACHINE_ID` - Salad provides this
- `VAST_CONTAINERLABEL` - Vast provides this
- `OCTASPACE_NODE_ID` - OctaSpace provides this

---

## Worker Loop (Python Pseudocode)

```python
import os
import time
import httpx

ORCH_URL = os.environ["ORCHESTRATOR_BASE_URL"]
API_KEY = os.environ["INTERNAL_API_KEY"]
WORKER_ID = (
    os.environ.get("SALAD_MACHINE_ID") or 
    os.environ.get("VAST_CONTAINERLABEL") or 
    os.environ.get("OCTASPACE_NODE_ID") or 
    "worker-" + os.urandom(4).hex()
)
WORKER_TYPE = os.environ.get("WORKER_TYPE", "main")
PROVIDER = os.environ.get("PROVIDER", "unknown")
GPU_CLASS = os.environ.get("GPU_CLASS_NAME", "unknown")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SEC", "5"))

HEADERS = {"X-Internal-API-Key": API_KEY}

def heartbeat(status="idle", current_job=None):
    try:
        httpx.post(
            f"{ORCH_URL}/internal/main/workers/{WORKER_ID}/heartbeat",
            json={
                "status": status, 
                "current_job_id": current_job,
                "provider": PROVIDER,
                "gpu_class": GPU_CLASS,
                "worker_type": WORKER_TYPE
            },
            headers=HEADERS, timeout=5
        )
    except Exception as e:
        print(f"Heartbeat failed: {e}")

def claim_job():
    """Claim job with retry logic and exponential backoff."""
    for attempt in range(3):
        try:
            r = httpx.post(
                f"{ORCH_URL}/internal/main/jobs/claim",
                json={
                    "worker_id": WORKER_ID, 
                    "worker_type": WORKER_TYPE, 
                    "gpu_class": GPU_CLASS
                },
                headers=HEADERS, timeout=10
            )
            data = r.json()
            if data.get("error"):
                print(f"Claim error: {data['error']}")
                return None
            return data.get("job")
        except Exception as e:
            print(f"Claim attempt {attempt+1} failed: {e}")
            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
    return None

def report_progress(job_id, status, progress, phase, metrics=None, error=None):
    try:
        httpx.post(
            f"{ORCH_URL}/internal/jobs/{job_id}/progress",
            json={
                "status": status,
                "progress": progress,
                "phase": phase,
                "worker_id": WORKER_ID,
                "metrics": metrics,
                "error": error
            },
            headers=HEADERS, timeout=5
        )
    except Exception as e:
        print(f"Progress report failed: {e}")

def main():
    print(f"Worker {WORKER_ID} starting ({PROVIDER}/{GPU_CLASS})")
    
    while True:
        heartbeat("idle")
        job = claim_job()
        
        if job:
            job_id = job["musetalk_job_id"]
            heartbeat("busy", job_id)
            
            try:
                # Download
                report_progress(job_id, "running", 0.1, "downloading")
                # ... download video/audio ...
                
                # Inference  
                report_progress(job_id, "running", 0.5, "inferring")
                # ... run MuseTalk ...
                
                # Upload
                report_progress(job_id, "running", 0.95, "uploading")
                b2_bucket, b2_file_name = upload_to_b2(output_path, job_id)
                
                # Complete
                report_progress(job_id, "succeeded", 1.0, "completed", 
                    metrics={"b2_bucket": b2_bucket, "b2_file_name": b2_file_name, "gpu_class": GPU_CLASS})
                    
            except Exception as e:
                report_progress(job_id, "failed", 0.0, "failed", error=str(e))
        else:
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
```

---

## Dockerfile Structure

```dockerfile
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y python3 python3-pip ffmpeg

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# MuseTalk model and code
COPY musetalk/ ./musetalk/
COPY models/ ./models/
COPY worker.py .

CMD ["python3", "worker.py"]
```

---

## Next Steps for Implementation

1. **Orchestrator changes needed:**
   - Add `POST /internal/main/workers/{id}/heartbeat` endpoint
   - Add `POST /internal/main/jobs/claim` endpoint (with job selection by worker_type)
   - Add worker timeout tracking (30s → offline)
   - Modify job submission to queue in DB instead of Salad Queue

2. **Worker container changes:**
   - Remove `salad-http-job-queue-worker` dependency
   - Add polling loop with retry logic
   - Use existing `/internal/jobs/{id}/progress` for status reporting

3. **Deployment:**
   - No `queue_connection` in container group config
   - Just environment variables + worker image

---

## Key Differences from Buffer Workers

| Aspect | Buffer Workers | Main/Transient/Expensive Workers |
|--------|---------------|----------------------------------|
| Purpose | Emergency + scaling buffer | Primary processing |
| Endpoints | `/internal/buffer/*` | `/internal/main/*` + `/internal/jobs/*/progress` |
| Job status | Claims jobs with status `pending_buffer` | Claims jobs with status `pending` |
| Priority | Used during scaling & emergencies | Used for normal processing |
