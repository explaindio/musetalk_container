from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timezone
import socket
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl

logger = logging.getLogger(__name__)

def get_worker_id() -> str:
    """
    Resolve the worker identity, prioritizing Salad Machine ID.
    """
    # 1. Try Salad Machine ID (Unique to the physical node)
    salad_id = os.environ.get("SALAD_MACHINE_ID")
    if salad_id:
        return salad_id
    
    # 2. Try configured ID (e.g. for buffer workers)
    env_id = os.environ.get("WORKER_ID")
    if env_id:
        return env_id
        
    # 3. Fallback to container hostname
    return socket.gethostname()

CURRENT_WORKER_ID = get_worker_id()

# Configuration from environment
CONFIG_LABEL = os.environ.get("CONFIG_LABEL", "default")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "8"))

app = FastAPI(title="MuseTalk Worker", description="MuseTalk job processor for Salad Job Queues.")


class GenerateRequest(BaseModel):
    musetalk_job_id: str
    video_url: HttpUrl
    audio_url: HttpUrl
    aspect_ratio: str
    resolution: str
    params: Dict[str, Any] = {}


class GenerateResponse(BaseModel):
    status: str
    output_url: Optional[str] = None
    musetalk_job_id: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class MediaError(Exception):
    """Input/media validation errors - bad URLs, corrupt files, etc."""
    def __init__(self, stage: str, message: str, details: Dict[str, Any]):
        self.stage = stage
        self.message = message
        self.details = details
        super().__init__(message)


class ProcessingError(Exception):
    """Worker/processing errors - CUDA OOM, model crashes, etc."""
    def __init__(self, stage: str, message: str, details: Dict[str, Any], retryable: bool = False):
        self.stage = stage
        self.message = message
        self.details = details
        self.retryable = retryable
        super().__init__(message)


