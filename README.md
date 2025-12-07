# MuseTalk Benchmarks on SaladCloud

This repo contains two closely related pieces:

1. A benchmarking helper to run standardized MuseTalk v1.5 inference across GPUs on SaladCloud.  
2. A new “avatar video” orchestration plane and worker service built on Salad Job Queues.

The benchmark script is still useful for GPU comparison and tuning; the orchestrator/worker are how production traffic will be served.

---

## Part 1 – Benchmarks

### Prerequisites

- Python 3.10+
- `requests` Python package (`pip install requests`)
- A SaladCloud organization and project with API access
- The benchmark image pushed to Docker Hub: `docker.io/explaindio/musetalk-salad:bench`

### Configuration

The script reads configuration from environment variables or `.env` in the repo root:

- `SALAD_API_KEY` – your SaladCloud API key.
- `SALAD_ORG_NAME` – organization name (e.g. `explaindiolls`).
- `SALAD_PROJECT_NAME` – project name (e.g. `project2`).
- `MUSETALK_BENCH_IMAGE` – optional, override the default benchmark image.

Target GPUs and their Salad GPU class IDs live in `gpu_targets.json`. Pricing for each class is fetched live from `GET /organizations/{org}/gpu-classes`.

### Running the benchmarks

Dry run (no containers started, just shows planned actions):

```bash
python bench_on_salad.py --dry-run
```

Full benchmark across all GPUs in `gpu_targets.json` (with a warmup run per GPU):

```bash
python bench_on_salad.py
```

You can skip warmup runs or adjust timeouts:

```bash
python bench_on_salad.py --no-warmup --timeout-minutes 45
```

### Benchmark Outputs

- `salad_bench_results.json` with per‑GPU metrics:
  - `GENERATION_TIME_SEC`, `SCRIPT_WALL_TIME_SEC`
  - `PEAK_VRAM_MIB`, `PEAK_RAM_KB`
  - `price_per_hour_high`, `cost_per_job`
- A tab‑separated summary printed to stdout.
- A short recommendation for:
  - **Value GPU** – lowest cost per job.
  - **Premium GPU** – fastest script wall time per job.

See `salad_musetalk_bench_results.md` for an aggregated Markdown report and design notes.

---

## Part 2 – Avatar Orchestrator + Salad Job Queue Worker

This is a new service layer that hides Salad and GPU details behind a simple HTTP API that other internal apps can call, similar in spirit to Replicate.

### High-level architecture

- **Orchestrator (FastAPI, `orchestrator/`)**
  - Exposes a small public API for submitting avatar video jobs and polling their status.
  - Talks to Salad Job Queues (queues/jobs/container groups) using an internal Salad API client.
  - Maintains an internal SQLite DB tracking jobs and queue/job snapshots for analysis.
  - Runs a background scaling loop to adjust GPU replicas based on queue pressure.

- **Worker (FastAPI, `worker_app/` + `Dockerfile.worker`)**
  - Runs inside GPU container groups on Salad.
  - Exposes `/hc` for health and `/generate` for actual work.
  - Is driven by the Salad HTTP Job Queue Worker binary; each queue job becomes a call to `/generate`.
  - Downloads input video + audio, calls MuseTalk v1.5 inference, uploads the final MP4 to Backblaze B2, and returns an HTTPS URL and metrics.

### Public API (what other apps see)

These endpoints are implemented in `orchestrator/main.py` and intentionally hide all provider/model details – they are generic “avatar video” endpoints.

- `POST /v1/avatar/jobs`

  Submit a new avatar video job.

  Request body:

  ```json
  {
    "video_url": "https://...",
    "audio_url": "https://...",
    "aspect_ratio": "9:16",
    "resolution": "720p",
    "webhook_url": "https://my-app/jobs/callback",
    "metadata": { "client_id": "abc", "request_id": "xyz" }
  }
  ```

  Response:

  ```json
  {
    "id": "<job-id>",
    "status": "queued",
    "output_url": null,
    "metrics": null,
    "error": null
  }
  ```

