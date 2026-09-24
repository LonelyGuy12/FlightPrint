"""Pipeline router — triggers processing and reports status."""

import json
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from ..config import settings
from ..models import PipelineRequest, ScaleRequest
from .upload import jobs

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# Track running pipelines
running_pipelines: dict = {}


def _run_pipeline_background(job_id: str, job_info: dict, stages: list[int] | None, config: dict | None):
    """Run the pipeline in a background thread."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from pipeline.runner import PipelineRunner

    output_dir = Path(job_info["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    runner = PipelineRunner(
        video_path=job_info["video_path"],
        metadata_path=job_info["metadata_path"],
        output_dir=output_dir,
        config=config or {},
    )

    running_pipelines[job_id] = runner

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
        running_pipelines.pop(job_id, None)


@router.post("/run/{job_id}")
async def run_pipeline(job_id: str, request: PipelineRequest = PipelineRequest()):
    """Trigger the processing pipeline for an uploaded video.
    
    Runs in the background — poll /status/{job_id} for progress.
    """
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job_info = jobs[job_id]

    if job_info["status"] == "running":
        raise HTTPException(409, f"Job {job_id} is already running")

    job_info["status"] = "running"

    # Run in background thread
    thread = threading.Thread(
        target=_run_pipeline_background,
        args=(job_id, job_info, request.stages, request.config),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "message": "Pipeline started", "status": "running"}


@router.get("/status/{job_id}")
async def pipeline_status(job_id: str):
    """Get current pipeline status and progress."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job_info = jobs[job_id]
    output_dir = Path(job_info.get("output_dir", ""))

    # Read progress file if it exists
    progress_path = output_dir / "progress.json"
    progress = {}
    if progress_path.exists():
        try:
            with open(progress_path) as f:
                progress = json.load(f)
        except Exception:
            pass

    return {
        "job_id": job_id,
        "status": job_info.get("status", "unknown"),
        **progress,
    }


@router.get("/results/{job_id}")
async def pipeline_results(job_id: str):
    """Get pipeline results — available outputs and metadata."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job_info = jobs[job_id]
    output_dir = Path(job_info.get("output_dir", ""))

    if not output_dir.exists():
        raise HTTPException(404, "No results available yet")

    results = {
        "job_id": job_id,
        "status": job_info.get("status"),
        "outputs": {},
    }

    # Check for available outputs
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
                "size_kb": round(filepath.stat().st_size / 1024, 1),
            }

    return results


@router.post("/scale/{job_id}")
async def scale_pipeline(job_id: str, request: ScaleRequest):
    """Apply manual scale factor to a completed vision-only reconstruction."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job_info = jobs[job_id]
    output_dir = Path(job_info["output_dir"])

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    
    try:
        from pipeline.scale_postprocess import apply_manual_scale
        mode_data = apply_manual_scale(output_dir, request.scale_factor)
        return JSONResponse({"message": "Scale applied successfully", "mode": mode_data})
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Scale failed: {e}")
