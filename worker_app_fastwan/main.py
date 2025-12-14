import os
import logging
import asyncio
import traceback
import time
import threading
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from fastapi import FastAPI, BackgroundTasks
import httpx

from .param_model import GenerateRequest, GenerateResponse
from .inference import FastWanInference
from .utils import download_to_temp, upload_to_b2, ProcessingError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model instance
inference_engine = FastWanInference()

# ============================================================================
# Buffer Mode Helpers
# ============================================================================

def _get_buffer_config() -> Dict[str, str]:
    """Get buffer mode configuration from environment."""
    return {
        "orchestrator_url": os.environ.get("ORCHESTRATOR_BASE_URL", ""),
        "api_key": os.environ.get("INTERNAL_API_KEY", ""),
        "worker_id": os.environ.get("BUFFER_WORKER_ID", ""),
        "gpu_class": os.environ.get("GPU_CLASS", "Unknown GPU"),
    }

def _send_heartbeat(config: Dict[str, str], status: str = "idle") -> bool:
    """Send heartbeat to orchestrator. Returns True on success."""
    if not config["orchestrator_url"] or not config["worker_id"]:
        return False
    
    url = f"{config['orchestrator_url'].rstrip('/')}/internal/buffer/workers/{config['worker_id']}/heartbeat"
    headers = {"X-Internal-API-Key": config["api_key"]}
    payload = {
        "status": status,
        "gpu_class": config["gpu_class"],
        "capacity": 1,
    }
    
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Heartbeat failed: {e}")
        return False

