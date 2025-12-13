# Orchestrator Integration Guide - ACTUAL Worker Response Format

**Version**: 1.2 (CORRECTED)  
**Date**: 2025-12-11  
**Status**: Production Format

---

## Critical Summary for Orchestrator Team

The worker returns a **hybrid format** that contains:
1. ✅ **Legacy fields** at top level of `metrics` (`GENERATION_TIME_SEC`, `SCRIPT_WALL_TIME_SEC`, etc.)
2. ✅ **New nested fields** also in `metrics` (`stage_times`, `total_time`, `gpu_class`)

**This is BY DESIGN for backward compatibility.**

---

## Actual Success Response (200 OK)

```json
{
  "status": "success",
  "output_url": "https://f000.backblazeb2.com/file/talking-avatar/avatar/outputs/job-123.mp4",
  "musetalk_job_id": "job-123",
  "metrics": {
    "GENERATION_TIME_SEC": 11.019,
    "SCRIPT_WALL_TIME_SEC": 80.828,
    "PEAK_VRAM_MIB": 7064.74,
    "PEAK_RAM_KB": null,
    "gpu_class": "RTX-3090",
    "stage_times": {
      "download": 0.37,
      "validation": 0.12,
      "inference": 99.33,
      "upload": 1.13
    },
    "total_time": 100.96
  }
}
```

### Fields Explanation

#### Top-Level Fields
- `status`: Always `"success"` for 200 OK
- `output_url`: Direct HTTPS URL to the B2 file
- `musetalk_job_id`: The job ID from the request

#### Metrics Object (Hybrid Format)
The `metrics` object is a **flat dictionary** containing BOTH legacy and new fields:

**Legacy Fields** (from MuseTalk inference script):
- `GENERATION_TIME_SEC`: Time spent in model inference loop
- `SCRIPT_WALL_TIME_SEC`: Total wall time of inference script
- `PEAK_VRAM_MIB`: Peak VRAM usage in MiB
- `PEAK_RAM_KB`: Peak RAM usage in KB (may be `null`)

**New Fields** (added by worker):
- `gpu_class`: GPU type (e.g., "RTX-3090", "unknown")
- `stage_times`: **Object** with timing for each stage:
  - `download`: Time to download inputs
  - `validation`: Time to validate with ffprobe
  - `inference`: Time for MuseTalk processing
  - `upload`: Time to upload to B2
- `total_time`: Total job time from start to finish

---

## Orchestrator Parsing Logic

### Recommended Code (Python)

```python
response = worker_post("/generate", json=job_payload)

if response.status_code == 200:
    data = response.json()
    
    # Extract fields
    output_url = data["output_url"]
    job_id = data["musetalk_job_id"]
    metrics = data["metrics"]
    
    # Parse new structured fields
    stage_times = metrics.get("stage_times", {})
    total_time = metrics.get("total_time")
    gpu_class = metrics.get("gpu_class")
    
    # Parse legacy fields (if needed)
    generation_time = metrics.get("GENERATION_TIME_SEC")
    peak_vram = metrics.get("PEAK_VRAM_MIB")
    
    # Store to database
    save_job_result(
        job_id=job_id,
        output_url=output_url,
        total_time=total_time,
        stage_times_json=json.dumps(stage_times),
        gpu_class=gpu_class,
        raw_metrics=json.dumps(metrics)  # Store full metrics for analysis
    )
```

### Database Schema Recommendation

```sql
CREATE TABLE job_results (
    job_id VARCHAR PRIMARY KEY,
    output_url TEXT NOT NULL,
    total_time_sec FLOAT,
    gpu_class VARCHAR,
    stage_times_json JSONB,  -- {"download": 0.37, "validation": 0.12, ...}
    raw_metrics JSONB,       -- Full metrics object for debugging
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Error Responses (422 / 500)

Error format is unchanged from spec v1.1:

### Input Error (422)
```json
{
  "status": "failed",
  "error_type": "media_error",
  "error_message": "Download failed: 404 Not Found",
  "stage": "download",
  "details": {"url": "...", "status_code": 404},
  "retryable": false,
 "stage_times": {}
}
```

### Worker Error (500)
```json
{
  "status": "failed",
  "error_type": "processing_error",
  "error_message": "Inference failed: CUDA out of memory",
  "stage": "inference",
  "details": {"is_oom": true},
  "stack_trace": "Traceback...",
  "retryable": true,
  "stage_times": {"download": 0.37, "validation": 0.12}
}
```

---

## Migration Notes

If orchestrator was expecting:
- ❌ `b2_bucket` + `b2_file_name` fields → **These are removed**. Use `output_url` instead.
- ❌ Pure nested `metrics` object → **Metrics is hybrid**. Contains both flat and nested fields.

---

**Deploy Date**: 2025-12-11  
**Image Digest**: `sha256:b6524aee486eb8019af5016fd0b8b9a57ea41f4fe3fdab8df0fa6f67471f658b`
