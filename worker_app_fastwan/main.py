import os
import logging
import asyncio
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from .param_model import GenerateRequest, GenerateResponse
from .inference import FastWanInference
from .utils import download_to_temp, upload_to_b2, send_progress_update, ProcessingError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model instance
inference_engine = FastWanInference()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load model on startup
    try:
        inference_engine.load_model()
    except Exception as e:
        logger.error(f"Failed to load model on startup: {e}")
        # We don't exit here so the health check can still run, but generate will fail
    yield
    # Cleanup if needed

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health():
    ready = inference_engine.generator is not None
    return {"status": "ok", "model_loaded": ready}

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = request.musetalk_job_id  # Using same field name for compatibility
    
    logger.info(f"Received job {job_id}")
    
    # Notify orchestrator: valid
    # (In async, we might want to do this via httpx explicitly, but for simplicity we skip direct 
    # async notification here unless we implement it properly. relying on return)
    
    try:
        # 1. Download Input Image
        logger.info(f"Downloading image from {request.image_url}")
        send_progress_update(job_id, status="running", phase="downloading", progress=0.1)
        
        input_image_path = await download_to_temp(str(request.image_url), ".png")
        
        # 2. Run Inference
        logger.info("Running inference...")
        send_progress_update(job_id, status="running", phase="inference", progress=0.2)
        
        output_video_path = f"/tmp/{job_id}_output.mp4"
        
        # Run synchronous inference in thread pool to avoid blocking event loop
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
        
        # Construct public/download URL (assuming B2 structure)
        # S3-compatible URL or B2 native URL. 
        # Using a standard pattern: https://f005.backblazeb2.com/file/<bucket>/<file>
        # You might need to adjust this depending on your B2 config (CDN vs direct)
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
