# Worker API Error Reporting Specification

**Version**: 1.1  
**Date**: 2025-12-11  
**Status**: Ready for Implementation

This document defines the interface contract for the MuseTalk Worker's new structured error reporting. The orchestrator must be updated to parse these responses to properly diagnose failures and handle retries.

---

## 1. Response Structure

The worker now returns structured JSON for **all** outcomes.

### ✅ Success Response (200 OK)

Returned when the job completes successfully.

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

**Important Notes:**
- The `metrics` object contains **BOTH** legacy flat fields (`GENERATION_TIME_SEC`, etc.) **AND** new nested fields (`stage_times`, `total_time`)
- This hybrid format maintains backward compatibility while adding new structured data
- Orchestrator should parse `metrics.stage_times` and `metrics.total_time` for new reporting
- Legacy fields (`GENERATION_TIME_SEC`, etc.) are still present for compatibility

### ❌ Error Response Format

Returned for both Input Errors (422) and Worker Errors (500).

```json
{
  "status": "failed",
  "error_type": "media_error",      // or "processing_error" / "unknown_error"
  "error_message": "Description of what went wrong",
  "stage": "download",              // Where it failed
  "details": {                      // Context-specific debugging info
    "url": "https://...",
    "status_code": 404,
    "timeout_seconds": 30
  },
  "stack_trace": "Traceback...",    // Only for 500 errors (optional)
  "retryable": false,               // Whether orchestrator should retry
  "stage_times": { ... }            // Timing info up to failure
}
```

---

## 2. HTTP Status Codes

| Status Code | Error Type | Description | Action |
|:-----------:|:----------:|:------------|:-------|
| **200** | `success` | Job completed successfully. | Store result. |
| **422** | `media_error` | **Input/Media Failure**. The worker is healthy, but the input (URL/file) is invalid. | **DO NOT RETRY** on same worker. Report failure to user immediately. |
| **500** | `processing_error` | **Worker/System Failure**. The worker ran into a runtime issue (GPU OOM, crash, disk full). | **RETRY** on a different worker (if `retryable: true`) or fail job. |

---

## 3. Error Types & Stages

### Error Types (`error_type`)

1.  **`media_error`** (422)
    *   Bad/expired URLs
    *   Download timeouts/failures
    *   Corrupt media files
    *   Unsupported codecs/formats
    *   Constraints check failure (e.g. file too small)

2.  **`processing_error`** (500)
    *   CUDA / GPU errors (OOM)
    *   Model loading failures
    *   Inference process crashes
    *   B2 upload failures (infrastructure issues)

### Stages (`stage`)

| Stage | Description |
|:------|:------------|
| `download` | Downloading video/audio inputs from URLs. |
| `validation` | Checking file integrity, format, and constraints (ffprobe). |
| `preprocessing` | Preparing inputs for model (resampling, face detection). |
| `inference` | Running the MuseTalk neural network model. |
| `postprocessing` | Encoding final video output. |
| `upload` | Uploading result to Backblaze B2. |
| `unknown` | Catch-all for unexpected unhandled exceptions. |

---

## 4. Integration Guide

### Recommended Orchestrator Handling Logic (Pseudocode)

```python
response = worker.post("/generate", json=payload)

if response.status_code == 200:
    # Success
    data = response.json()
    save_result(data["output_url"], data["metrics"])

elif response.status_code == 422:
    # Input Error - DO NOT RETRY
    error_data = response.json()
    log_failure(
        reason="Invalid Input",
        details=error_data["details"],
        user_message=error_data["error_message"]
    )
    mark_job_failed(job_id, error=error_data["error_message"])

elif response.status_code == 500:
    # Worker Error
    error_data = response.json()
    
    if error_data.get("retryable", False) and attempts < max_retries:
        # Retry on another worker (e.g. OOM, network blip)
        log_retry(reason=error_data["error_message"], stage=error_data["stage"])
        requeue_job(job_id)
    else:
        # Hard failure or max retries exceeded
        log_failure(
            reason="Worker Failure",
            stack_trace=error_data.get("stack_trace")
        )
        mark_job_failed(job_id, error="Internal processing error")
```

---

## 5. Example Scenarios

### Scenario A: Expired/Bad URL

**Response:**
```json
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "status": "failed",
  "error_type": "media_error",
  "error_message": "Download failed: 404 Not Found",
  "stage": "download",
  "details": {
    "url": "https://files.catbox.moe/expired.mp4",
    "status_code": 404
  },
  "retryable": false
}
```

### Scenario B: Corrupt Video File

**Response:**
```json
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "status": "failed",
  "error_type": "media_error",
  "error_message": "Invalid video file: ffprobe failed",
  "stage": "validation",
  "details": {
    "path": "/tmp/tmp123.mp4",
    "ffprobe_stderr": "[mov,mp4,m4a,3gp,3g2,mj2 @ 0x...] moov atom not found"
  },
  "retryable": false
}
```

### Scenario C: GPU Out of Memory

**Response:**
```json
HTTP/1.1 500 Internal Server Error
Content-Type: application/json

{
  "status": "failed",
  "error_type": "processing_error",
  "error_message": "Inference failed: CUDA out of memory",
  "stage": "inference",
  "details": {
    "gpu_memory_allocated": "23.5 GB",
    "frame_number": 450
  },
  "stack_trace": "Traceback (most recent call last):\n  File \"inference.py\", line 120...",
  "retryable": true
}
```
