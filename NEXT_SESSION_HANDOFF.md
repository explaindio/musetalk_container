# Handoff: MuseTalk + FastWan Worker Repo

## Current State (Dec 13, 2025)

This repository (`/home/a/musetalk`) now manages **two distinct worker types** for the `api.avatargen.online` platform.

### 1. MuseTalk Worker (Legacy/Stable)
- **Role:** Talking Head Avatar Generation.
- **Hardware:** RTX 3090/4090/A6000.
- **Run Modes:**
  - **Buffer Worker:** Runs locally (on this machine `left`) as `buffer-orch-local-1`. Currently **PAUSED** via Docker to stop GPU usage but persist container.
  - **Salad Worker:** Runs on ephemeral cloud nodes.
- **Docs:** `DOCS_WORKER_MUSETALK.md`

### 2. FastWan Worker (New/Beta)
- **Role:** Image-to-Video Generation (FastWan 2.2).
- **Hardware:** RTX 5090 (Blackwell) / A100.
- **Run Modes:**
  - **Salad Worker ONLY:** No local buffer worker exists (hardware limitation).
- **Docs:** `DOCS_WORKER_FASTWAN.md`
- **Integration Guide:** `FASTWAN_ORCHESTRATOR_DEV_GUIDE.md`

## Recent Actions
- **Buffer Worker (`buffer-orch-local-1`):** 
    - Reconfigured to point to `https://api.avatargen.online`.
    - Service `buffer-worker.service` created.
    - Container **PAUSED** (`docker pause buffer-orch-local-1`) per user request.
- **FastWan Worker:**
    - Created `Dockerfile.fastwan` & `worker_app_fastwan/`.
    - Implemented API (VideoGen endpoints).
    - **Actions Completed:** Built & Pushed `explaindio/fastwan-worker:v1`.
    - **Pending:** Backend developer integration (guides provided).

## Next Steps / Context for Agent
- **Do not mix up the workers.** They use different base images, different endpoints (`/internal/jobs` vs `/internal/videogen/jobs`), and different hardware.
- **This machine (`left`)** is primarily for:
    - Running the MuseTalk Buffer Worker (when resumed).
    - Developing/Building Docker images for both workers.
- **If user asks to resume buffer worker:**
    - Run `docker unpause buffer-orch-local-1`.
    - If that fails/container missing, use `/setup-buffer-worker` workflow or restart systemd service.

## Key Files Map
| File | Purpose |
| :--- | :--- |
| `Dockerfile.worker` | MuseTalk Image Definition |
| `Dockerfile.fastwan` | FastWan Image Definition |
| `worker_app/` | MuseTalk App Code |
| `worker_app_fastwan/` | FastWan App Code |
| `.agent/workflows/` | Workflows (e.g. setup buffer) |
