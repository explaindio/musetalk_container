from salad_cloud_sdk import SaladCloudSdk

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
ORG_NAME = "explaindiolls"
PROJECT_NAME = "project2"

sdk = SaladCloudSdk(api_key=API_KEY)

try:
    # List container groups
    groups = sdk.container_groups.list_container_groups(
        organization_name=ORG_NAME,
        project_name=PROJECT_NAME
    )
    
    if hasattr(groups, 'items') and groups.items:
        group_name = groups.items[0].name
        print(f"Inspecting container group: {group_name}")
        print("=" * 80)
        
        # Get instances of first container group
        instances = sdk.container_groups.list_container_group_instances(
            organization_name=ORG_NAME,
            project_name=PROJECT_NAME,
            container_group_name=group_name
        )
        
        if hasattr(instances, 'items') and instances.items:
            instance = instances.items[0]
            print(f"\nInstance ID: {instance.machine_id}")
            print(f"\nAvailable attributes:")
            for attr in dir(instance):
                if not attr.startswith('_'):
                    try:
                        value = getattr(instance, attr)
                        if not callable(value):
                            print(f"  {attr}: {value}")
                    except:
                        pass
        else:
            print("No instances found")
    else:
        print("No container groups found")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
