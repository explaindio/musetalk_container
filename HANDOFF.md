# MuseTalk Worker System - Session Handoff

**Date:** January 23, 2026
**Repository:** `https://github.com/explaindio/musetalk_container`
**Docker Hub Image:** `explaindio/musetalk-worker:unified-v1`
**Digest:** `sha256:dc0984f7c4d3f196475a78f4f5b56078895c0743516a021a2227ae99610a793c`

---

## 1. Project Overview
This project manages the **GPU worker system** for MuseTalk video generation. It runs on Docker (Salad, Vast.ai, Local) and polls an orchestrator for jobs.

### Recent Major Updates
1.  **System Metrics Profiling:** Workers now report CPU, RAM, Disk, and Download Speed on startup.
2.  **Inference Optimization:**
    -   **PNG → JPEG:** Frame writes are ~40% faster.
    -   **Copy-Stream Audio:** Audio muxing is ~10x faster.
    -   **Expected Perf:** Wall time reduced from ~379s to ~200-250s.
3.  **Critical Fixes:**
    -   Fixed missing `/usr/bin/time` dependency in Docker image.
    -   Added `BATCH_SIZE` and `CONFIG_LABEL` configuration support.

---

## 2. Docker Images

| Image | Tag | Digest | Purpose |
|-------|-----|--------|---------|
| `explaindio/musetalk-worker` | `unified-v1` | `sha256:dc0984f7...` | **Production**. Contains all fixes & optimizations. |
| `explaindio/musetalk-base` | `latest` | `sha256:edb9254b...` | Base image with system deps (`ffmpeg`, `time`, etc). |

---

## 3. Local Buffer Worker

The local worker on this machine is **STOPPED** (as requested) but ready to run.

-   **Container Name:** `buffer-local-unified-1`
-   **Restore Script:** `/home/a/musetalk/restore_buffer_worker.sh`
-   **Status:** Stopped/Removed.

**To Start:**
```bash
cd /home/a/musetalk
./restore_buffer_worker.sh
```

---

## 4. Migration Guide (New Machine)

**See:** `MIGRATION.md`

To move to your new RTX 3090 machine:
1.  **Zip:** Run `cd /home/a && zip -r musetalk_full.zip musetalk/` (9GB).
2.  **Transfer:** Move zip to new machine.
3.  **Setup:** Install Docker & NVIDIA Toolkit (details in `MIGRATION.md`).
4.  **Run:** Use the startup script instructions in the guide.

---

## 5. Deployment (Orchestrator)

**Salad Deployment:**
-   **Image:** `explaindio/musetalk-worker:unified-v1`
-   **Registry Auth:** Required (Docker Hub PAT).
-   **Action:** Redeploy all container groups to pull `sha256:dc0984f7...`.

**Metrics Guide:**
-   **See:** `orchestrator_metrics_guide.md`
-   Workers now send `system_info` in heartbeat (CPU, RAM, DL Speed).
-   Backend needs to update schema to store this.

---

## 6. Key Files

| File | Purpose |
|------|---------|
| `unified_worker.py` | Main worker logic (polling, heartbeats, metrics). |
| `scripts/inference.py` | MuseTalk inference (Optimized: JPEG + Copy-Stream). |
| `Dockerfile.base` | Builds base env (Fixed: added `time` pkg). |
| `Dockerfile.unified` | Builds production worker image. |
| `MIGRATION.md` | Guide for moving to new 3090 machine. |
| `orchestrator_salad_deploy.md` | Deployment specs for Salad. |

---

## 7. Configuration (Env Vars)

| Variable | Value | Description |
|----------|-------|-------------|
| `BATCH_SIZE` | `8` (default) | Batch size for inference. Use `16` for 3090/4090. |
| `CONFIG_LABEL` | `batch8-default` | Label for metrics tracking. |
| `POLL_INTERVAL_SEC` | `5` | How often to check for jobs. |
| `ORCHESTRATOR_BASE_URL` | `...` | API endpoint. |

---

## 8. Troubleshooting

**"No such file or directory: /usr/bin/time"**
-   **Cause:** Missing dependency in old image.
-   **Fix:** Resolved in `sha256:dc0984f7...`. Redeploy workers.

**Slow Post-Processing**
-   **Cause:** PNG writes and re-encoding.
-   **Fix:** Resolved in `unified-v1`. Now uses JPEG and stream copy.

**Container Not Starting**
-   Check `docker logs <container_name>`.
-   Verify `.env` file exists with API keys.
-   Ensure GPU drivers are active (`nvidia-smi`).
