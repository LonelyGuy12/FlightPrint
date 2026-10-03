"""Service handling background execution, progress querying, scaling, and results retrieval."""

import sys
import threading
from pathlib import Path
from typing import Any
from fastapi import HTTPException

from .job_service import job_service
from ..models import PipelineRequest, ScaleRequest
from ..utils.file_utils import read_json_file, get_file_size_kb, ensure_dir


class PipelineService:
    """Orchestrates pipeline execution and pipeline results generation."""

    def __init__(self):
        # Track active pipeline runner instances
        self.running_pipelines: dict[str, Any] = {}

    def _run_pipeline_background(
        self,
        job_id: str,
        job_info: dict[str, Any],
        stages: list[int] | None,
        config: dict[str, Any] | None,
    ) -> None:
        """Run the pipeline in a background thread."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

        from pipeline.runner import PipelineRunner

        output_dir = Path(job_info["output_dir"])
        ensure_dir(output_dir)

        runner = PipelineRunner(
            video_path=job_info["video_path"],
            metadata_path=job_info["metadata_path"],
            output_dir=output_dir,
            config=config or {},
        )

        self.running_pipelines[job_id] = runner

        try:
            ctx = runner.run(stages)
            job_info["status"] = runner.status.value
            job_info["num_frames"] = len(ctx.frame_paths)
            job_info["num_points"] = len(ctx.sparse_cloud) if ctx.sparse_cloud is not None else 0
            job_info["has_mesh"] = ctx.mesh_path is not None
            job_info["has_anomalies"] = len(ctx.anomalies) > 0
        except Exception as e:
            job_info["status"] = "failed"
            job_info["error"] = str(e)
        finally:
            self.running_pipelines.pop(job_id, None)

    def start_pipeline(self, job_id: str, request: PipelineRequest) -> dict[str, Any]:
        """Trigger background pipeline execution for the given job."""
        job_info = job_service.get_job(job_id)

        if job_info["status"] == "running":
            raise HTTPException(status_code=409, detail=f"Job {job_id} is already running")

        job_info["status"] = "running"

        thread = threading.Thread(
            target=self._run_pipeline_background,
            args=(job_id, job_info, request.stages, request.config),
            daemon=True,
        )
        thread.start()

        return {"job_id": job_id, "message": "Pipeline started", "status": "running"}

    def get_status(self, job_id: str) -> dict[str, Any]:
        """Get pipeline progress and current status."""
        job_info = job_service.get_job(job_id)
        output_dir = Path(job_info.get("output_dir", ""))

        progress_path = output_dir / "progress.json"
        progress = read_json_file(progress_path, default={})

        return {
            "job_id": job_id,
            "status": job_info.get("status", "unknown"),
            **progress,
        }

    def get_results(self, job_id: str) -> dict[str, Any]:
        """Retrieve dictionary of available pipeline output artifacts."""
        job_info = job_service.get_job(job_id)
        output_dir = Path(job_info.get("output_dir", ""))

        if not output_dir.exists():
            raise HTTPException(status_code=404, detail="No results available yet")

        results: dict[str, Any] = {
            "job_id": job_id,
            "status": job_info.get("status"),
            "outputs": {},
        }

        output_files = {
            "sparse_cloud": "sparse_cloud.ply",
            "dense_cloud": "dense_cloud.ply",
            "filtered_cloud": "filtered_cloud.ply",
            "mesh": "mesh.ply",
            "mesh_obj": "mesh.obj",
            "camera_trajectory": "camera_trajectory.json",
            "anomaly_report": "anomaly_report.json",
            "georef_cloud": "georef_cloud.geojson",
            "pipeline_report": "pipeline_report.json",
            "dsm": "dsm.json",
        }

        for key, filename in output_files.items():
            filepath = output_dir / filename
            if filepath.exists():
                results["outputs"][key] = {
                    "filename": filename,
                    "url": f"/api/viewer/files/{job_id}/{filename}",
                    "size_kb": get_file_size_kb(filepath),
                }

        return results

    def apply_scale(self, job_id: str, request: ScaleRequest) -> dict[str, Any]:
        """Apply manual scale factor to a completed reconstruction."""
        job_info = job_service.get_job(job_id)
        output_dir = Path(job_info["output_dir"])

        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

        try:
            from pipeline.scale_postprocess import apply_manual_scale
            mode_data = apply_manual_scale(output_dir, request.scale_factor)
            return {"message": "Scale applied successfully", "mode": mode_data}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Scale failed: {e}")


# Global singleton instance
pipeline_service = PipelineService()
