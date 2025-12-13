# Handoff: MuseTalk + FastWan Worker Repo

## Current State (Dec 13, 2025)

This repository (`/home/a/musetalk`) now manages **two distinct worker types** for the `api.avatargen.online` platform.

### 1. MuseTalk Worker (Legacy/Stable)
- **Role:** Talking Head Avatar Generation.
- **Hardware:** RTX 3090/4090/A6000.
- **Run Modes:** Buffer (Paused) & Salad.
- **Docs:** `DOCS_WORKER_MUSETALK.md`

### 2. FastWan Worker (New/Dev - CRITICAL ISSUE)
- **Role:** Image-to-Video Generation (FastWan 2.2).
- **Hardware:** RTX 5090 (Blackwell).
- **Status:** **DEBUGGING CRASH ON 5090**
- **Docs:** `DOCS_WORKER_FASTWAN.md`

## 🚨 Critical Issue: RTX 5090 (Blackwell) Support
**Date:** Dec 13, 2025
**Symptom:** Worker on Salad (RTX 5090) crashed with:
`RuntimeError: CUDA error: no kernel image is available for execution on the device`
Logs indicate the installed PyTorch (nightly) only supported up to `sm_90` (Hopper), but 5090 is `sm_120`.

**Actions Taken:**
1.  Modified `Dockerfile.fastwan` to **force reinstall** PyTorch Nightly `cu128`.
2.  Added `ENV TORCH_CUDA_ARCH_LIST="9.0;10.0;12.0"`.
3.  Removed `pip cache purge` (caused build error).
4.  Rebuild triggered (Image: `explaindio/fastwan-worker:v1`).

**Next Steps for Agent/AI:**
1.  **Verify Build:** Check if `docker build` (ID `a27d1d5a...`) succeeded.
2.  **Push:** Run `docker push explaindio/fastwan-worker:v1`.
3.  **Test:** If it crashes again with `no kernel image`, it means the **binary wheels for nightly/cu128 DO NOT yet contain sm_120 kernels**.
    - **Fallback Plan:** You must compile PyTorch from source (very slow) OR find a specific NVIDIA container tag (e.g. `nvcr.io/nvidia/pytorch:24.12-py3` if available/beta) that explicitly supports Blackwell.

## Key Files Map
| File | Purpose |
| :--- | :--- |
| `Dockerfile.fastwan` | The focus of debugging. |
| `worker_app_fastwan` | The python code (seems fine, error is driver/framework level). |
