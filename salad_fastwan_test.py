#!/usr/bin/env python3
"""
Salad Cloud FastWan Worker Test Script
Creates a container group and job queue for testing FastWan on Salad.
"""
import requests
import json
import time
import sys

SALAD_API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
ORG_NAME = "explaindiolls"
PROJECT_NAME = "testing-wanfast"
BASE_URL = f"https://api.salad.com/api/public/organizations/{ORG_NAME}/projects/{PROJECT_NAME}"

headers = {
    "Salad-Api-Key": SALAD_API_KEY,
    "Content-Type": "application/json"
}

def list_container_groups():
    """List all container groups in the project."""
    url = f"{BASE_URL}/container-groups"
    response = requests.get(url, headers=headers)
    print(f"List Container Groups: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(json.dumps(data, indent=2))
        return data
    else:
        print(f"Error: {response.text}")
        return None

def list_queues():
    """List all queues in the project."""
    url = f"{BASE_URL}/queues"
    response = requests.get(url, headers=headers)
    print(f"List Queues: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(json.dumps(data, indent=2))
        return data
    else:
        print(f"Error: {response.text}")
        return None

def create_queue(queue_name="fastwan-test-queue"):
    """Create a job queue."""
    url = f"{BASE_URL}/queues"
    payload = {
        "name": queue_name,
        "display_name": "FastWan Test Queue",
        "description": "Test queue for FastWan video generation"
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"Create Queue: {response.status_code}")
    if response.status_code in [200, 201]:
        data = response.json()
        print(json.dumps(data, indent=2))
        return data
    else:
        print(f"Error: {response.text}")
        return None

def create_container_group(queue_name="fastwan-test-queue"):
    """Create a container group for FastWan worker."""
    url = f"{BASE_URL}/container-groups"
    
    payload = {
        "name": "fastwan-test-worker",
        "display_name": "FastWan Test Worker",
        "container": {
            "image": "explaindio/fastwan-worker:v1",
            "resources": {
                "cpu": 4,
                "memory": 32768,  # 32GB
                "gpu_classes": ["rtx_5090"]
            },
            "command": [],
            "environment_variables": {
                "WORKER_MODE": "queue"
            }
        },
        "autostart_policy": True,
        "restart_policy": "always",
        "replicas": 1,
        "country_codes": [],
        "networking": {
            "protocol": "http",
            "port": 8000,
            "auth": False
        },
        "liveness_probe": {
            "http": {
                "path": "/health",
                "port": 8000
            },
            "initial_delay_seconds": 30,
            "period_seconds": 10,
            "timeout_seconds": 5,
            "success_threshold": 1,
            "failure_threshold": 3
        },
        "readiness_probe": {
            "http": {
                "path": "/health",
                "port": 8000
            },
            "initial_delay_seconds": 30,
            "period_seconds": 10,
            "timeout_seconds": 5,
            "success_threshold": 1,
            "failure_threshold": 3
        },
        "queue_connection": {
            "path": "/",
            "port": 8000,
            "queue_name": queue_name
        },
        "container_gateway_enabled": True
    }
    
    response = requests.post(url, headers=headers, json=payload)
    print(f"Create Container Group: {response.status_code}")
    if response.status_code in [200, 201]:
        data = response.json()
        print(json.dumps(data, indent=2))
        return data
    else:
        print(f"Error: {response.text}")
        return None

def update_container_group_ipc(container_group_name="fastwan-test-worker"):
    """Update container group to set ipc_mode and shm_size."""
    url = f"{BASE_URL}/container-groups/{container_group_name}"
    
    # First get current config
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to get container group: {response.text}")
        return None
    
    current_config = response.json()
    
    # Update with IPC settings
    current_config["container"]["ipc_mode"] = "host"
    current_config["container"]["shm_size"] = 8589934592  # 8GB in bytes
    
    response = requests.patch(url, headers=headers, json=current_config)
    print(f"Update Container Group IPC: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(json.dumps(data, indent=2))
        return data
    else:
        print(f"Error: {response.text}")
        return None

def submit_test_job(queue_name="fastwan-test-queue"):
    """Submit a test job to the queue."""
    url = f"{BASE_URL}/queues/{queue_name}/jobs"
    
    payload = {
        "input": {
            "prompt": "A woman walking on a beach at sunset",
            "image_url": "https://example.com/test-image.jpg",
            "width": 480,
            "height": 848,
            "num_frames": 121,
            "steps": 4
        },
        "metadata": {
            "test": "salad-api-test"
        }
    }
    
    response = requests.post(url, headers=headers, json=payload)
    print(f"Submit Job: {response.status_code}")
    if response.status_code in [200, 201]:
        data = response.json()
        print(json.dumps(data, indent=2))
        return data
    else:
        print(f"Error: {response.text}")
        return None

def main():
    print("=" * 70)
    print("SALAD CLOUD FASTWAN WORKER TEST")
    print("=" * 70)
    print()
    
    # Step 1: List existing resources
    print("Step 1: Checking existing resources...")
    print("-" * 70)
    list_container_groups()
    print()
    list_queues()
    print()
    
    # Step 2: Create queue
    print("Step 2: Creating queue...")
    print("-" * 70)
    queue = create_queue()
    if not queue:
        print("Failed to create queue. Exiting.")
        sys.exit(1)
    print()
    
    # Step 3: Create container group
    print("Step 3: Creating container group...")
    print("-" * 70)
    cg = create_container_group()
    if not cg:
        print("Failed to create container group. Exiting.")
        sys.exit(1)
    print()
    
    # Step 4: Update IPC settings
    print("Step 4: Updating IPC settings (ipc_mode: host, shm_size: 8GB)...")
    print("-" * 70)
    time.sleep(2)  # Wait a bit for the container group to be created
    update_container_group_ipc()
    print()
    
    print("=" * 70)
    print("SETUP COMPLETE")
    print("=" * 70)
    print("Next steps:")
    print("1. Wait for container to start (check Salad Portal)")
    print("2. Submit a test job using submit_test_job()")
    print("3. Monitor logs in Salad Portal")

if __name__ == "__main__":
    main()
