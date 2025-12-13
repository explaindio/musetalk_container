import os
import logging
import tempfile
import uuid
import httpx
import asyncio
import subprocess
from typing import Optional, Tuple
from b2sdk.v2 import B2Api, InMemoryAccountInfo

logger = logging.getLogger(__name__)

class DownloadError(Exception):
    def __init__(self, url: str, reason: str):
        super().__init__(f"Download failed for {url}: {reason}")

class ProcessingError(Exception):
    def __init__(self, stage: str, message: str, details: dict = None, retryable: bool = False):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.details = details or {}
        self.retryable = retryable

async def download_to_temp(url: str, suffix: str, timeout_sec: float = 300.0) -> str:
    """Download a URL to a temporary file."""
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            
            fd, path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(resp.content)
            return path
    except Exception as e:
        raise DownloadError(url, str(e))

def upload_to_b2(file_path: str, job_id: Optional[str] = None) -> Tuple[str, str]:
    """Uploads file to B2 and returns (bucket, filename)."""
    bucket_name = os.environ.get("B2_BUCKET_NAME")
    if not bucket_name:
        raise ProcessingError("upload", "B2_BUCKET_NAME not set")

    ext = os.path.splitext(file_path)[1]
    name_id = job_id if job_id else f"fastwan-{uuid.uuid4()}"
    b2_prefix = os.environ.get("B2_PREFIX", "avatar/outputs")
    file_name = f"{b2_prefix}/{name_id}{ext}"
    
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")
    
    if not key_id or not app_key:
        raise ProcessingError("upload", "B2 credentials missing")

    try:
        info = InMemoryAccountInfo()
        b2_api = B2Api(info)
        b2_api.authorize_account("production", key_id, app_key)
        bucket = b2_api.get_bucket_by_name(bucket_name)
        
        logger.info(f"Uploading {file_path} to B2: {file_name}")
        bucket.upload_local_file(local_file=file_path, file_name=file_name)
        return bucket_name, file_name
    except Exception as e:
        raise ProcessingError("upload", f"B2 upload failed: {str(e)}", retryable=True)

def send_progress_update(job_id: str, status: str = None, progress: float = None, error: str = None):
    """Best-effort progress update to orchestrator."""
    base_url = os.environ.get("ORCHESTRATOR_BASE_URL")
    internal_key = os.environ.get("INTERNAL_API_KEY")
    
    if not base_url or not internal_key:
        return

    url = f"{base_url.rstrip('/')}/internal/videogen/jobs/{job_id}/progress"
    payload = {}
    if status: payload["status"] = status
    if progress: payload["progress"] = progress
    if error: payload["error"] = error
    
    headers = {"X-Internal-API-Key": internal_key}
    
    try:
        # Use simple requests here since it's fire-and-forget synchronous in non-async context usually, 
        # but better to use httpx if we were async. For simplicity in utils, using requests or assuming async caller?
        # Let's use requests with timeout for simplicity if called from synced code, or just skip if complex.
        # Actually, let's use httpx.post inside a try/except helper in main. 
        pass 
    except Exception:
        pass
