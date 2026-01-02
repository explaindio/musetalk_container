#!/usr/bin/env python3
"""
Submit test job to Salad FastWan worker
"""
import requests
import json
import time

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
ORG_NAME = "explaindiolls"
PROJECT_NAME = "testing-wanfast"
QUEUE_NAME = "fastwan-test-queue"

BASE_URL = f"https://api.salad.com/api/public/organizations/{ORG_NAME}/projects/{PROJECT_NAME}/queues/{QUEUE_NAME}/jobs"

headers = {
    "Salad-Api-Key": API_KEY,
    "Content-Type": "application/json"
}

job_id = f"test-job-{int(time.time())}"

payload = {
    "input": {
        "musetalk_job_id": job_id,
        "prompt": "A cinematic shot of a futuristic cyberpunk city with neon lights and flying cars, high resolution, 8k",
        "image_url": "https://images.unsplash.com/photo-1546484475-7f7bd55792da?q=80&w=2576&auto=format&fit=crop",  # Placeholder image
        "num_frames": 49,
        "width": 640,
        "height": 360,
        "steps": 20,
        "seed": 42
    },
    "metadata": {
        "test": "fastwan-v1",
        "created_at": str(time.time())
    }
}

print(f"Submitting job {job_id}...")
response = requests.post(BASE_URL, headers=headers, json=payload)

if response.status_code in [200, 201]:
    data = response.json()
    salad_job_id = data.get("id")
    print(f"Job submitted successfully!")
    print(f"Salad Job ID: {salad_job_id}")
    print(f"Input Job ID: {job_id}")
    
    # Monitor status
    print("\nMonitoring status (Ctrl+C to stop)...")
    while True:
        status_url = f"{BASE_URL}/{salad_job_id}"
        status_resp = requests.get(status_url, headers=headers)
        if status_resp.status_code == 200:
            status_data = status_resp.json()
            status = status_data.get("status")
            print(f"[{time.strftime('%H:%M:%S')}] Status: {status}")
            
            if status in ["succeeded", "failed"]:
                print("\nJob Complete!")
                print(json.dumps(status_data, indent=2))
                break
        else:
            print(f"Error checking status: {status_resp.status_code}")
            
        time.sleep(5)

else:
    print(f"Error submitting job: {response.text}")
