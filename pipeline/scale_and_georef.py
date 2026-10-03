"""Scale and Georeferencing — centralized mode detection and scale recovery.

This module is the single source of truth for how FlightPrint handles the
three operating modes:

  FULL            — GPS + IMU present → metric scale + WGS84 georeferencing
  SCALE_ASSISTED  — partial metadata (GPS-only, or just altitude) → approximate
                    metric scale, local or partial georeferencing
  VISION_ONLY     — no metadata at all → relative/unscaled local coordinates

All mode-selection logic lives here so the rest of the pipeline can simply
call `detect_mode()` and `apply_scale_and_georef()` without scattering
conditionals everywhere.
"""

from __future__ import annotations

import json
import math
import numpy as np
from enum import Enum
from dataclasses import dataclass
from pathlib import Path

from .utils.logging import get_logger
from .utils.geo import gps_to_local_enu, interpolate_gps


# ─── Mode Definitions ────────────────────────────────────────────────────────

class ReconstructionMode(str, Enum):
    FULL = "full"
    SCALE_ASSISTED = "scale_assisted"
    VISION_ONLY = "vision_only"


class ScaleStatus(str, Enum):
    METRIC_GEOREFERENCED = "metric_georeferenced"       # Full GPS+IMU
    METRIC_APPROX = "metric_approximate"                 # Partial metadata
    RELATIVE_UNSCALED = "relative_unscaled"              # No metadata


# Human-readable labels for the frontend
MODE_LABELS = {
    ReconstructionMode.FULL: "Full accuracy — georeferenced",
    ReconstructionMode.SCALE_ASSISTED: "Approximate scale",
    ReconstructionMode.VISION_ONLY: "Relative geometry only — no metadata provided",
}

SCALE_LABELS = {
    ScaleStatus.METRIC_GEOREFERENCED: "Metric, georeferenced (WGS84)",
    ScaleStatus.METRIC_APPROX: "Approximate metric scale (local frame)",
    ScaleStatus.RELATIVE_UNSCALED: "Relative/unscaled (arbitrary units)",
}


@dataclass
class ModeDecision:
    """Result of mode detection — carries the decision plus the reasons."""
    mode: ReconstructionMode
    scale_status: ScaleStatus
    label: str
    has_gps: bool
    has_imu: bool
    has_altitude: bool
    has_intrinsics: bool
    reasons: list[str]
    user_altitude_m: float | None = None   # user-entered flight altitude
    user_scale_distance: float | None = None  # user-entered known distance

    def to_dict(self) -> dict:
        return {
            "reconstruction_mode": self.mode.value,
            "scale_status": self.scale_status.value,
            "label": self.label,
            "has_gps": self.has_gps,
            "has_imu": self.has_imu,
            "has_altitude": self.has_altitude,
            "has_intrinsics": self.has_intrinsics,
            "reasons": self.reasons,
        }


# ─── Mode Detection ──────────────────────────────────────────────────────────

