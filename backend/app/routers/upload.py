"""Upload router — handles video + metadata file uploads via controller."""

from fastapi import APIRouter, UploadFile, File

from ..controllers.upload_controller import upload_controller
from ..services.job_service import job_service

router = APIRouter(prefix="/api/upload", tags=["upload"])

# Backwards-compatible export for existing code referencing `upload.jobs`
jobs = job_service.jobs


@router.post("/")
async def upload_video(
    video: UploadFile = File(...),
    metadata: UploadFile | None = File(None),
):
    """Upload a drone video and optionally its metadata file.

    If no metadata is provided the pipeline will run in *vision-only* mode
    (pure monocular SfM, relative scale, no georeferencing).
    """
    return await upload_controller.upload_video(video=video, metadata=metadata)


@router.get("/jobs")
async def list_jobs():
    """List all uploaded jobs."""
    return await upload_controller.list_jobs()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get info about a specific job."""
    return await upload_controller.get_job(job_id=job_id)
