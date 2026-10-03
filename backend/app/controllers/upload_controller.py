"""Upload controller — handles HTTP request orchestration for file uploads and job queries."""

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from ..services.job_service import job_service


class UploadController:
    """Controller handling upload endpoints."""

    def __init__(self, service=job_service):
        self.service = service

    async def upload_video(
        self,
        video: UploadFile,
        metadata: UploadFile | None = None,
    ) -> JSONResponse:
        """Handle video and metadata upload."""
        result = await self.service.create_job_from_upload(video=video, metadata=metadata)
        return JSONResponse({
            "job_id": result["job_id"],
            "message": result["message"],
            "video_size_mb": result["video_size_mb"],
            "has_metadata": result["has_metadata"],
        })

    async def list_jobs(self) -> list[dict]:
        """List all jobs."""
        return self.service.list_jobs()

    async def get_job(self, job_id: str) -> dict:
        """Get details for a specific job."""
        return self.service.get_job(job_id)


# Global singleton instance
upload_controller = UploadController()
