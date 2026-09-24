"""Viewer router — serves 3D assets and scene data for the frontend."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from ..config import settings
from .upload import jobs

router = APIRouter(prefix="/api/viewer", tags=["viewer"])


@router.get("/files/{job_id}/{filename:path}")
async def serve_file(job_id: str, filename: str):
    """Serve an output file (PLY, OBJ, JSON, etc.) for the 3D viewer."""
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    output_dir = Path(jobs[job_id].get("output_dir", ""))
    filepath = output_dir / filename

    if not filepath.exists():
        raise HTTPException(404, f"File {filename} not found")

    # Security: ensure file is within output dir
    try:
        filepath.resolve().relative_to(output_dir.resolve())
    except ValueError:
        raise HTTPException(403, "Access denied")

    # Set correct MIME type
    mime_types = {
        ".ply": "application/octet-stream",
        ".obj": "text/plain",
        ".json": "application/json",
        ".geojson": "application/geo+json",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".npy": "application/octet-stream",
    }

    suffix = filepath.suffix.lower()
    media_type = mime_types.get(suffix, "application/octet-stream")

    return FileResponse(filepath, media_type=media_type, filename=filename)


@router.get("/scene/{job_id}")
async def get_scene_data(job_id: str):
    """Get all scene data for the 3D viewer in a single response.

    Combines camera trajectory, anomaly markers, geo info, mode info,
    and available assets into one payload for the frontend.
    """
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    output_dir = Path(jobs[job_id].get("output_dir", ""))
    scene = {
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
    mode_path = output_dir / "reconstruction_mode.json"
    if mode_path.exists():
        with open(mode_path) as f:
            mode_info = json.load(f)
            scene["reconstruction_mode"] = mode_info.get("reconstruction_mode")
            scene["scale_status"] = mode_info.get("scale_status")
            scene["mode_label"] = mode_info.get("label")
            scene["mode_reasons"] = mode_info.get("reasons", [])

    # Camera trajectory
    traj_path = output_dir / "camera_trajectory.json"
    if traj_path.exists():
        with open(traj_path) as f:
            scene["trajectory"] = json.load(f)

    # Anomaly report
    anomaly_path = output_dir / "anomaly_report.json"
    if anomaly_path.exists():
        with open(anomaly_path) as f:
            report = json.load(f)
            scene["anomalies"] = report.get("anomalies", [])

    # Georeferencing info
    georef_path = output_dir / "georef_report.json"
    if georef_path.exists():
        with open(georef_path) as f:
            scene["geo"] = json.load(f)

    # Pipeline report
    report_path = output_dir / "pipeline_report.json"
    if report_path.exists():
        with open(report_path) as f:
            scene["report"] = json.load(f)

    # Available assets
    asset_files = ["sparse_cloud.ply", "dense_cloud.ply", "filtered_cloud.ply",
                   "mesh.ply", "mesh.obj"]
    for af in asset_files:
        fp = output_dir / af
        if fp.exists():
            name = af.replace(".", "_").replace("_ply", "").replace("_obj", "")
            scene["assets"][af] = {
                "url": f"/api/viewer/files/{job_id}/{af}",
                "size_kb": round(fp.stat().st_size / 1024, 1),
            }

    return scene
