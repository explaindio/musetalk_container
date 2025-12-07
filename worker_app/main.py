from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl

logger = logging.getLogger(__name__)

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
    b2_bucket: Optional[str] = None
    b2_file_name: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


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

    worker_id = os.environ.get("BUFFER_WORKER_ID")
    if not worker_id:
        return

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

    gpu_class = os.environ.get("GPU_CLASS_NAME")
    capacity = int(os.environ.get("BUFFER_CAPACITY", "1"))
    interval_sec = int(os.environ.get("BUFFER_POLL_INTERVAL_SEC", "10"))

    headers = {"X-Internal-API-Key": internal_key}

    async with httpx.AsyncClient(timeout=10.0) as client:
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
                            await client.post(
                                f"{base_url.rstrip('/')}/internal/buffer/jobs/{buffer_job_id}/status",
                                json={
                                    "status": "succeeded" if job_ok else "failed",
                                    "error": None if job_ok else job_error,
                                },
                                headers=headers,
                            )
                        except Exception as report_exc:  # pragma: no cover - defensive
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
                logger.warning(
                    "buffer_worker_loop_error",
                    extra={"worker_id": worker_id, "error": last_error},
                )

            await asyncio.sleep(interval_sec)


async def _download_to_temp(url: str, suffix: str) -> str:
    """
    Download a remote file to a temporary local path.

    This is a simple helper; in the actual production image we may
    want to reuse any existing download/caching utilities.
    """

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(resp.content)
    return path


