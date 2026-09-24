"""File I/O helpers for FlightPrint pipeline."""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ..scale_and_georef import ModeDecision


@dataclass
class PipelineContext:
    """Shared context passed between pipeline stages.
    
    Each stage reads from and writes to this context, along with the
    filesystem (output_dir). This keeps inter-stage coupling explicit.
    """
    video_path: Path
    metadata_path: Path | None            # None when user uploads video-only
    output_dir: Path

    # Populated by metadata loading
    metadata: dict = field(default_factory=dict)

    # Reconstruction mode (set early by runner, read by all downstream stages)
    reconstruction_mode: str = "vision_only"    # "full" | "scale_assisted" | "vision_only"
    scale_status: str = "relative_unscaled"     # "metric_georeferenced" | "metric_approximate" | "relative_unscaled"
    mode_decision: Any = None                   # ModeDecision dataclass (avoids circular import)

    # Stage 1 outputs
    frames_dir: Path | None = None
    frame_timestamps: list[float] = field(default_factory=list)
    frame_paths: list[Path] = field(default_factory=list)

    # Stage 2 outputs
    camera_matrix: np.ndarray | None = None
    dist_coeffs: np.ndarray | None = None

    # Stage 3 outputs
    keypoints: list[Any] = field(default_factory=list)  # per-frame keypoints
    descriptors: list[np.ndarray | None] = field(default_factory=list)
    matches: dict = field(default_factory=dict)  # (i,j) -> list of matches

    # Stage 4 outputs
    poses: list[np.ndarray | None] = field(default_factory=list)  # 4x4 transforms
    pose_gps: list[dict] = field(default_factory=list)  # GPS for each frame
    geo_origin: dict = field(default_factory=dict)  # ENU origin

    # Stage 5+ outputs
    sparse_cloud: np.ndarray | None = None
    sparse_colors: np.ndarray | None = None
    dense_cloud: np.ndarray | None = None
    dense_colors: np.ndarray | None = None
    mesh_path: Path | None = None

    # AI outputs
    anomalies: list[dict] = field(default_factory=list)


def load_metadata(metadata_path: Path | None) -> dict:
    """Load and validate the flight metadata JSON file.

    Returns an empty dict if *metadata_path* is ``None`` or the file cannot
    be parsed — this enables vision-only mode instead of crashing.

    Expected structure (all fields optional)::

        {
            "gps_track": [{"timestamp": float, "lat": float, "lon": float, "alt": float}, ...],
            "camera": {"focal_length_mm": float, "sensor_width_mm": float, ...},
            "imu": [{"timestamp": float, "roll": float, "pitch": float, "yaw": float}, ...],
            "flight_altitude_m": float   // optional single altitude hint
        }
    """
    if metadata_path is None:
        return {}

    path = Path(metadata_path)
    if not path.exists():
        return {}

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    # Ensure gps_track is sorted by timestamp
    if "gps_track" in data:
        data["gps_track"] = sorted(data["gps_track"], key=lambda x: x.get("timestamp", 0))

    return data


def save_point_cloud_ply(path: Path, points: np.ndarray, colors: np.ndarray | None = None):
    """Save a point cloud to PLY format.
    
    Args:
        path: Output PLY file path.
        points: Nx3 array of XYZ coordinates.
        colors: Optional Nx3 array of RGB colors (0-255).
    """
    n = len(points)
    has_color = colors is not None and len(colors) == n

    with open(path, "w") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {n}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        if has_color:
            f.write("property uchar red\n")
            f.write("property uchar green\n")
            f.write("property uchar blue\n")
        f.write("end_header\n")

        for i in range(n):
            line = f"{points[i, 0]:.6f} {points[i, 1]:.6f} {points[i, 2]:.6f}"
            if has_color:
                r, g, b = int(colors[i, 0]), int(colors[i, 1]), int(colors[i, 2])
                line += f" {r} {g} {b}"
            f.write(line + "\n")


def save_camera_trajectory(path: Path, poses: list, timestamps: list[float],
                           gps_points: list[dict],
                           mode_decision: "ModeDecision | None" = None):
    """Save camera trajectory to a JSON file for the web viewer."""
    trajectory = []
    for i, (pose, ts) in enumerate(zip(poses, timestamps)):
        entry = {"frame_index": i, "timestamp": ts}
        if pose is not None:
            entry["pose"] = pose.tolist()
        if i < len(gps_points):
            entry["gps"] = gps_points[i]
        trajectory.append(entry)

    payload: dict = {"trajectory": trajectory}
    if mode_decision is not None:
        payload["reconstruction_mode"] = mode_decision.mode.value
        payload["scale_status"] = mode_decision.scale_status.value

    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def save_pipeline_report(path: Path, ctx: "PipelineContext"):
    """Save a summary report of the pipeline run."""
    report = {
        "video": str(ctx.video_path),
        "reconstruction_mode": ctx.reconstruction_mode,
        "scale_status": ctx.scale_status,
        "num_frames": len(ctx.frame_paths),
        "num_poses_estimated": sum(1 for p in ctx.poses if p is not None),
        "sparse_points": len(ctx.sparse_cloud) if ctx.sparse_cloud is not None else 0,
        "dense_points": len(ctx.dense_cloud) if ctx.dense_cloud is not None else 0,
        "num_anomalies": len(ctx.anomalies),
        "geo_origin": ctx.geo_origin,
    }
    if ctx.mode_decision is not None:
        report["mode_reasons"] = ctx.mode_decision.reasons

    with open(path, "w") as f:
        json.dump(report, f, indent=2)
