"""Pipeline controller — orchestrates pipeline execution, status, and manual scaling endpoints."""

from fastapi.responses import JSONResponse

from ..models import PipelineRequest, ScaleRequest
from ..services.pipeline_service import pipeline_service


class PipelineController:
    """Controller handling pipeline operations."""

    def __init__(self, service=pipeline_service):
        self.service = service

    async def run_pipeline(self, job_id: str, request: PipelineRequest) -> dict:
        """Trigger processing pipeline for a given job."""
        return self.service.start_pipeline(job_id=job_id, request=request)

    async def get_status(self, job_id: str) -> dict:
        """Get pipeline execution status and progress metrics."""
        return self.service.get_status(job_id=job_id)

    async def get_results(self, job_id: str) -> dict:
        """Get pipeline output files and metadata."""
        return self.service.get_results(job_id=job_id)

    async def scale_pipeline(self, job_id: str, request: ScaleRequest) -> JSONResponse:
        """Apply manual scale factor to reconstruction outputs."""
        result = self.service.apply_scale(job_id=job_id, request=request)
        return JSONResponse(result)


# Global singleton instance
pipeline_controller = PipelineController()
