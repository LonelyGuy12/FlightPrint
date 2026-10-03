"""Service for retrieving scene data and resolving files for the 3D viewer."""

from pathlib import Path
from typing import Any
from fastapi import HTTPException
from fastapi.responses import FileResponse

from .job_service import job_service
from ..utils.file_utils import (
    read_json_file,
    get_file_size_kb,
    resolve_safe_subpath,
    MIME_TYPES,
)


class ViewerService:
    """Manages scene aggregation and asset serving."""

    def get_file_response(self, job_id: str, filename: str) -> FileResponse:
        """Resolve an output file safely and return a FileResponse with appropriate mime type."""
        job_info = job_service.get_job(job_id)
        output_dir = Path(job_info.get("output_dir", ""))

        filepath = resolve_safe_subpath(output_dir, filename)

        if not filepath.exists():
            raise HTTPException(status_code=404, detail=f"File {filename} not found")

        suffix = filepath.suffix.lower()
        media_type = MIME_TYPES.get(suffix, "application/octet-stream")

        return FileResponse(filepath, media_type=media_type, filename=filename)

    def get_scene_data(self, job_id: str) -> dict[str, Any]:
        """Combine scene outputs, camera trajectory, anomalies, and assets into a payload."""
        job_info = job_service.get_job(job_id)
        output_dir = Path(job_info.get("output_dir", ""))

        scene: dict[str, Any] = {
            "job_id": job_id,
            "assets": {},
            "trajectory": None,
            "anomalies": [],
            "geo": None,
            "reconstruction_mode": None,
            "scale_status": None,
            "mode_label": None,
        }

        # Reconstruction mode
        mode_info = read_json_file(output_dir / "reconstruction_mode.json")
        if mode_info:
            scene["reconstruction_mode"] = mode_info.get("reconstruction_mode")
            scene["scale_status"] = mode_info.get("scale_status")
            scene["mode_label"] = mode_info.get("label")
            scene["mode_reasons"] = mode_info.get("reasons", [])

        # Camera trajectory
        scene["trajectory"] = read_json_file(output_dir / "camera_trajectory.json")

        # Anomaly report
        anomaly_report = read_json_file(output_dir / "anomaly_report.json")
        if anomaly_report:
            scene["anomalies"] = anomaly_report.get("anomalies", [])

        # Georeferencing info
        scene["geo"] = read_json_file(output_dir / "georef_report.json")

        # Pipeline report
        scene["report"] = read_json_file(output_dir / "pipeline_report.json")

        # Available assets
        asset_files = [
            "sparse_cloud.ply",
            "dense_cloud.ply",
            "filtered_cloud.ply",
            "mesh.ply",
            "mesh.obj",
        ]
        for af in asset_files:
            fp = output_dir / af
            if fp.exists():
                scene["assets"][af] = {
                    "url": f"/api/viewer/files/{job_id}/{af}",
                    "size_kb": get_file_size_kb(fp),
                }

        return scene


# Global singleton instance
viewer_service = ViewerService()