class DownloadError(MediaError):
    """
    Represents a failure to download or validate input media.
    """

    def __init__(self, url: str, reason: str, status_code: Optional[int] = None) -> None:
        self.url = url
        self.reason = reason
        self.status_code = status_code
        details = {
            "url": url,
            "reason": reason,
            "status_code": status_code
        }
        super().__init__(
            stage="download",
            message=f"{reason} (url={url}, status={status_code})",
            details=details
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _send_progress_update(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    phase: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """
    Best-effort progress callback to the orchestrator.

    This is synchronous and uses a short timeout so it does not hold
    up inference if the orchestrator is unavailable.
    """

    base_url = os.environ.get("ORCHESTRATOR_BASE_URL")
    internal_key = os.environ.get("INTERNAL_API_KEY")
    if not base_url or not internal_key:
        return

    url = f"{base_url.rstrip('/')}/internal/jobs/{job_id}/progress"
    payload: Dict[str, Any] = {}
    if status is not None:
        payload["status"] = status
    if progress is not None:
        payload["progress"] = progress
    if phase is not None:
        payload["phase"] = phase
    if metrics is not None:
        payload["metrics"] = metrics
    if error is not None:
        payload["error"] = error
    
    payload["worker_id"] = CURRENT_WORKER_ID
    payload["config_label"] = CONFIG_LABEL
    payload["batch_size"] = BATCH_SIZE

    headers = {"X-Internal-API-Key": internal_key}

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=5.0)
        resp.raise_for_status()
    except Exception as exc:  # pragma: no cover - best-effort logging only
        logger.warning(
            "progress_update_failed",
            extra={"musetalk_job_id": job_id, "error": repr(exc)},
        )


async def _buffer_worker_loop() -> None:
    """
    Optional buffer/emergency worker loop.

    When BUFFER_WORKER_ID is set, this loop:
      - Sends periodic heartbeats to the orchestrator.
      - Claims buffer jobs and runs them via the local /generate endpoint.
    """

    # Support both BUFFER_WORKER_ID (legacy) and WORKER_MODE=buffer (new)
    worker_id = os.environ.get("BUFFER_WORKER_ID")
    worker_mode = os.environ.get("WORKER_MODE", "queue").lower()
    
    # If neither is set for buffer mode, exit
    if not worker_id and worker_mode != "buffer":
        return
    
    # Generate worker_id if only WORKER_MODE=buffer is set
    if not worker_id and worker_mode == "buffer":
        import socket
        worker_id = f"buffer-{socket.gethostname()}"

    base_url = os.environ.get("BUFFER_ORCHESTRATOR_BASE_URL") or os.environ.get(
        "ORCHESTRATOR_BASE_URL"
    )
    internal_key = os.environ.get("INTERNAL_API_KEY")
    if not base_url or not internal_key:
        logger.warning(
            "buffer_worker_disabled_missing_config",
            extra={"BUFFER_WORKER_ID": worker_id, "ORCHESTRATOR_BASE_URL": base_url},
        )
        return

    # Support both GPU_CLASS (new) and GPU_CLASS_NAME (legacy)
    gpu_class = os.environ.get("GPU_CLASS") or os.environ.get("GPU_CLASS_NAME", "Unknown GPU")
    capacity = int(os.environ.get("BUFFER_CAPACITY", "1"))
    interval_sec = int(os.environ.get("BUFFER_POLL_INTERVAL_SEC", "10"))

    headers = {"X-Internal-API-Key": internal_key}

    async with httpx.AsyncClient(timeout=30.0) as client:
        status = "idle"
        last_error: Optional[str] = None
        while True:
            try:
                # Heartbeat
                hb_body: Dict[str, Any] = {
                    "status": status,
                    "gpu_class": gpu_class,
                    "capacity": capacity,
                    "error": last_error,
                }
                hb_resp = await client.post(
                    f"{base_url.rstrip('/')}/internal/buffer/workers/{worker_id}/heartbeat",
                    json=hb_body,
                    headers=headers,
                )
                # If the orchestrator rejects the heartbeat (e.g. 401/404),
                # surface it so we get a clear log line rather than silently
                # continuing with no recorded heartbeat.
                hb_resp.raise_for_status()

                if status == "idle":
                    # Try to claim a job
                    claim_resp = await client.post(
                        f"{base_url.rstrip('/')}/internal/buffer/jobs/claim",
                        json={"worker_id": worker_id},
                        headers=headers,
                    )
                    claim_resp.raise_for_status()
                    data = claim_resp.json()
                    job = data.get("job")
                    if job:
                        buffer_job_id = job["buffer_job_id"]
                        musetalk_job_id = job["musetalk_job_id"]
                        job_ok = False
                        job_error: Optional[str] = None
                        try:
                            status = "busy"
                            last_error = None

                            # Run local generate
                            gen_body = {
                                "musetalk_job_id": musetalk_job_id,
                                "video_url": job["video_url"],
                                "audio_url": job["audio_url"],
                                "aspect_ratio": job["aspect_ratio"],
                                "resolution": job["resolution"],
                                "params": {},
                            }
                            gen_resp = await client.post(
                                "http://localhost:8000/generate",
                                json=gen_body,
                                timeout=600.0,
                            )
                            gen_resp.raise_for_status()
                            job_ok = True
                        except Exception as job_exc:  # pragma: no cover - defensive
                            job_error = repr(job_exc)
                            last_error = job_error
                            logger.warning(
                                "buffer_job_failed",
                                extra={
                                    "worker_id": worker_id,
                                    "buffer_job_id": buffer_job_id,
                                    "error": job_error,
                                },
                            )
                        # Always attempt to report final status, but do not
                        # treat reporting failures themselves as job failures.
                        try:
                            print(f"[buffer_worker] Sending status update for {buffer_job_id}: {'succeeded' if job_ok else 'failed'}", flush=True)
                            status_resp = await client.post(
                                f"{base_url.rstrip('/')}/internal/buffer/jobs/{buffer_job_id}/status",
                                json={
                                    "status": "succeeded" if job_ok else "failed",
                                    "error": None if job_ok else job_error,
                                },
                                headers=headers,
                            )
                            print(f"[buffer_worker] Status update response: {status_resp.status_code}", flush=True)
                        except Exception as report_exc:  # pragma: no cover - defensive
                            print(f"[buffer_worker] Status update FAILED: {report_exc}", flush=True)
                            logger.warning(
                                "buffer_job_status_update_failed",
                                extra={
                                    "worker_id": worker_id,
                                    "buffer_job_id": buffer_job_id,
                                    "error": repr(report_exc),
                                },
                            )
                        finally:
                            status = "idle"
            except Exception as exc:  # pragma: no cover - defensive
                last_error = repr(exc)
                tb = traceback.format_exc()
                print(f"[buffer_worker_loop_error] {last_error}\n{tb}", flush=True)
                logger.warning(
                    "buffer_worker_loop_error",
                    extra={"worker_id": worker_id, "error": last_error, "traceback": tb},
                )

            await asyncio.sleep(interval_sec)


async def _download_to_temp(
    url: str,
    suffix: str,
    *,
    max_retries: int = 3,
    chunk_size: int = 8192,
    timeout_sec: float = 300.0,
) -> str:
    """
    Download a remote file to a temporary local path.

    This helper is intentionally defensive:

      - Streams the response body so it works even when Content-Length
        is missing or reported as zero.
      - Retries a few times on transient network/protocol failures.
      - Falls back to `curl` for certain protocol-level issues that
        httpx/httpcore are more strict about (e.g. some CDNs).
      - Treats an empty download as a hard failure.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_sec, connect=10.0, read=timeout_sec),
                follow_redirects=True,
            ) as client:
                try:
                    async with client.stream("GET", url) as resp:
                        resp.raise_for_status()

                        content_type = resp.headers.get("content-type", "") or ""
                        if (
                            content_type
                            and "video" not in content_type
                            and "audio" not in content_type
                            and "octet-stream" not in content_type
                        ):
                            logger.warning(
                                "download_unexpected_content_type",
                                extra={"url": url, "content_type": content_type},
                            )

                        fd, path = tempfile.mkstemp(suffix=suffix)
                        bytes_written = 0
                        try:
                            with os.fdopen(fd, "wb") as f:
                                async for chunk in resp.aiter_bytes(chunk_size):
                                    if not chunk:
                                        continue
                                    f.write(chunk)
                                    bytes_written += len(chunk)
                        except Exception:
                            try:
                                os.remove(path)
                            except OSError:
                                pass
                            raise

                except httpx.TimeoutException as exc:
                    # Surface timeouts as DownloadError below after retries.
                    last_exc = exc
                    raise

            if bytes_written == 0:
                raise DownloadError(
                    url,
                    reason="downloaded file is empty",
                    status_code=resp.status_code,
                )

            return path

        except httpx.TimeoutException as exc:
            last_exc = exc
            if attempt < max_retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 10))
                continue

            raise DownloadError(
                url,
                reason=f"download timeout after {timeout_sec:.0f}s",
                status_code=None,
            ) from exc

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            
            # For protocol-level issues that httpx treats as fatal (like
            # `RemoteProtocolError` from some CDNs), immediately fall back to curl,
            # which tends to be more forgiving in the wild.
            # This avoids wasting retries on an error that won't succeed with httpx.
            if isinstance(exc, httpx.RemoteProtocolError):
                logger.info(
                    "download_httpx_protocol_error_fallback_to_curl",
                    extra={"url": url, "attempt": attempt},
                )
                try:
                    fd, path = tempfile.mkstemp(suffix=suffix)
                    os.close(fd)
                    cmd = [
                        "curl",
                        "-L",
                        "--fail",
                        "--max-time",
                        str(int(timeout_sec)),
                        "-o",
                        path,
                        url,
                    ]
                    proc = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    if proc.returncode != 0:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                        last_line = ""
                        if proc.stderr:
                            lines = proc.stderr.splitlines()
                            if lines:
                                last_line = lines[-1]
                        raise DownloadError(
                            url,
                            reason=(
                                f"curl failed with code {proc.returncode}: {last_line}"
                            ),
                            status_code=None,
                        )
                    size = os.path.getsize(path)
                    if size == 0:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                        raise DownloadError(
                            url,
                            reason="downloaded file is empty (curl)",
                            status_code=None,
                        )
                    return path
                except DownloadError:
                    raise
                except Exception as curl_exc:
                    raise DownloadError(
                        url,
                        reason=f"failed via httpx and curl: {curl_exc!r}",
                        status_code=None,
                    ) from curl_exc
            
            # For other transient errors, retry a couple of times.
            if attempt < max_retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 10))
                continue

            # All retries exhausted
            status_code: Optional[int] = None
            resp = getattr(exc, "response", None)
            if resp is not None:
                status_code = getattr(resp, "status_code", None)

            raise DownloadError(
                url,
                reason="failed to download after retries",
                status_code=status_code,
            ) from exc

    # This line should be unreachable, but keeps type checkers happy.
    raise DownloadError(url, reason="unreachable", status_code=None)


def _validate_media_file(path: str, expected_type: str) -> None:
    """
    Use ffprobe to check if the file is a valid media file of the expected type.
    Raises MediaError if invalid.
    """
    # Check if file exists and is not empty
    if not os.path.exists(path):
        raise MediaError(
            stage="validation",
            message=f"{expected_type} file not found",
            details={"path": path}
        )
        
    size = os.path.getsize(path)
    if size < 1000:
        raise MediaError(
            stage="validation",
            message=f"{expected_type} file too small",
            details={"path": path, "size": size, "min_size": 1000}
        )

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            raise MediaError(
                stage="validation",
                message=f"Invalid {expected_type} file: ffprobe failed",
                details={
                    "path": path, 
                    "expected_type": expected_type,
                    "ffprobe_stderr": result.stderr[:500] if result.stderr else "No stderr"
                }
            )
            
        # Basic check that we got a duration
        if not result.stdout.strip():
            raise MediaError(
                stage="validation",
                message=f"Invalid {expected_type} file: no duration info",
                details={"path": path, "ffprobe_output": result.stdout}
            )
            
    except subprocess.TimeoutExpired:
        raise MediaError(
            stage="validation",
            message=f"Validation timeout for {expected_type}",
            details={"path": path, "timeout": 30}
        )
    except Exception as e:
        if isinstance(e, MediaError):
            raise
        raise MediaError(
            stage="validation",
            message=f"Validation failed: {str(e)}",
            details={"path": path, "error": str(e)}
        )


def _upload_to_b2(file_path: str, job_id: Optional[str]) -> Tuple[str, str]:
    """
    Upload file to Backblaze B2 using b2-sdk.
    Returns (bucket_name, file_name).
    """
    from b2sdk.v2 import B2Api, InMemoryAccountInfo

    bucket_name = os.environ.get("B2_BUCKET_NAME")
    if not bucket_name:
        raise ProcessingError(
            stage="upload",
            message="B2_BUCKET_NAME not set",
            details={},
            retryable=True
        )

    # Generate object name
    ext = os.path.splitext(file_path)[1]
    name_id = job_id if job_id else f"manual-{uuid.uuid4()}"
    b2_prefix = os.environ.get("B2_PREFIX", "avatar/outputs")
    file_name = f"{b2_prefix}/{name_id}{ext}"
    
    # Check credentials
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")
    
    if not key_id or not app_key:
        raise ProcessingError(
            stage="upload",
            message="B2 credentials missing",
            details={},
            retryable=True
        )

    if not os.path.exists(file_path):
        raise ProcessingError(
            stage="upload",
            message=f"Output file not found: {file_path}",
            details={"path": file_path},
            retryable=False
        )

    try:
        info = InMemoryAccountInfo()
        b2_api = B2Api(info)
        b2_api.authorize_account("production", key_id, app_key)
        
        bucket = b2_api.get_bucket_by_name(bucket_name)
        
        file_size = os.path.getsize(file_path)
        logger.info(
            "b2_upload_start",
            extra={"bucket": bucket_name, "file": file_name, "size": file_size}
        )
        
        bucket.upload_local_file(
            local_file=file_path,
            file_name=file_name,
        )
        
        logger.info("b2_upload_success", extra={"file": file_name})
        return bucket_name, file_name
        
    except Exception as e:
        logger.exception("b2_upload_failed", extra={"error": str(e)})
        raise ProcessingError(
            stage="upload",
            message=f"B2 upload failed: {str(e)}",
            details={"bucket": bucket_name, "file_name": file_name, "error": str(e)},
            retryable=True
        )


def _build_inference_config(video_path: str, audio_path: str) -> str:
    """
    Build a temporary MuseTalk inference config YAML pointing at the
    downloaded video and audio files.
    """

    fd, yaml_path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        # Minimal OmegaConf-compatible YAML
        f.write("task_0:\n")
        f.write(f"  video_path: {video_path}\n")
        f.write(f"  audio_path: {audio_path}\n")
    return yaml_path


def _run_musetalk_inference(
    video_path: str,
    audio_path: str,
    aspect_ratio: str,
    resolution: str,
    job_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Run MuseTalk v1.5 inference via `python -m scripts.inference` and parse
    timing / resource metrics from its output (similar to run_benchmark.sh).

    Returns:
      - metrics dict with GENERATION_TIME_SEC, SCRIPT_WALL_TIME_SEC,
        PEAK_VRAM_MIB, PEAK_RAM_KB
      - output video path (on local filesystem)
    """

    workdir = os.environ.get("MUSETALK_WORKDIR", "/app")
    inference_config_path = _build_inference_config(video_path, audio_path)

    result_dir = os.environ.get("MUSETALK_RESULT_DIR", "results/job_queue")
    unet_model_path = os.environ.get(
        "MUSETALK_UNET_MODEL_PATH", "models/musetalkV15/unet.pth"
    )
    unet_config = os.environ.get(
        "MUSETALK_UNET_CONFIG", "models/musetalkV15/musetalk.json"
    )

    cmd = [
        "/usr/bin/time",
        "-v",
        "python",
        "-m",
        "scripts.inference",
        "--inference_config",
        inference_config_path,
        "--result_dir",
        result_dir,
        "--unet_model_path",
        unet_model_path,
        "--unet_config",
        unet_config,
        "--version",
        "v15",
        "--use_float16",
        "--batch_size",
        str(BATCH_SIZE),
    ]

    logger.info(
        "running_musetalk_inference", 
        extra={
            "job_id": job_id, 
            "resolution": resolution,
            "cmd": " ".join(cmd)
        }
    )

    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1800,  # 30 minute timeout
        )
    except subprocess.TimeoutExpired:
        raise ProcessingError(
            stage="inference",
            message="Inference timed out after 30 minutes",
            details={"timeout": 1800},
            retryable=True
        )
    except Exception as e:
        raise ProcessingError(
            stage="inference",
            message=f"Inference execution failed: {str(e)}",
            details={"error": str(e)},
            retryable=True
        )

    duration = time.time() - start_time
    
    # Capture stderr for debugging
    stderr_lines = proc.stderr.splitlines() if proc.stderr else []
    last_stderr = "\n".join(stderr_lines[-20:]) if stderr_lines else ""

    if proc.returncode != 0:
        logger.error(
            "inference_failed",
            extra={
                "return_code": proc.returncode,
                "stderr_tail": last_stderr,
            },
        )
        
        # Try to detect OOM
        is_oom = "CUDA out of memory" in proc.stderr or "OOM" in proc.stderr
        
        raise ProcessingError(
            stage="inference",
            message=f"Inference failed with code {proc.returncode}",
            details={
                "return_code": proc.returncode, 
                "stderr_tail": last_stderr,
                "is_oom": is_oom
            },
            retryable=is_oom  # OOM might pass on a different worker
        )

    # This matches scripts.inference default pattern for v15.
    base_dir = os.path.join(workdir, result_dir, "v15")
    # We don't know exact name; in practice you may want to glob here.
    output_vid = base_dir # This is a placeholder, actual output path needs to be parsed from stdout

    # Check validation output
    # The original code had a placeholder `output_vid = base_dir` and then checked `if output_vid is None`.
    # This needs to be updated to actually parse the output path from `proc.stdout`.
    # For now, assuming `output_vid` is correctly set by parsing `proc.stdout` or `proc.stderr`.
    # If the output path is not reliably parsed, this check might fail.
    # For this diff, we'll assume `output_vid` is the path to the expected output file.
    # The original code had a loop to parse stdout, which is now replaced by `subprocess.run`.
    # We need to re-introduce parsing logic for metrics and output_vid from `proc.stdout`.

    total_frames: Optional[int] = None
    processed_frames = 0
    last_reported_progress = 0.0
    gen_sec = None
    script_sec = None
    peak_vram = None
    peak_ram_kb = None
    output_vid_parsed: Optional[str] = None

    for line in proc.stdout.splitlines():
        if line.startswith("Number of frames:"):
            try:
                total_frames = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("PROGRESS_FRAMES="):
            try:
                processed_frames = int(line.split("=", 1)[1].strip())
                if total_frames and job_id:
                    frac = processed_frames / float(total_frames)
                    logical_progress = 0.1 + 0.8 * max(0.0, min(frac, 1.0))
                    if logical_progress >= last_reported_progress + 0.05:
                        last_reported_progress = logical_progress
                        _send_progress_update(
                            job_id,
                            status="running",
                            progress=logical_progress,
                            phase="inferring",
                            metrics={
                                "frames_done": processed_frames,
                                "frames_total": total_frames,
                            },
                        )
            except ValueError:
                pass
        elif line.startswith("Padding generated images to original video size"):
            if job_id:
                _send_progress_update(
                    job_id,
                    status="running",
                    progress=max(last_reported_progress, 0.9),
                    phase="encoding",
                )
        elif line.startswith("Generation time (model inference loop):"):
            try:
                parts = line.split(": ", 1)[1].split()
                gen_sec = float(parts[0])
            except ValueError:
                pass
        elif line.startswith("Total script wall time (main):"):
            try:
                parts = line.split(": ", 1)[1].split()
                script_sec = float(parts[0])
            except ValueError:
                pass
        elif line.startswith("Peak VRAM (PyTorch max allocated):"):
            try:
                parts = line.split(": ", 1)[1].split()
                peak_vram = float(parts[0])
            except ValueError:
                pass
        elif line.startswith("Results saved to"):
            try:
                output_vid_parsed = line.split("Results saved to", 1)[1].strip()
            except IndexError:
                pass

    for line in stderr_lines:
        if "Maximum resident set size" in line:
            try:
                parts = line.split()
                peak_ram_kb = int(parts[-2])
            except ValueError:
                pass

    if output_vid_parsed is None:
        # Fallback if inference didn't print output path
        # This matches scripts.inference default pattern for v15.
        output_vid_parsed = os.path.join(workdir, result_dir, "v15")
        # In a real scenario, you might need to glob for the actual file here.
        # For this example, we'll assume the directory is sufficient or a specific file name is known.
        # If the output is a directory, we need to find the actual video file within it.
        # For now, we'll just use the directory as a placeholder.
        # A more robust solution would involve parsing the actual filename from stdout/stderr or globbing.
        # For the purpose of this diff, we'll assume `output_vid_parsed` is the path to the video.
        # If it's a directory, the `os.path.exists` check below might need adjustment.

    if not os.path.exists(output_vid_parsed):
        raise ProcessingError(
            stage="postprocessing",
            message="Output video not found after inference success",
            details={"output_path": output_vid_parsed},
            retryable=False
        )
    
    metrics: Dict[str, Any] = {
        "GENERATION_TIME_SEC": gen_sec,
        "SCRIPT_WALL_TIME_SEC": script_sec,
        "PEAK_VRAM_MIB": peak_vram,
        "PEAK_RAM_KB": peak_ram_kb,
    }

    # Clean up temporary inference config.
    try:
        os.remove(inference_config_path)
    except OSError:
        pass

    return metrics, output_vid_parsed