def _claim_job(config: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Claim a job from the orchestrator. Returns job dict or None."""
    if not config["orchestrator_url"] or not config["worker_id"]:
        return None
    
    url = f"{config['orchestrator_url'].rstrip('/')}/internal/buffer/jobs/claim"
    headers = {"X-Internal-API-Key": config["api_key"]}
    payload = {"worker_id": config["worker_id"]}
    
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("job")  # Returns None if no job available
    except Exception as e:
        logger.warning(f"Job claim failed: {e}")
        return None

def _report_job_status(
    config: Dict[str, str],
    buffer_job_id: str,
    status: str,
    output_url: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
) -> bool:
    """Report job completion/failure to orchestrator."""
    if not config["orchestrator_url"]:
        return False
    
    url = f"{config['orchestrator_url'].rstrip('/')}/internal/buffer/jobs/{buffer_job_id}/status"
    headers = {"X-Internal-API-Key": config["api_key"]}
    payload: Dict[str, Any] = {"status": status}
    if output_url:
        payload["output_url"] = output_url
    if metrics:
        payload["metrics"] = metrics
    if error:
        payload["error"] = error
    
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to report job status: {e}")
        return False

def _send_progress_update_buffer(config: Dict[str, str], job_id: str, **kwargs):
    """Send progress update for videogen jobs."""
    if not config["orchestrator_url"]:
        return
    
    url = f"{config['orchestrator_url'].rstrip('/')}/internal/videogen/jobs/{job_id}/progress"
    headers = {"X-Internal-API-Key": config["api_key"]}
    
    try:
        resp = httpx.post(url, json=kwargs, headers=headers, timeout=5.0)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Progress update failed: {e}")

def _process_buffer_job(job: Dict[str, Any], config: Dict[str, str]) -> None:
    """Process a single buffer job."""
    buffer_job_id = job.get("buffer_job_id")
    musetalk_job_id = job.get("musetalk_job_id")  # Generic job ID
    image_url = job.get("image_url")
    prompt = job.get("prompt", "")
    num_frames = job.get("num_frames", 121)
    width = job.get("width", 720)
    height = job.get("height", 1280)
    steps = job.get("steps", 4)
    seed = job.get("seed", 42)
    
    logger.info(f"Processing buffer job {buffer_job_id} (job_id={musetalk_job_id})")
    
    try:
        # 1. Download input
        _send_progress_update_buffer(config, musetalk_job_id, status="running", phase="downloading", progress=0.1)
        
        import tempfile
        fd, input_image_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        
        # Simple sync download
        resp = httpx.get(image_url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
        with open(input_image_path, "wb") as f:
            f.write(resp.content)
        
        # 2. Run inference
        _send_progress_update_buffer(config, musetalk_job_id, status="running", phase="inference", progress=0.2)
        
        output_video_path = f"/tmp/{musetalk_job_id}_output.mp4"
        
        metrics = inference_engine.generate(
            image_path=input_image_path,
            prompt=prompt,
            num_frames=num_frames,
            width=width,
            height=height,
            steps=steps,
            seed=seed,
            guidance_scale=1.0,
            output_path=output_video_path
        )
        
        # 3. Upload result
        _send_progress_update_buffer(config, musetalk_job_id, status="running", phase="uploading", progress=0.9)
        
        bucket, file_name = upload_to_b2(output_video_path, musetalk_job_id)
        output_url = f"https://f005.backblazeb2.com/file/{bucket}/{file_name}"
        
        # 4. Report success
        _report_job_status(config, buffer_job_id, "succeeded", output_url=output_url, metrics=metrics)
        _send_progress_update_buffer(config, musetalk_job_id, status="succeeded", progress=1.0, output_url=output_url)
        
        # Cleanup
        try:
            os.remove(input_image_path)
            os.remove(output_video_path)
        except:
            pass
        
        logger.info(f"Buffer job {buffer_job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Buffer job {buffer_job_id} failed: {traceback.format_exc()}")
        _report_job_status(config, buffer_job_id, "failed", error=str(e))
        _send_progress_update_buffer(config, musetalk_job_id, status="failed", error=str(e))

def _buffer_worker_loop():
    """Main loop for buffer mode: heartbeat + job claim."""
    config = _get_buffer_config()
    
    if not config["orchestrator_url"] or not config["worker_id"]:
        logger.error("Buffer mode requires ORCHESTRATOR_BASE_URL and BUFFER_WORKER_ID")
        return
    
    logger.info(f"Starting buffer worker loop: worker_id={config['worker_id']}, gpu={config['gpu_class']}")
    
    # Load model first
    try:
        inference_engine.load_model()
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return
    
    last_heartbeat = 0
    heartbeat_interval = 5  # seconds
    
    while True:
        try:
            now = time.time()
            
            # Send heartbeat every 5 seconds
            if now - last_heartbeat >= heartbeat_interval:
                _send_heartbeat(config, status="idle")
                last_heartbeat = now
            
            # Try to claim a job
            job = _claim_job(config)
            
            if job:
                # Mark busy
                _send_heartbeat(config, status="busy")
                
                # Process the job (synchronous)
                _process_buffer_job(job, config)
                
                # Back to idle
                _send_heartbeat(config, status="idle")
                last_heartbeat = time.time()
            else:
                # No job available, sleep briefly
                time.sleep(2)
                
        except Exception as e:
            logger.error(f"Buffer loop error: {e}")
            time.sleep(5)

# ============================================================================
# Queue Mode (FastAPI for Salad)
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load model on startup
    try:
        inference_engine.load_model()
    except Exception as e:
        logger.error(f"Failed to load model on startup: {e}")
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health():
    ready = inference_engine.generator is not None
    return {"status": "ok", "model_loaded": ready}

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Queue mode endpoint - called by Salad worker binary."""
    from .utils import send_progress_update
    
    job_id = request.musetalk_job_id
    logger.info(f"Received job {job_id}")
    
    try:
        # 1. Download Input Image
        logger.info(f"Downloading image from {request.image_url}")
        send_progress_update(job_id, status="running", phase="downloading", progress=0.1)
        
        input_image_path = await download_to_temp(str(request.image_url), ".png")
        
        # 2. Run Inference
        logger.info("Running inference...")
        send_progress_update(job_id, status="running", phase="inference", progress=0.2)
        
        output_video_path = f"/tmp/{job_id}_output.mp4"
        
        loop = asyncio.get_running_loop()
        metrics = await loop.run_in_executor(
            None,
            lambda: inference_engine.generate(
                image_path=input_image_path,
                prompt=request.prompt,
                num_frames=request.num_frames,
                width=request.width,
                height=request.height,
                steps=request.steps,
                seed=request.seed,
                guidance_scale=request.guidance_scale,
                output_path=output_video_path
            )
        )
        
        # 3. Upload Result
        logger.info("Uploading result...")
        send_progress_update(job_id, status="running", phase="uploading", progress=0.9)
        
        bucket, file_name = await loop.run_in_executor(
            None,
            lambda: upload_to_b2(output_video_path, job_id)
        )
        
        output_url = f"https://f005.backblazeb2.com/file/{bucket}/{file_name}"
        
        # Cleanup
        try:
            os.remove(input_image_path)
            os.remove(output_video_path)
        except:
            pass
            
        return GenerateResponse(
            status="succeeded",
            output_url=output_url,
            metrics=metrics
        )

    except Exception as e:
        logger.error(f"Job {job_id} failed: {traceback.format_exc()}")
        send_progress_update(job_id, status="failed", error=str(e))
        return GenerateResponse(
            status="failed",
            error=str(e)
        )

# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Main entry point - checks WORKER_MODE and starts appropriate mode."""
    worker_mode = os.environ.get("WORKER_MODE", "queue").lower()
    
    if worker_mode == "buffer":
        logger.info("Starting in BUFFER mode")
        _buffer_worker_loop()
    else:
        logger.info("Starting in QUEUE mode (Salad)")
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