def _upload_to_b2(local_path: str, job_id: str) -> Tuple[str, str]:
    """
    Upload the rendered video to Backblaze B2 using credentials from env.

    Required env vars:
      - B2_KEY_ID
      - B2_APP_KEY
      - B2_BUCKET_NAME
      - B2_PREFIX (optional path prefix within the bucket)

    Returns:
      (bucket_name, file_name) identifying the stored object. The orchestrator
      will use this information to generate signed HTTPS URLs with a chosen TTL.
    """

    from b2sdk.v2 import B2Api, InMemoryAccountInfo

    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")
    bucket_name = os.environ.get("B2_BUCKET_NAME")
    prefix = os.environ.get("B2_PREFIX", "").strip("/")

    if not key_id or not app_key or not bucket_name:
        raise RuntimeError("Missing B2_KEY_ID, B2_APP_KEY, or B2_BUCKET_NAME in environment")

    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", key_id, app_key)
    bucket = b2_api.get_bucket_by_name(bucket_name)

    file_name = f"{prefix}/{job_id}.mp4" if prefix else f"{job_id}.mp4"
    bucket.upload_local_file(local_file=local_path, file_name=file_name)
    return bucket_name, file_name


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
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    if proc.stdout is None or proc.stderr is None:  # pragma: no cover - defensive
        raise RuntimeError("Failed to capture MuseTalk stdout/stderr")

    total_frames: Optional[int] = None
    processed_frames = 0
    last_reported_progress = 0.0
    gen_sec = None
    script_sec = None
    peak_vram = None
    peak_ram_kb = None
    output_vid = None

    # Stream stdout so we can emit progress updates while inference runs.
    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("Number of frames:"):
            try:
                # "Number of frames: N"
                total_frames = int(line.split(":", 1)[1].strip())
                if job_id:
                    _send_progress_update(
                        job_id,
                        status="running",
                        progress=0.0,
                        phase="preparing",
                        metrics={"frames_total": total_frames},
                    )
            except Exception:
                pass
        elif line.startswith("PROGRESS_FRAMES="):
            try:
                processed_frames = int(line.split("=", 1)[1].strip())
                if total_frames and job_id:
                    frac = processed_frames / float(total_frames)
                    # Map raw inference progress into 0.1–0.9 window.
                    logical_progress = 0.1 + 0.8 * max(0.0, min(frac, 1.0))
                    # Emit only on meaningful change (~5%).
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
            except Exception:
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
                # ...: 24.374 seconds
                parts = line.split(": ", 1)[1].split()
                gen_sec = float(parts[0])
            except Exception:
                pass
        elif line.startswith("Total script wall time (main):"):
            try:
                parts = line.split(": ", 1)[1].split()
                script_sec = float(parts[0])
            except Exception:
                pass
        elif line.startswith("Peak VRAM (PyTorch max allocated):"):
            try:
                parts = line.split(": ", 1)[1].split()
                peak_vram = float(parts[0])
            except Exception:
                pass
        elif line.startswith("Results saved to"):
            # Expected: "Results saved to <path>"
            try:
                output_vid = line.split("Results saved to", 1)[1].strip()
            except Exception:
                pass

    stderr_lines = proc.stderr.read().splitlines()

    for line in stderr_lines:
        if "Maximum resident set size" in line:
            try:
                # ...: 123456 kbytes
                parts = line.split()
                peak_ram_kb = int(parts[-2])
            except Exception:
                pass

    return_code = proc.wait()
    if return_code != 0:
        raise RuntimeError(
            f"Inference process failed with code {return_code}: "
            f"{os.linesep.join(stderr_lines)[:500]}"
        )

    metrics: Dict[str, Any] = {
        "GENERATION_TIME_SEC": gen_sec,
        "SCRIPT_WALL_TIME_SEC": script_sec,
        "PEAK_VRAM_MIB": peak_vram,
        "PEAK_RAM_KB": peak_ram_kb,
    }

    # Fallback if inference didn't print output path
    if output_vid is None:
        # This matches scripts.inference default pattern for v15.
        base_dir = os.path.join(workdir, result_dir, "v15")
        # We don't know exact name; in practice you may want to glob here.
        output_vid = base_dir

    # Clean up temporary inference config.
    try:
        os.remove(inference_config_path)
    except OSError:
        pass

    return metrics, output_vid


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

    worker_id = os.environ.get("BUFFER_WORKER_ID")
    if worker_id:
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

    try:
        video_path = await _download_to_temp(str(req.video_url), suffix=".mp4")
        audio_path = await _download_to_temp(str(req.audio_url), suffix=".wav")
        metrics, output_video_path = _run_musetalk_inference(
            video_path=video_path,
            audio_path=audio_path,
            aspect_ratio=req.aspect_ratio,
            resolution=req.resolution,
            job_id=job_id,
        )
        # Tag metrics with gpu_class so the orchestrator can aggregate
        # per-tier statistics later.
        metrics = dict(metrics or {})
        metrics.setdefault("gpu_class", gpu_class)
        if job_id:
            _send_progress_update(
                job_id,
                status="running",
                progress=0.95,
                phase="uploading",
            )
        b2_bucket, b2_file_name = _upload_to_b2(output_video_path, job_id)
        _write_asset_metadata(
            job_id, queue_job_id, gpu_class, req, b2_bucket, b2_file_name, metrics
        )
    finally:
        # Best-effort cleanup of temp files
        for p in [locals().get("video_path"), locals().get("audio_path")]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    if metrics.get("GENERATION_TIME_SEC") is None or metrics.get(
        "SCRIPT_WALL_TIME_SEC"
    ) is None:
        # Still treat as success but log a warning; metrics parsing failed.
        logger.warning(
            "worker_job_missing_metrics",
            extra={
                "musetalk_job_id": job_id,
                "queue_job_id": queue_job_id,
            },
        )

    logger.info(
        "worker_job_success",
        extra={
            "musetalk_job_id": job_id,
            "queue_job_id": queue_job_id,
            "gpu_class": gpu_class,
            "b2_bucket": b2_bucket,
            "b2_file_name": b2_file_name,
            "metrics": metrics,
        },
    )
    if job_id:
        progress_metrics = dict(metrics or {})
        progress_metrics.update(
            {
                "b2_bucket": b2_bucket,
                "b2_file_name": b2_file_name,
            }
        )
        _send_progress_update(
            job_id,
            status="succeeded",
            progress=1.0,
            phase="completed",
            metrics=progress_metrics,
        )

    return GenerateResponse(
        status="ok",
        b2_bucket=b2_bucket,
        b2_file_name=b2_file_name,
        metrics=metrics,
    )
