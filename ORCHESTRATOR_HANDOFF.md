# 🚨 URGENT: MUSKE_TALK_WORKER REDEPLOYMENT REQUIRED

### **CONTEXT**
Critical updates have been pushed to the Docker images (`explaindio/musetalk-queue-worker:progress` and `explaindio/musetalk-worker:vast-v1`). These updates fix a heartbeat timeout crash and update the Orchestrator URL.

### **ACTION REQUIRED: SALAD CONTAINER GROUPS**
You **MUST** perform a full **REDEPLOY/RESTART** of all Salad Container Groups running MuseTalk.
Simply "updating variables" is NOT enough. The container must be destroyed and recreated to pull the new image digest `sha256:5eddcc...`.

**Step-by-Step for Salad:**
1.  **STOP** the Container Group.
2.  **EDIT** Configuration:
    *   **Shared Memory Size**: Set to **8192 MB (8GB)**. *<-- THIS IS CRITICAL TO PREVENT CRASHES*
    *   **Environment Variable**: Ensure `ORCHESTRATOR_BASE_URL` is `https://orch.avatargen.online`.
3.  **START** the Container Group.

### **ACTION REQUIRED: VAST.AI INSTANCES**
1.  **DESTROY** existing instances (the "shim" or startup script needs to be replaced).
2.  **CREATE** new instances using image: `explaindio/musetalk-worker:vast-v1`.
3.  **VERIFY** `ORCHESTRATOR_BASE_URL=https://orch.avatargen.online`.

---
**VERIFICATION**
If you see `[buffer_worker_loop_error]` in the logs WITHOUT a python traceback, the worker is running OLD CODE.
If you see crashes without an error message, shared memory is likely still 64MB. Set it to 8GB.