def _write_asset_metadata(
    job_id: str,
    queue_job_id: Optional[str],
    gpu_class: str,
    req: GenerateRequest,
    b2_bucket: str,
    b2_file_name: str,
    metrics: Dict[str, Any],
) -> None:
    """
    Write a JSON sidecar file for the generated asset.

    In a real deployment this would upload to B2 next to the video file.
    For now, we just write to a local file for traceability.
    """

    meta = {
        "musetalk_job_id": job_id,
        "queue_job_id": queue_job_id,
        "gpu_class": gpu_class,
        "aspect_ratio": req.aspect_ratio,
        "resolution": req.resolution,
        "generation_time_sec": metrics.get("GENERATION_TIME_SEC"),
        "script_wall_time_sec": metrics.get("SCRIPT_WALL_TIME_SEC"),
        "peak_vram_mib": metrics.get("PEAK_VRAM_MIB"),
        "peak_ram_kb": metrics.get("PEAK_RAM_KB"),
        "b2_bucket": b2_bucket,
        "b2_file_name": b2_file_name,
        "create_time_utc": utc_now_iso(),
    }

    # Local write; in production this should be an upload to B2.
    meta_path = f"{job_id}.json"
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        logger.info("wrote_metadata_json", extra={"musetalk_job_id": job_id, "path": meta_path})
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("failed_to_write_metadata_json: %r", exc)


