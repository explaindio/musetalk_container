#!/usr/bin/env python3
"""
Create FastWan container group on Salad Cloud
"""
from salad_cloud_sdk import SaladCloudSdk
from salad_cloud_sdk.models import (
    ContainerGroupCreationRequest,
    ContainerConfiguration,
    CreateContainerResourceRequirements,
    ContainerRestartPolicy,
    ContainerGroupQueueConnection,
    CreateContainerGroupNetworking,
    ContainerNetworkingProtocol
)

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
ORG_NAME = "explaindiolls"
PROJECT_NAME = "testing-wanfast"
QUEUE_NAME = "fastwan-test-queue"

# Initialize SDK
sdk = SaladCloudSdk(api_key=API_KEY, timeout=60000)

print("=" * 70)
print("CREATING FASTWAN CONTAINER GROUP")
print("=" * 70)
print()

# Create container configuration
container_config = ContainerConfiguration(
    image="explaindio/fastwan-worker:v1",
    resources=CreateContainerResourceRequirements(
        cpu=4,
        memory=32768,  # 32GB
        gpu_classes=["rtx_5090"]
    ),
    command=[],
    environment_variables={
        "WORKER_MODE": "queue"
    }
)

# Create networking configuration
networking = CreateContainerGroupNetworking(
    protocol=ContainerNetworkingProtocol.HTTP,
    port=8000,
    auth=False
)

# Create queue connection
queue_connection = ContainerGroupQueueConnection(
    path="/",
    port=8000,
    queue_name=QUEUE_NAME
)

# Create container group request
request = ContainerGroupCreationRequest(
    name="fastwan-test-worker",
    display_name="FastWan Test Worker",
    container=container_config,
    autostart_policy=True,
    restart_policy=ContainerRestartPolicy.ALWAYS,
    replicas=1,
    networking=networking,
    queue_connection=queue_connection,
    country_codes=[]
)

try:
    print("Creating container group...")
    result = sdk.container_groups.create_container_group(
        organization_name=ORG_NAME,
        project_name=PROJECT_NAME,
        container_group_creation_request=request
    )
    print(f"✓ Container group created successfully!")
    print(f"  Name: {result.name}")
    print(f"  ID: {result.id_ if hasattr(result, 'id_') else 'N/A'}")
    print()
    
    print("=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("1. Update IPC settings manually in Salad Portal:")
    print("   - ipc_mode: host")
    print("   - shm_size: 8589934592 (8GB)")
    print("2. Start the container group")
    print("3. Monitor logs for startup")
    
except Exception as e:
    print(f"✗ Error creating container group: {e}")
    import traceback
    traceback.print_exc()