def detect_mode(metadata: dict, config: dict | None = None) -> ModeDecision:
    """Auto-detect the reconstruction mode from available metadata fields.

    Args:
        metadata: Parsed metadata dict (may be empty or partial).
        config:   Optional pipeline config with user overrides like
                  ``{"user_altitude_m": 80}`` or ``{"user_scale_distance_m": 7}``.

    Returns:
        A ``ModeDecision`` describing which mode to use and why.
    """
    config = config or {}
    reasons: list[str] = []

    # ── Probe available fields ──
    gps_track = metadata.get("gps_track", [])
    imu_data = metadata.get("imu", [])
    camera = metadata.get("camera", {})

    has_gps = len(gps_track) >= 2
    has_imu = len(imu_data) >= 2
    has_intrinsics = bool(
        camera.get("focal_length_mm") or camera.get("focal_length_px")
    )

    # Altitude can come from GPS alt, a dedicated field, or user input
    has_altitude_in_gps = has_gps and any(
        pt.get("alt") is not None for pt in gps_track
    )
    user_altitude = config.get("user_altitude_m")
    meta_altitude = metadata.get("flight_altitude_m")
    has_altitude = has_altitude_in_gps or user_altitude is not None or meta_altitude is not None

    effective_altitude = (
        user_altitude
        or meta_altitude
        or (gps_track[0].get("alt") if has_altitude_in_gps else None)
    )

    user_scale_distance = config.get("user_scale_distance_m")

    # ── Decision tree ──
    if has_gps and has_imu:
        mode = ReconstructionMode.FULL
        scale_status = ScaleStatus.METRIC_GEOREFERENCED
        reasons.append("GPS track present (≥2 points)")
        reasons.append("IMU data present (≥2 readings)")
        if has_intrinsics:
            reasons.append("Camera intrinsics provided")

    elif has_gps and not has_imu:
        mode = ReconstructionMode.SCALE_ASSISTED
        scale_status = ScaleStatus.METRIC_GEOREFERENCED  # GPS alone still georefs
        reasons.append("GPS track present — used for scale + georeferencing")
        reasons.append("No IMU data — skipping attitude correction")

    elif has_altitude and not has_gps:
        mode = ReconstructionMode.SCALE_ASSISTED
        scale_status = ScaleStatus.METRIC_APPROX
        reasons.append("No GPS track available")
        if user_altitude is not None:
            reasons.append(f"User-supplied flight altitude: {user_altitude}m")
        elif meta_altitude is not None:
            reasons.append(f"Metadata flight altitude: {meta_altitude}m")
        else:
            reasons.append("Altitude from metadata fields")
        reasons.append("Deriving approximate metric scale from altitude + intrinsics")

    elif user_scale_distance is not None and not has_gps:
        mode = ReconstructionMode.SCALE_ASSISTED
        scale_status = ScaleStatus.METRIC_APPROX
        reasons.append("No GPS track available")
        reasons.append(f"User-supplied scale reference: {user_scale_distance}m")

    else:
        mode = ReconstructionMode.VISION_ONLY
        scale_status = ScaleStatus.RELATIVE_UNSCALED
        reasons.append("No GPS track, no IMU, no altitude hint")
        reasons.append("Running pure monocular SfM — output is relative/unscaled")

    if not has_intrinsics:
        reasons.append("No camera intrinsics — using generic drone preset")

    return ModeDecision(
        mode=mode,
        scale_status=scale_status,
        label=MODE_LABELS[mode],
        has_gps=has_gps,
        has_imu=has_imu,
        has_altitude=has_altitude,
        has_intrinsics=has_intrinsics,
        reasons=reasons,
        user_altitude_m=effective_altitude if mode == ReconstructionMode.SCALE_ASSISTED else None,
        user_scale_distance=user_scale_distance,
    )


# ─── Scale & Georef Application ──────────────────────────────────────────────

