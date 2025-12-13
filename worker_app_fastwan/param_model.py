from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict, Any

class GenerateRequest(BaseModel):
    musetalk_job_id: str  # Kept naming for consistency with orchestrator, or generic 'job_id'
    image_url: HttpUrl
    prompt: str
    num_frames: int = 121
    width: int = 480
    height: int = 832
    steps: int = 4
    seed: int = 42
    guidance_scale: float = 1.0
    params: Dict[str, Any] = {}

class GenerateResponse(BaseModel):
    status: str
    output_url: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
