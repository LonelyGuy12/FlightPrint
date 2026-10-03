"""Viewer controller — serves 3D assets and aggregated scene data."""

from fastapi.responses import FileResponse

from ..services.viewer_service import viewer_service


class ViewerController:
    """Controller handling 3D viewer file serving and scene payloads."""

    def __init__(self, service=viewer_service):
        self.service = service

    async def serve_file(self, job_id: str, filename: str) -> FileResponse:
        """Serve scene asset file."""
        return self.service.get_file_response(job_id=job_id, filename=filename)

    async def get_scene_data(self, job_id: str) -> dict:
        """Get aggregated scene metadata and asset list."""
        return self.service.get_scene_data(job_id=job_id)


# Global singleton instance
viewer_controller = ViewerController()
