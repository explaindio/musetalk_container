from salad_cloud_sdk import SaladCloudSdk

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
ORG_NAME = "explaindiolls"

sdk = SaladCloudSdk(api_key=API_KEY)

try:
    result = sdk.organization_data.list_gpu_classes(organization_name=ORG_NAME)
    
    print("RTX 30-series GPUs:")
    print("=" * 80)
    
    if hasattr(result, 'items'):
        for gpu in result.items:
            if '3060' in gpu.name.upper() or '3070' in gpu.name.upper() or '3080' in gpu.name.upper():
                print(f"\nGPU: {gpu.name}")
                print(f"ID: {gpu.id_}")
                if hasattr(gpu, 'prices') and gpu.prices:
                    for price in gpu.prices:
                        priority = getattr(price, 'priority', 'N/A')
                        price_val = getattr(price, 'price', 'N/A')
                        print(f"  {priority}: ${price_val}/hour")
                print("-" * 80)
                
except Exception as e:
    print(f"Error: {e}")
