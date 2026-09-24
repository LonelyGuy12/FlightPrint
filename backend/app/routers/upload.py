"""Upload router — handles video + metadata file uploads."""

import uuid
import time
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from ..config import settings

router = APIRouter(prefix="/api/upload", tags=["upload"])

# In-memory job registry (would be Redis/DB in production)
jobs: dict = {}


@router.post("/")
async def upload_video(
    video: UploadFile = File(...),
    metadata: UploadFile | None = File(None),
):
    """Upload a drone video and optionally its metadata file.

    If no metadata is provided the pipeline will run in *vision-only* mode
    (pure monocular SfM, relative scale, no georeferencing).
    """
    # Validate file types
    if not video.filename.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        raise HTTPException(400, "Video must be MP4, AVI, MOV, or MKV")

    if metadata is not None and not metadata.filename.lower().endswith(".json"):
        raise HTTPException(400, "Metadata must be a JSON file")

    job_id = str(uuid.uuid4())[:8]
    job_dir = settings.upload_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save video
    video_path = job_dir / video.filename
    with open(video_path, "wb") as f:
        while chunk := await video.read(8192):
            f.write(chunk)

    # Save metadata (if provided)
    meta_path = None
    if metadata is not None:
        meta_path = job_dir / "metadata.json"
        meta_content = await metadata.read()
        try:
            json.loads(meta_content)  # Validate JSON
        except json.JSONDecodeError:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(400, "Metadata file contains invalid JSON")

        with open(meta_path, "wb") as f:
            f.write(meta_content)

    # Register job
    jobs[job_id] = {
        "job_id": job_id,
        "status": "uploaded",
        "video_filename": video.filename,
        "video_path": str(video_path),
        "metadata_path": str(meta_path) if meta_path else None,
        "has_metadata": meta_path is not None,
        "created_at": time.time(),
        "output_dir": str(settings.output_dir / job_id),
    }

    return JSONResponse({
        "job_id": job_id,
        "message": f"Uploaded {video.filename} successfully"
                   + (" (no metadata — vision-only mode)" if meta_path is None else ""),
        "video_size_mb": round(video_path.stat().st_size / 1_000_000, 1),
        "has_metadata": meta_path is not None,
    })


@router.get("/jobs")
async def list_jobs():
    """List all uploaded jobs."""
    return list(jobs.values())


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get info about a specific job."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")
    return jobs[job_id]
