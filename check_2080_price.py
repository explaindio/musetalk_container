from salad_cloud_sdk import SaladCloudSdk
import json

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
ORG_NAME = "explaindiolls"

sdk = SaladCloudSdk(api_key=API_KEY)

try:
    # List all GPU classes
    result = sdk.organization_data.list_gpu_classes(organization_name=ORG_NAME)
    
    print("Searching for RTX 2080...")
    print("=" * 80)
    
    if hasattr(result, 'items'):
        rtx_2080_found = False
        for gpu in result.items:
            if '2080' in gpu.name.upper():
                rtx_2080_found = True
                print(f"\nGPU Name: {gpu.name}")
                print(f"GPU ID: {gpu.id_}")
                if hasattr(gpu, 'prices') and gpu.prices:
                    for price in gpu.prices:
                        priority = getattr(price, 'priority', 'N/A')
                        price_val = getattr(price, 'price', 'N/A')
                        print(f"  Priority: {priority}")
                        print(f"  Price: ${price_val}/hour")
                else:
                    print(f"  No pricing info available")
                print("-" * 80)
        
        if not rtx_2080_found:
            print("\nNo RTX 2080 found. Showing all available RTX 20-series GPUs:")
            print("=" * 80)
            for gpu in result.items:
                if '20' in gpu.name.upper() and 'RTX' in gpu.name.upper():
                    print(f"{gpu.name} (ID: {gpu.id_})")
                    if hasattr(gpu, 'prices') and gpu.prices:
                        for price in gpu.prices:
                            priority = getattr(price, 'priority', 'N/A')
                            price_val = getattr(price, 'price', 'N/A')
                            print(f"  {priority}: ${price_val}/hour")
                
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