def apply_scale_and_georef(
    visual_poses: list[np.ndarray | None],
    frame_timestamps: list[float],
    metadata: dict,
    camera_matrix: np.ndarray,
    mode_decision: ModeDecision,
    output_dir: Path | None = None,
) -> tuple[list[np.ndarray | None], dict, list[dict]]:
    """Apply scale correction and georeferencing according to the detected mode.

    This is the single entry-point that Stage 4 calls instead of directly
    invoking ``fuse_poses_with_gps`` / ``apply_imu_orientation``.

    Returns:
        (aligned_poses, geo_origin, pose_gps_list)
    """
    log = get_logger("scale_georef", output_dir)
    mode = mode_decision.mode
    geo_origin: dict = {}
    pose_gps: list[dict] = []

    gps_track = metadata.get("gps_track", [])
    imu_data = metadata.get("imu", [])

    # ── FULL MODE ─────────────────────────────────────────────────────
    if mode == ReconstructionMode.FULL:
        log.info("Mode: FULL — GPS + IMU fusion for metric georeferenced output")

        # GPS fusion (Sim3 alignment)
        poses, geo_origin = _fuse_with_gps(visual_poses, frame_timestamps, gps_track)
        log.info(f"GPS fusion complete. Origin: {geo_origin.get('lat', '?')}, "
                 f"{geo_origin.get('lon', '?')}")

        # IMU orientation refinement
        poses = _apply_imu(poses, frame_timestamps, imu_data)
        log.info(f"IMU orientation refinement applied ({len(imu_data)} readings)")

        # Build per-frame GPS list
        pose_gps = [interpolate_gps(gps_track, ts) for ts in frame_timestamps]

        return poses, geo_origin, pose_gps

    # ── SCALE-ASSISTED MODE (GPS only, no IMU) ────────────────────────
    if mode == ReconstructionMode.SCALE_ASSISTED and mode_decision.has_gps:
        log.info("Mode: SCALE_ASSISTED (GPS only) — scale + georeferencing, no IMU correction")

        poses, geo_origin = _fuse_with_gps(visual_poses, frame_timestamps, gps_track)
        log.info(f"GPS fusion complete. Origin: {geo_origin.get('lat', '?')}, "
                 f"{geo_origin.get('lon', '?')}")

        pose_gps = [interpolate_gps(gps_track, ts) for ts in frame_timestamps]
        return poses, geo_origin, pose_gps

    # ── SCALE-ASSISTED MODE (altitude only) ───────────────────────────
    if mode == ReconstructionMode.SCALE_ASSISTED and mode_decision.user_altitude_m is not None:
        altitude = mode_decision.user_altitude_m
        log.info(f"Mode: SCALE_ASSISTED (altitude) — deriving scale from altitude={altitude}m")

        scale = _estimate_scale_from_altitude(
            visual_poses, camera_matrix, altitude
        )
        poses = _apply_uniform_scale(visual_poses, scale)
        log.info(f"Applied uniform scale factor: {scale:.4f}")
        return poses, {}, []

    # ── SCALE-ASSISTED MODE (user-entered distance) ───────────────────
    if mode == ReconstructionMode.SCALE_ASSISTED and mode_decision.user_scale_distance is not None:
        log.info(f"Mode: SCALE_ASSISTED (user distance) — "
                 f"scale from reference={mode_decision.user_scale_distance}m")
        # For now, just pass through — the user sets scale after reconstruction
        # via the API. This placeholder keeps poses in arbitrary scale until then.
        return visual_poses, {}, []

    # ── VISION-ONLY MODE ──────────────────────────────────────────────
    log.info("Mode: VISION_ONLY — no scale correction, arbitrary local frame")
    return visual_poses, {}, []


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _fuse_with_gps(
    visual_poses: list[np.ndarray | None],
    frame_timestamps: list[float],
    gps_track: list[dict],
) -> tuple[list[np.ndarray | None], dict]:
    """Sim(3) alignment of visual odometry trajectory to GPS/ENU."""
    if not gps_track:
        return visual_poses, {}

    gps_at_frames = [interpolate_gps(gps_track, ts) for ts in frame_timestamps]
    gps_enu, origin = gps_to_local_enu(gps_at_frames)

    # Collect VO positions
    vo_positions, gps_positions, valid_indices = [], [], []
    for i, pose in enumerate(visual_poses):
        if pose is not None and i < len(gps_enu):
            R_cam = pose[:3, :3]
            t_cam = pose[:3, 3]
            vo_positions.append(-R_cam.T @ t_cam)
            gps_positions.append(gps_enu[i])
            valid_indices.append(i)

    if len(vo_positions) < 3:
        # Not enough poses — set translation directly from GPS
        aligned = []
        for i, pose in enumerate(visual_poses):
            if pose is not None and i < len(gps_enu):
                new_pose = pose.copy()
                R_cam = new_pose[:3, :3]
                new_pose[:3, 3] = -R_cam @ gps_enu[i]
                aligned.append(new_pose)
            else:
                aligned.append(pose)
        return aligned, {"lat": origin["lat"], "lon": origin["lon"], "alt": origin["alt"]}

    vo_pts = np.array(vo_positions)
    gps_pts = np.array(gps_positions)
    aligned = _sim3_align(visual_poses, vo_pts, gps_pts)

    return aligned, {"lat": origin["lat"], "lon": origin["lon"], "alt": origin["alt"]}


def _sim3_align(
    poses: list[np.ndarray | None],
    src_pts: np.ndarray,
    dst_pts: np.ndarray,
) -> list[np.ndarray | None]:
    """Umeyama Sim(3) alignment: find s, R, t mapping src → dst."""
    n = len(src_pts)
    if n < 3:
        return poses

    mu_src = src_pts.mean(axis=0)
    mu_dst = dst_pts.mean(axis=0)
    src_c = src_pts - mu_src
    dst_c = dst_pts - mu_dst

    H = src_c.T @ dst_c / n
    U, S, Vt = np.linalg.svd(H)
    d = np.linalg.det(Vt.T @ U.T)
    D = np.diag([1, 1, np.sign(d)])
    R_align = Vt.T @ D @ U.T

    var_src = np.sum(src_c ** 2) / n
    scale = np.sum(S * np.diag(D)) / var_src if var_src > 1e-10 else 1.0
    t_align = mu_dst - scale * R_align @ mu_src

    aligned = []
    for pose in poses:
        if pose is None:
            aligned.append(None)
            continue
        R_cam = pose[:3, :3]
        t_cam = pose[:3, 3]
        center = -R_cam.T @ t_cam
        new_center = scale * R_align @ center + t_align
        new_R = R_cam @ R_align.T
        new_pose = np.eye(4)
        new_pose[:3, :3] = new_R
        new_pose[:3, 3] = -new_R @ new_center
        aligned.append(new_pose)
    return aligned


