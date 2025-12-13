# FastWan 2.2 Worker Setup (Salad)

This guide explains how to build the new FastWan 2.2 worker image and configure the orchestrator to use it.

## 1. Description
The **FastWan Worker** generates videos from a single image + prompt using the **FastWan 2.2** model (Hao AI Lab).
It is optimized for **NVIDIA RTX 5090** (Blackwell) GPUs but also works on A100/H100.
It runs on **Salad** via the HTTP Job Queue.

## 2. Build and Push Docker Image

Run these commands on a machine with Docker (can be local or VPS):

```bash
# 1. Build the image
docker build -f Dockerfile.fastwan -t explaindio/fastwan-worker:v1 .

# 2. Push to Docker Hub
docker push explaindio/fastwan-worker:v1
```

## 3. Orchestrator Configuration (VPS)

You need to update the orchestrator (API) to handle this new worker type.

### A. Add new GPU Class
Insert into `gpu_classes` table:
- **Name:** `RTX-5090-FastWan`
- **VRAM:** 32GB (min)
- **Hourly Price:** (Set your Salad price limit, e.g., $0.60)

### B. Add new Queue
Create a new Salad Job Queue via the Salad Portal or API:
- **Queue Name:** `fastwan-queue`
- **Container Image:** `explaindio/fastwan-worker:v1`
- **Resources:**
    - GPU: RTX 5090 (or A100/H100)
    - RAM: 32GB+
    - vCPU: 4+
- **Environment Variables:**
    - `INTERNAL_API_KEY`: <your-secret-key>
    - `ORCHESTRATOR_BASE_URL`: `https://api.avatargen.online`
    - `B2_KEY_ID`: ...
    - `B2_APP_KEY`: ...
    - `B2_BUCKET_NAME`: ...

### C. Update Orchestrator Logic
When a client requests a FastWan generation, the orchestrator must:
1. Accept the request (new endpoint `/generate-fastwan` or flag in `/generate`).
2. Create a job record with type `fastwan`.
3. Push the job to the **FastWan Salad Queue** url (instead of MuseTalk queue).
