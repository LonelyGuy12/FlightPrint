"""Viewer router — serves 3D assets and scene data for the frontend via controller."""

from fastapi import APIRouter

from ..controllers.viewer_controller import viewer_controller

router = APIRouter(prefix="/api/viewer", tags=["viewer"])


@router.get("/files/{job_id}/{filename:path}")
async def serve_file(job_id: str, filename: str):
    """Serve an output file (PLY, OBJ, JSON, etc.) for the 3D viewer."""
    return await viewer_controller.serve_file(job_id=job_id, filename=filename)


@router.get("/scene/{job_id}")
async def get_scene_data(job_id: str):
    """Get all scene data for the 3D viewer in a single response."""
    return await viewer_controller.get_scene_data(job_id=job_id)