def _apply_imu(
    poses: list[np.ndarray | None],
    frame_timestamps: list[float],
    imu_data: list[dict],
) -> list[np.ndarray | None]:
    """Refine orientations using IMU yaw (keeps visual roll/pitch)."""
    if not imu_data:
        return poses

    try:
        from scipy.spatial.transform import Rotation as R
    except ImportError:
        from pipeline.stage4_poses import _NumpyRotation as R

    refined = []
    for i, pose in enumerate(poses):
        if pose is None:
            refined.append(None)
            continue
        ts = frame_timestamps[i] if i < len(frame_timestamps) else None
        if ts is None:
            refined.append(pose)
            continue

        # Nearest IMU
        best, best_dt = None, float("inf")
        for reading in imu_data:
            dt = abs(reading.get("timestamp", 0) - ts)
            if dt < best_dt:
                best_dt, best = dt, reading
        if best is None or best_dt > 0.5:
            refined.append(pose)
            continue

        yaw = best.get("yaw", 0.0)
        r_visual = R.from_matrix(pose[:3, :3])
        euler = r_visual.as_euler("xyz", degrees=True)
        blended = R.from_euler("xyz", [euler[0], euler[1], yaw], degrees=True).as_matrix()

        new_pose = pose.copy()
        new_pose[:3, :3] = blended
        refined.append(new_pose)

    return refined


def _estimate_scale_from_altitude(
    poses: list[np.ndarray | None],
    camera_matrix: np.ndarray,
    altitude_m: float,
) -> float:
    """Derive a uniform scale factor from a known flight altitude.

    Idea: if we know the drone flies at H meters above ground, the median
    depth of triangulated points should equal roughly H. The ratio gives
    the scale factor to apply to the whole reconstruction.
    """
    # Estimate median "depth" from camera to ground in VO coordinates
    valid_positions = []
    for pose in poses:
        if pose is not None:
            R_cam = pose[:3, :3]
            t_cam = pose[:3, 3]
            valid_positions.append(-R_cam.T @ t_cam)

    if len(valid_positions) < 2:
        return 1.0

    positions = np.array(valid_positions)
    # Use the Z-range of camera positions as a proxy for scene scale
    z_range = positions[:, 2].max() - positions[:, 2].min()
    if z_range < 1e-6:
        # Cameras all at same Z → use trajectory length instead
        diffs = np.diff(positions, axis=0)
        traj_len = np.sum(np.linalg.norm(diffs, axis=1))
        if traj_len < 1e-6:
            return 1.0
        # Assume trajectory covers roughly 5x the altitude as horizontal distance
        return altitude_m / (traj_len / 5.0)

    return altitude_m / z_range


def _apply_uniform_scale(
    poses: list[np.ndarray | None], scale: float
) -> list[np.ndarray | None]:
    """Scale all camera translations by a uniform factor."""
    scaled = []
    for pose in poses:
        if pose is None:
            scaled.append(None)
            continue
        new_pose = pose.copy()
        new_pose[:3, 3] *= scale
        scaled.append(new_pose)
    return scaled


# ─── Output Metadata Stamping ────────────────────────────────────────────────

def stamp_output(data: dict, mode_decision: ModeDecision) -> dict:
    """Inject reconstruction_mode and scale_status into any output dict."""
    data["reconstruction_mode"] = mode_decision.mode.value
    data["scale_status"] = mode_decision.scale_status.value
    data["scale_label"] = mode_decision.label
    return data


def save_mode_report(output_dir: Path, mode_decision: ModeDecision):
    """Persist mode decision to a JSON file read by the frontend."""
    path = output_dir / "reconstruction_mode.json"
    with open(path, "w") as f:
        json.dump(mode_decision.to_dict(), f, indent=2)
