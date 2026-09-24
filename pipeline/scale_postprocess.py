"""Post-processing module to apply a manual scale factor.

This is used when a user manually measures a distance in a Vision-Only
(unscaled) reconstruction and provides the real-world distance, allowing
us to retroactively scale the entire scene to approximate metric units.
"""

import json
from pathlib import Path
import numpy as np

from .utils.logging import get_logger
from .scale_and_georef import ReconstructionMode, ScaleStatus


def apply_manual_scale(job_dir: str | Path, scale_factor: float) -> dict:
    """Retroactively scale an existing reconstruction by a uniform factor.
    
    Args:
        job_dir: Path to the pipeline output directory.
        scale_factor: Multiplier to convert relative units to meters.
        
    Returns:
        Updated scene metadata.
    """
    job_dir = Path(job_dir)
    log = get_logger("scale_postprocess", job_dir)
    
    mode_path = job_dir / "reconstruction_mode.json"
    if not mode_path.exists():
        raise FileNotFoundError("reconstruction_mode.json not found")
        
    with open(mode_path, "r") as f:
        mode_data = json.load(f)
        
    if mode_data.get("scale_status") == ScaleStatus.METRIC_GEOREFERENCED.value:
        raise ValueError("Cannot manually scale a fully georeferenced reconstruction.")

    log.info(f"Applying manual scale factor: {scale_factor:.4f}")

    # 1. Scale camera trajectory
    traj_path = job_dir / "camera_trajectory.json"
    if traj_path.exists():
        with open(traj_path, "r") as f:
            traj_data = json.load(f)
            
        for entry in traj_data.get("trajectory", []):
            if "pose" in entry:
                pose = np.array(entry["pose"])
                pose[:3, 3] *= scale_factor
                entry["pose"] = pose.tolist()
                
        traj_data["reconstruction_mode"] = ReconstructionMode.SCALE_ASSISTED.value
        traj_data["scale_status"] = ScaleStatus.METRIC_APPROX.value
        
        with open(traj_path, "w") as f:
            json.dump(traj_data, f, indent=2)
        log.info("Scaled camera trajectory")

    # 2. Scale anomalies
    anomaly_path = job_dir / "anomaly_report.json"
    if anomaly_path.exists():
        with open(anomaly_path, "r") as f:
            anom_data = json.load(f)
            
        for anomaly in anom_data.get("anomalies", []):
            if "position_enu" in anomaly:
                pos = np.array(anomaly["position_enu"])
                pos *= scale_factor
                anomaly["position_enu"] = pos.tolist()
                
            # Naive string replace for descriptions (converting ratio back to roughly meters)
            # This is a hackathon shortcut; ideal would be re-running Stage 9.
            desc = anomaly.get("description", "")
            if "~" in desc and "×" in desc:
                try:
                    # extract "~2.3×" -> 2.3
                    ratio = float(desc.split("~")[1].split("×")[0])
                    # We don't have z_std easily, but we know the position.
                    # Just rewrite it generically to avoid wrong math.
                    anomaly["description"] = desc.replace("std-dev", "meters (approx)")
                except Exception:
                    pass
                    
        anom_data["reconstruction_mode"] = ReconstructionMode.SCALE_ASSISTED.value
        anom_data["scale_status"] = ScaleStatus.METRIC_APPROX.value
        
        with open(anomaly_path, "w") as f:
            json.dump(anom_data, f, indent=2)
        log.info("Scaled anomaly positions")

    # 3. Scale 3D Assets using Open3D
    try:
        import open3d as o3d
        
        assets = ["sparse_cloud.ply", "dense_cloud.ply", "filtered_cloud.ply", "mesh.ply", "mesh.obj"]
        for asset in assets:
            asset_path = job_dir / asset
            if asset_path.exists():
                if asset.endswith(".ply"):
                    if "mesh" in asset:
                        geom = o3d.io.read_triangle_mesh(str(asset_path))
                    else:
                        geom = o3d.io.read_point_cloud(str(asset_path))
                elif asset.endswith(".obj"):
                    geom = o3d.io.read_triangle_mesh(str(asset_path))
                
                # Scale geometry around origin
                geom.scale(scale_factor, center=(0, 0, 0))
                
                if isinstance(geom, o3d.geometry.TriangleMesh):
                    o3d.io.write_triangle_mesh(str(asset_path), geom)
                else:
                    o3d.io.write_point_cloud(str(asset_path), geom)
                    
                log.info(f"Scaled 3D asset: {asset}")
    except ImportError:
        log.warning("Open3D not available, skipping 3D asset scaling!")

    # 4. Update mode report
    mode_data["reconstruction_mode"] = ReconstructionMode.SCALE_ASSISTED.value
    mode_data["scale_status"] = ScaleStatus.METRIC_APPROX.value
    mode_data["label"] = "Approximate scale (user anchored)"
    mode_data["reasons"].append(f"User applied manual scale factor: {scale_factor:.4f}")
    
    with open(mode_path, "w") as f:
        json.dump(mode_data, f, indent=2)
        
    log.info("Successfully applied manual scale factor.")
    return mode_data