- `GET /v1/avatar/jobs/{id}`

  Poll the status of a job by its opaque id.

  Example response when complete:

  ```json
  {
    "id": "<job-id>",
    "status": "succeeded",
    "output_url": "https://...backblazeb2.com/file/<bucket>/musetalk/outputs/<id>.mp4",
    "metrics": {
      "generation_time_sec": 20.63,
      "script_wall_time_sec": 141.62,
      "peak_vram_mib": 917.3,
      "peak_ram_kb": 5130911
    },
    "error": null,
    "input": {
      "video_url": "https://...",
      "audio_url": "https://...",
      "aspect_ratio": "9:16",
      "resolution": "720p"
    }
  }
  ```

- `DELETE /v1/avatar/jobs/{id}`

  Request cancellation for a queued job:

  ```json
  { "detail": "Cancellation requested" }
  ```

All of these endpoints require an internal API key header `X-Internal-API-Key` (configured via `INTERNAL_API_KEY` in `.env` for local dev; in production this comes from secure env).

### Orchestrator internals (brief)

- Configuration (`orchestrator/config.py`):
  - Reads all Salad and scaling parameters from env (see `salad_musetalk_bench_results.md` for a full list).
  - Computes a scaling budget as `CURRENT_MAX_REPLICAS - ALWAYS_ON_MIN_REPLICAS_3060`.

- Salad client (`orchestrator/salad_client.py`):
  - Thin wrapper over the public Salad API:
    - GPU classes and availability.
    - Queues and queue jobs.
    - Container groups (replicas patching).

- Storage (`orchestrator/storage.py`):
  - SQLite DB storing:
    - `musetalk_jobs` (internal job tracking – name kept for historical reasons).
    - `queue_snapshots` (queue length + replicas per evaluation).
    - `job_snapshots` (job statuses over time).

- Scaling loop (`orchestrator/scaling.py`):
  - Runs periodically as a background task.
  - Tracks queue length windows (approx. 15 min / 60 min).
  - Computes jobs-per-replica metrics and applies scale-up/scale-down rules to the RTX 3080 scaling group (other tiers can be added).

### Worker internals (brief)

- `worker_app/main.py`:
  - `GET /hc` – health endpoint for Salad readiness/startup probes.
  - `POST /generate`:
    - Downloads inputs from the provided URLs.
    - Constructs a small YAML and calls `python -m scripts.inference` from the MuseTalk repo.
    - Parses stdout/stderr to extract generation time, script wall time, peak VRAM, and peak RAM.
    - Uploads the final MP4 to Backblaze B2 using `b2sdk`.
    - Writes a per-asset JSON metadata file (local sidecar, which can also be uploaded).
    - Returns `{"status": "ok", "output_video_url": "<https-url>", "metrics": {...}}`.

- `Dockerfile.worker` and `run_worker.sh`:
  - Build the worker image on top of the MuseTalk environment.
  - Download and run the Salad HTTP Job Queue Worker.
  - Start the FastAPI worker app in the same container.

### Environment configuration

See the “Configuration (.env) Reference” section in `salad_musetalk_bench_results.md` for the full list, but in short:

- Orchestrator:
  - `SALAD_API_KEY`, `SALAD_ORG_NAME`, `SALAD_PROJECT_NAME`
  - `INTERNAL_API_KEY`
  - `CURRENT_MAX_REPLICAS`, `ALWAYS_ON_MIN_REPLICAS_3060`
  - Scaling thresholds and cooldowns.
- Worker:
  - `B2_KEY_ID`, `B2_APP_KEY`, `B2_BUCKET_NAME`, `B2_PREFIX`
  - `MUSETALK_WORKDIR`, `MUSETALK_RESULT_DIR`, etc.

The orchestrator hides all provider/model details, exposing only a clean avatar-video job API to internal callers, while the worker handles MuseTalk and B2 details on the backend. 
