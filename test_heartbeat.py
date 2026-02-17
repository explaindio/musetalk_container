import httpx
import os
import sys

# Configuration matches the worker environment
ORCH_URL = "https://orch.avatargen.online"
# This key was confirmed in previous steps
API_KEY = "02cba7ae048ef8ae1a877f4673fe449ef7c0991a49b07916b84a2e04dc3b0716"
WORKER_ID = "test-simulation-host"
HEADERS = {"X-Internal-API-Key": API_KEY, "Content-Type": "application/json"}

PAYLOAD = {
    "status": "idle",
    "current_job_id": None,
    "provider": "local_test",
    "gpu_class": "test_gpu",
    "worker_type": "test",
    "system_info": {
        "cpu_cores_physical": 4,
        "cpu_cores_logical": 8,
        "ram_total_gb": 16.0,
        "ram_available_gb": 8.0,
        "disk_total_gb": 100.0,
        "disk_free_gb": 50.0,
        "download_speed_mbps": 100.0
    },
}

def test_heartbeat(use_http2: bool):
    print(f"\n--- Testing with http2={use_http2} ---")
    try:
        with httpx.Client(timeout=10.0, http2=use_http2) as client:
            resp = client.post(
                f"{ORCH_URL}/internal/main/workers/{WORKER_ID}/heartbeat",
                json=PAYLOAD,
                headers=HEADERS
            )
            print(f"Status Code: {resp.status_code}")
            print(f"Protocol: {resp.http_version}")
            print(f"Response: {resp.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Running Smoke Test (Host Machine)")
    
    # Test 1: HTTP/1.1 (Current Worker Config)
    test_heartbeat(use_http2=False)

    # Test 2: HTTP/2 (Proposed Fix)
    test_heartbeat(use_http2=True)
