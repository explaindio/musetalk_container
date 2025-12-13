# CRITICAL FIX: Worker Code Issue Resolved

**Date**: 2025-12-11 (21:30 EST)  
**Status**: ✅ Deploy ASAP
**New Digest**: `sha256:b6524aee486eb8019af5016fd0b8b9a57ea41f4fe3fdab8df0fa6f67471f658b`

---

## Problem Discovered

All workers (100%) were returning the **legacy response format** despite the new error reporting code being added. Analysis showed:
- Workers were returning flat `GENERATION_TIME_SEC` fields instead of nested `metrics` object
- Orchestrator receiving incompatible data → empty/null output records  
- 0% of jobs showing new structured metrics

---

## Root Cause

The `/generate` endpoint in `worker_app/main.py` had **BOTH** the new error handling code AND legacy response code:

- **Lines 938-1074**: New try/except structure with `MediaError`, `ProcessingError` handling ✅
- **Lines 1085-1129**: Legacy return statement with old response format ❌

The issue: If no exceptions were raised (successful job), execution fell through to the legacy return statement at the bottom, returning the old format.

---

## Fix Applied

**Deleted lines 1085-1129** containing:
```python
# DELETED - Legacy code
return GenerateResponse(
    status="ok",
    b2_bucket=b2_bucket,
    b2_file_name=b2_file_name,
    metrics=metrics,  # Flat metrics, not nested
)
```

Now the endpoint **only** returns via the new structured exception handlers:
- Success: Returns `output_url` + nested `metrics` with `stage_times`
- Media Error (422): Returns structured JSON with `error_type: "media_error"`
- Processing Error (500): Returns structured JSON with `error_type: "processing_error"` + `stack_trace`

---

## Deployment Steps

### All Workers MUST Be Updated Immediately

1. **Stop old container:**
   ```bash
   docker rm -f <container-name>
   ```

2. **Pull corrected image:**
   ```bash
   docker pull explaindio/musetalk-queue-worker:progress
   ```

3. **Verify correct digest:**
   ```bash
   docker inspect explaindio/musetalk-queue-worker:progress | grep "sha256:b6524aee"
   ```
   Should return the new digest starting with `b6524aee`.

4. **Start with auto-restart:**
   ```bash
   docker run --gpus all -d \
     --name <container-name> \
     --restart unless-stopped \
     --network bridge \
     --env-file .env \
     -e BUFFER_WORKER_ID=<worker-id> \
     -e ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
     -e BUFFER_ORCHESTRATOR_BASE_URL=https://api.avatargen.online \
     explaindio/musetalk-queue-worker:progress
   ```

---

## Verification

After workers restart, successful jobs should return:
```json
{
  "status": "success",
  "output_url": "https://f000.backblazeb2.com/file/...",
  "metrics": {
    "stage_times": {
      "download": 0.37,
      "validation": 0.12,
      "inference": 99.33,
      "upload": 1.13
    },
    "total_time": 100.96,
    "GENERATION_TIME_SEC": 11.0,
    ...
  }
}
```

**Key indicators of success:**
- `output_url` field present (not `b2_bucket` + `b2_file_name`)
- `metrics.stage_times` object present
- `metrics.total_time` present

---

**URGENT**: Deploy to all workers immediately to restore proper orchestrator compatibility.
