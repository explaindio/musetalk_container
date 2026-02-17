from salad_cloud_sdk import SaladCloudSdk
import json

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
ORG_NAME = "explaindiolls"
PROJECT_NAME = "project2"

sdk = SaladCloudSdk(api_key=API_KEY)

try:
    result = sdk.container_groups.list_container_groups(
        organization_name=ORG_NAME,
        project_name=PROJECT_NAME
    )
    
    if hasattr(result, 'items'):
        for group in result.items:
            print(f"\n{'='*70}")
            print(f"Name: {group.name}")
            print(f"Display Name: {group.display_name}")
            print(f"Status: {group.current_state.status}")
            print(f"Description: {group.current_state.description}")
            print(f"Replicas: {group.replicas}")
            print(f"Image Hash: {group.container.hash}")
            print(f"Running: {group.current_state.instance_status_counts.running_count}")
            print(f"Creating: {group.current_state.instance_status_counts.creating_count}")
            print(f"Allocating: {group.current_state.instance_status_counts.allocating_count}")
            print(f"Stopping: {group.current_state.instance_status_counts.stopping_count}")
    else:
        print(result)
        
except Exception as e:
    print(f"Error: {e}")
