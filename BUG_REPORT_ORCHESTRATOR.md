# 🐛 Orchestrator Bug Report - Unified Worker Integration

**Date:** 2026-01-01 21:40 EST
**Reporter:** Container Builder (Antigravity)
**Affected Component:** Orchestrator API - Main Worker Endpoints

---

## Issue Summary

The unified worker container (`explaindio/musetalk-worker:unified-v1`) is running but cannot connect to the orchestrator. The new `/internal/main/*` endpoints are returning errors.

---

## Observed Behavior

### Error 1: HTTP 404 Not Found
```
[claim_job] HTTP 404: {"detail":"Not Found"}
```
**Endpoint:** `POST /internal/main/jobs/claim`

### Error 2: HTTP 502 Bad Gateway
```
[claim_job] HTTP 502: (Cloudflare error page)
```
**Endpoint:** `POST /internal/main/jobs/claim`

---

## Worker Configuration (Verified Working)

```
Worker ID:    buffer-local-unified-1
Worker Type:  main
Provider:     local
GPU Class:    RTX-local-buffer
Orchestrator: https://orch.avatargen.online
Poll Interval: 5s
```

---

## Expected Endpoints (per Verification Doc)

The orchestrator should have these endpoints:

| Endpoint | Method | Status |
|----------|--------|--------|
| `/internal/main/workers/{worker_id}/heartbeat` | POST | ❓ Unknown |
| `/internal/main/jobs/claim` | POST | ❌ 404/502 |
| `/internal/jobs/{job_id}/progress` | POST | ✅ Existing |

---

## What Needs to Be Fixed

1. **Deploy the `/internal/main/*` endpoints** - The 404 suggests they're not live
2. **Restart orchestrator** - The 502 suggests the service is down/restarting
3. **Verify Cloudflare** - 502 could be Cloudflare<->origin connection issue

---

## Test Commands

Once fixed, the orchestrator should pass these tests:

```bash
# 1. Test heartbeat
curl -X POST https://orch.avatargen.online/internal/main/workers/test-worker/heartbeat \
  -H "X-Internal-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status": "idle", "provider": "vast", "gpu_class": "RTX_3060", "worker_type": "transient"}'
# Expected: {"detail":"ok"}

# 2. Test job claim
curl -X POST https://orch.avatargen.online/internal/main/jobs/claim \
  -H "X-Internal-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"worker_id": "test-worker", "worker_type": "transient", "gpu_class": "RTX_3060"}'
# Expected: {"job": null, "error": null}
```

---

## Worker Status

The unified worker container is running and will automatically connect once endpoints are available:
```bash
docker logs buffer-local-unified-1 -f  # Stream logs
```
