"""Pipeline router — triggers processing and reports status via controller."""

from fastapi import APIRouter

from ..models import PipelineRequest, ScaleRequest
from ..controllers.pipeline_controller import pipeline_controller

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run/{job_id}")
async def run_pipeline(job_id: str, request: PipelineRequest = PipelineRequest()):
    """Trigger the processing pipeline for an uploaded video.

    Runs in the background — poll /status/{job_id} for progress.
    """
    return await pipeline_controller.run_pipeline(job_id=job_id, request=request)


@router.get("/status/{job_id}")
async def pipeline_status(job_id: str):
    """Get current pipeline status and progress."""
    return await pipeline_controller.get_status(job_id=job_id)


@router.get("/results/{job_id}")
async def pipeline_results(job_id: str):
    """Get pipeline results — available outputs and metadata."""
    return await pipeline_controller.get_results(job_id=job_id)


@router.post("/scale/{job_id}")
async def scale_pipeline(job_id: str, request: ScaleRequest):
    """Apply manual scale factor to a completed vision-only reconstruction."""
    return await pipeline_controller.scale_pipeline(job_id=job_id, request=request)