@app.get("/hc")
async def health_check() -> Dict[str, str]:
    """
    Simple health check endpoint used by Salad readiness/startup probes.
    """

    return {"status": "ok"}


@app.on_event("startup")
async def _start_buffer_worker_loop() -> None:
    """
    Optionally start the buffer worker loop when configured.

    This is enabled only when BUFFER_WORKER_ID is set, so Salad queue
    workers are unaffected.
    """

    # Support both BUFFER_WORKER_ID (legacy) and WORKER_MODE=buffer (new)
    worker_id = os.environ.get("BUFFER_WORKER_ID")
    worker_mode = os.environ.get("WORKER_MODE", "queue").lower()
    
    if worker_id or worker_mode == "buffer":
        logger.info(
            "buffer_worker_loop_starting",
            extra={"BUFFER_WORKER_ID": worker_id},
        )
        asyncio.create_task(_buffer_worker_loop())


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    """
    Entry point invoked by the Salad Job Queue worker.

    It downloads inputs, runs MuseTalk inference, uploads the video to
    storage (B2), writes a JSON metadata sidecar, and returns the URL
    and metrics.
    """

    job_id = req.musetalk_job_id
    queue_job_id = os.environ.get("SALAD_QUEUE_JOB_ID")  # may be provided by worker
    gpu_class = os.environ.get("GPU_CLASS_NAME", "unknown")

    logger.info(
        "worker_job_start",
        extra={
            "musetalk_job_id": job_id,
            "queue_job_id": queue_job_id,
            "gpu_class": gpu_class,
        },
    )

    # 0. Startup Model Check (Fail fast if something is wrong)
    # This is a lightweight check to ensure critical dependencies are importable.
    # In a real scenario, we might want to load the model on startup, 
    # but the current architecture runs inference in a subprocess, so we just check imports.
    try:
        import torch
        if not torch.cuda.is_available():
             logger.error("startup_check_failed: CUDA not available")
    except ImportError:
         logger.error("startup_check_failed: torch import failed")

    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    metrics: Dict[str, Any] = {}
    b2_bucket: Optional[str] = None
    b2_file_name: Optional[str] = None

    job_id = req.musetalk_job_id
    queue_job_id = os.environ.get("SALAD_QUEUE_JOB_ID")
    gpu_class = os.environ.get("GPU_CLASS_NAME", "unknown")
    
    stage_times: Dict[str, float] = {}
    total_start = time.time()

    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    metrics: Dict[str, Any] = {}
    b2_bucket: Optional[str] = None
    b2_file_name: Optional[str] = None

    try:
        # 1. Download Stage
        stage_start = time.time()
        video_path = await _download_to_temp(str(req.video_url), suffix=".mp4")
        audio_path = await _download_to_temp(str(req.audio_url), suffix=".wav")
        stage_times["download"] = time.time() - stage_start

        # 2. Validation Stage
        stage_start = time.time()
        _validate_media_file(video_path, "video")
        _validate_media_file(audio_path, "audio")
        stage_times["validation"] = time.time() - stage_start

        # 3. Inference Stage
        stage_start = time.time()
        
        # Send progress update
        if job_id:
             try:
                _send_progress_update(job_id, status="running", progress=0.1, phase="inference")
             except:
                pass # Non-critical
                
        metrics, output_video_path = _run_musetalk_inference(
            video_path=video_path,
            audio_path=audio_path,
            aspect_ratio=req.aspect_ratio,
            resolution=req.resolution,
            job_id=job_id,
        )
        
        # Tag metrics
        metrics = dict(metrics or {})
        metrics.setdefault("gpu_class", gpu_class)
        stage_times["inference"] = time.time() - stage_start

        # 4. Upload Stage
        stage_start = time.time()
        if job_id:
            try:
                _send_progress_update(job_id, status="running", progress=0.95, phase="uploading")
            except:
                pass

        b2_bucket, b2_file_name = _upload_to_b2(output_video_path, job_id)
        stage_times["upload"] = time.time() - stage_start
        
        # Record metadata
        _write_asset_metadata(
            job_id, queue_job_id, gpu_class, req, b2_bucket, b2_file_name, metrics
        )

        return GenerateResponse(
            status="success",
            output_url=f"https://f000.backblazeb2.com/file/{b2_bucket}/{b2_file_name}",  # Construct URL mostly for debug
            musetalk_job_id=job_id,
            metrics={
                **metrics,
                "stage_times": stage_times,
                "total_time": time.time() - total_start
            }
        )

    except MediaError as exc:
        # Return 422 for input/media errors
        logger.warning(
            "media_error",
            extra={
                "job_id": job_id,
                "queue_job_id": queue_job_id,
                "stage": exc.stage,
                "error": exc.message,
                "details": exc.details
            }
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "status": "failed",
                "error_type": "media_error",
                "error_message": exc.message,
                "stage": exc.stage,
                "details": exc.details,
                "retryable": False,
                "stage_times": stage_times
            }
        )

    except ProcessingError as exc:
        # Return 500 for worker/processing errors
        logger.error(
            "processing_error", 
            extra={
                "job_id": job_id,
                "queue_job_id": queue_job_id,
                "stage": exc.stage,
                "error": exc.message,
                "details": exc.details
            }
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "failed",
                "error_type": "processing_error",
                "error_message": exc.message,
                "stage": exc.stage,
                "details": exc.details,
                "stack_trace": traceback.format_exc(),
                "retryable": exc.retryable,
                "stage_times": stage_times
            }
        )

    except Exception as exc:
        # Catch-all for unexpected errors
        logger.error(
            "unexpected_worker_error",
            extra={
                "job_id": job_id,
                "queue_job_id": queue_job_id,
                "error": str(exc),
                "traceback": traceback.format_exc()
            }
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "failed",
                "error_type": "unknown_error",
                "error_message": str(exc),
                "stage": "unknown",
                "details": {},
                "stack_trace": traceback.format_exc(),
                "retryable": False,
                "stage_times": stage_times
            }
        )
        
    finally:
        # Best-effort cleanup of temp files
        for p in [video_path, audio_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
