# FastWan 2.2 Orchestrator Integration Guide

## 1. Docker Image
**Image:** `explaindio/fastwan-worker:v1`
**Push Status:** (Pending - build in progress)

## 2. Salad Queue Configuration

Create a new **Job Queue** in Salad with these settings:

| Setting | Value |
| :--- | :--- |
| **Queue Name** | `fastwan-queue` (or similar) |
| **Container Image** | `explaindio/fastwan-worker:v1` |
| **Replica Count** | 0 (Scale manually or via autoscaler) |
| **vCPU** | 4+ |
| **RAM** | 32 GB (Required) |
| **GPU** | RTX 5090 (Recommended), A100 |

### Environment Variables
Configure these in the Salad User Group:

```properties
ORCHESTRATOR_BASE_URL=https://api.avatargen.online
# API Key for worker -> orchestrator communication
INTERNAL_API_KEY=<your-internal-api-key>

# B2 Storage Credentials (for uploading video results)
B2_KEY_ID=<your-b2-key-id>
B2_APP_KEY=<your-b2-app-key>
B2_BUCKET_NAME=talking-avatar
B2_PREFIX=avatar/outputs
```

## 3. Orchestrator Database Updates

Add a new entry to the `gpu_classes` table:

```sql
INSERT INTO gpu_classes (name, vram_gb, hourly_price_usd)
VALUES ('RTX-5090-FastWan', 32, 0.60);
```

## 4. API Request Handling

When a client requests a video generation with model `fastwan`, rout the job to the new Salad Queue.

**Job Payload to Salad Queue:**
The worker expects a JSON payload at its `/generate` endpoint (via Salad's job mechanism).
The orchestrator should push a job to the `fastwan-queue` with this body:

```json
{
  "musetalk_job_id": "<job_uuid>",
  "image_url": "https://...",
  "prompt": "She speaks with calm composed energy...",
  "num_frames": 81,
  "width": 720,
  "height": 1280,
  "steps": 4,
  "seed": 42
}
```

## 5. Progress & Results

The worker will call back to:
- `POST /internal/jobs/<job_id>/progress` with `status="running"`, `progress=0.x`.
- `POST /internal/jobs/<job_id>/progress` with `status="succeeded"`, `metrics={...}`, `output_url="..."` upon completion.
