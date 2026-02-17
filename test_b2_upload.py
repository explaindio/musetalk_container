import os
import sys
from b2sdk.v2 import B2Api, InMemoryAccountInfo

def test_upload():
    print("Testing B2 Upload...", flush=True)
    
    bucket_name = os.environ.get("B2_BUCKET_NAME")
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")
    
    print(f"Bucket: {bucket_name}", flush=True)
    print(f"Key ID: {key_id[:4]}..." if key_id else "Key ID: None", flush=True)
    
    if not all([bucket_name, key_id, app_key]):
        print("Missing credentials!", flush=True)
        return

    try:
        info = InMemoryAccountInfo()
        b2_api = B2Api(info)
        print("Authorizing...", flush=True)
        b2_api.authorize_account("production", key_id, app_key)
        print("Authorized.", flush=True)
        
        print(f"Getting bucket {bucket_name}...", flush=True)
        bucket = b2_api.get_bucket_by_name(bucket_name)
        print("Got bucket.", flush=True)
        
        # Create dummy file
        with open("test_upload.txt", "w") as f:
            f.write("test content")
            
        file_name = "test_upload_debug.txt"
        print(f"Uploading to {file_name}...", flush=True)
        
        bucket.upload_local_file(
            local_file="test_upload.txt",
            file_name=file_name,
        )
        print("Upload SUCCESS!", flush=True)

    except Exception as e:
        print(f"Upload FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_upload()
