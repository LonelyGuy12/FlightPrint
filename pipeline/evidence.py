"""Evidence linking and confidence scoring for FlightPrint findings.

Every anomaly found in the 3D reconstruction is traced back to the video
frames that actually show it, so a reviewer can check each finding against
the source footage.

How it works
------------
Stage 4 gives a world-to-camera pose [R | t] for each extracted frame, and
Stage 2 gives the intrinsic matrix K. A 3D point X projects into frame i at

    x_cam = R_i X + t_i,      [u, v, 1]^T ~ K x_cam / z_cam

A frame *supports* a finding when the point lies in front of the camera
(z_cam > 0) and projects inside the image with a small margin. Frames are
ranked by how central the point is in the image and how close the camera is.

Confidence
----------
Each finding's confidence combines four factors, each in [0, 1]:

    signal     how strongly the detector fired (e.g. elevation z-score)
    views      how many frames see it:          1 - exp(-n_views / 4)
    diversity  spread of viewing angles:        min(1, max_angle_deg / 30)
    points     3D points behind it:             1 - exp(-n_points / 50)

    confidence = 0.35 signal + 0.25 views + 0.20 diversity + 0.20 points

A finding with no supporting frame is capped at 0.30 and marked
"unverified": it may be a reconstruction artefact. Occlusion is not
modelled yet, so a supporting frame can in rare cases show a wall in front
of the point; the saved crops make that easy to spot.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

CONFIDENCE_WEIGHTS = {"signal": 0.35, "views": 0.25, "diversity": 0.20, "points": 0.20}
UNVERIFIED_CAP = 0.30


# ---------------------------------------------------------------- projection

def project_point(point: np.ndarray, pose: np.ndarray, K: np.ndarray) -> tuple[float, float, float]:
    """Project a world point with a 4x4 world-to-camera pose. Returns (u, v, depth)."""
    x_cam = pose[:3, :3] @ np.asarray(point, dtype=np.float64) + pose[:3, 3]
    depth = float(x_cam[2])
    if depth <= 1e-9:
        return float("nan"), float("nan"), depth
    uvw = K @ x_cam
    return float(uvw[0] / uvw[2]), float(uvw[1] / uvw[2]), depth


def camera_center(pose: np.ndarray) -> np.ndarray:
    """Camera position in world coordinates for a world-to-camera pose."""
    return -pose[:3, :3].T @ pose[:3, 3]


def find_supporting_frames(point: np.ndarray, poses: list, K: np.ndarray,
                           image_size: tuple[int, int],
                           frame_paths: list | None = None,
                           frame_timestamps: list[float] | None = None,
                           margin: float = 0.05,
                           max_frames: int = 8) -> list[dict]:
    """Frames in which *point* is visible, best first.

    Args:
        point: 3D point in the reconstruction's world frame.
        poses: per-frame 4x4 world-to-camera transforms (None for unposed frames).
        K: 3x3 intrinsic matrix.
        image_size: (width, height) of the extracted frames.
        margin: fraction of width/height to ignore at the image border.
        max_frames: keep at most this many frames (best ranked).
    """
    w, h = image_size
    mx, my = margin * w, margin * h
    half_diag = math.hypot(w / 2, h / 2)
    hits = []
    for i, pose in enumerate(poses):
        if pose is None:
            continue
        u, v, depth = project_point(point, pose, K)
        if depth <= 0 or not (mx <= u <= w - mx and my <= v <= h - my):
            continue
        centrality = 1.0 - math.hypot(u - w / 2, v - h / 2) / half_diag
        hits.append({
            "frame_index": i,
            "timestamp": float(frame_timestamps[i]) if frame_timestamps and i < len(frame_timestamps) else None,
            "frame_path": str(frame_paths[i]) if frame_paths and i < len(frame_paths) else None,
            "pixel": [round(u, 1), round(v, 1)],
            "depth": round(depth, 3),
            "centrality": round(centrality, 3),
        })

    if not hits:
        return []
    # Rank: central in the image first, then nearer cameras.
    depths = np.array([hh["depth"] for hh in hits])
    d_norm = depths / depths.max() if depths.max() > 0 else depths
    for hh, dn in zip(hits, d_norm):
        hh["score"] = round(0.7 * hh["centrality"] + 0.3 * (1.0 - float(dn)), 3)
    hits.sort(key=lambda hh: hh["score"], reverse=True)
    return hits[:max_frames]


def viewing_angle_spread(point: np.ndarray, poses: list, frame_indices: list[int]) -> float:
    """Largest angle (degrees) between viewing rays from the given frames to the point."""
    rays = []
    for i in frame_indices:
        pose = poses[i]
        if pose is None:
            continue
        ray = np.asarray(point, dtype=np.float64) - camera_center(pose)
        n = np.linalg.norm(ray)
        if n > 0:
            rays.append(ray / n)
    if len(rays) < 2:
        return 0.0
    rays = np.array(rays)
    cos = np.clip(rays @ rays.T, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos.min())))


# ---------------------------------------------------------------- crops

def save_evidence_crop(frame_path: str | Path, pixel: list[float], out_path: Path,
                       size: int = 256) -> Path | None:
    """Save a square crop of *frame_path* centred on *pixel*, with a marker ring."""
    import cv2
    img = cv2.imread(str(frame_path))
    if img is None:
        return None
    h, w = img.shape[:2]
    u, v = int(round(pixel[0])), int(round(pixel[1]))
    half = size // 2
    x0, y0 = max(0, min(w - size, u - half)), max(0, min(h - size, v - half))
    crop = img[y0:y0 + size, x0:x0 + size].copy()
    cv2.circle(crop, (u - x0, v - y0), max(6, size // 12), (0, 0, 255), 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return out_path


# ---------------------------------------------------------------- confidence

def score_confidence(signal: float, n_views: int, angle_spread_deg: float,
                     n_points: int | None) -> dict:
    """Combine evidence factors into a confidence score with its breakdown."""
    factors = {
        "signal": float(np.clip(signal, 0.0, 1.0)),
        "views": 1.0 - math.exp(-n_views / 4.0),
        "diversity": min(1.0, angle_spread_deg / 30.0),
        # Frame-only findings (no 3D points) get a neutral 0.5.
        "points": 0.5 if n_points is None else 1.0 - math.exp(-n_points / 50.0),
    }
    score = sum(CONFIDENCE_WEIGHTS[k] * v for k, v in factors.items())
    verified = n_views > 0
    if not verified:
        score = min(score, UNVERIFIED_CAP)
    score = float(np.clip(score, 0.01, 0.99))

    if not verified:
        level = "unverified"
    elif n_views >= 3 and factors["diversity"] >= 0.5:
        level = "strong"
    elif n_views >= 2:
        level = "moderate"
    else:
        level = "weak"

    return {
        "confidence": round(score, 3),
        "evidence_level": level,
        "confidence_factors": {k: round(v, 3) for k, v in factors.items()},
    }


def attach_evidence(anomaly: dict, poses: list, K: np.ndarray, image_size: tuple[int, int],
                    frame_paths: list | None, frame_timestamps: list[float] | None,
                    crops_dir: Path | None = None, max_frames: int = 8,
                    max_crops: int = 3) -> dict:
    """Add supporting frames, crops and an evidence-based confidence to *anomaly* (in place)."""
    pos = anomaly.get("position_enu")
    frames: list[dict] = []
    spread = 0.0
    if pos is not None and K is not None and poses:
        frames = find_supporting_frames(np.array(pos), poses, K, image_size,
                                        frame_paths, frame_timestamps, max_frames=max_frames)
        spread = viewing_angle_spread(np.array(pos), poses, [f["frame_index"] for f in frames])

    if crops_dir is not None:
        aid = anomaly.get("id", "anomaly")
        for rank, f in enumerate(frames[:max_crops]):
            if f.get("frame_path"):
                out = save_evidence_crop(f["frame_path"], f["pixel"],
                                         crops_dir / f"{aid}_f{f['frame_index']:04d}.jpg")
                if out is not None:
                    f["crop_path"] = str(out)

    anomaly["supporting_frames"] = frames
    anomaly["view_angle_spread_deg"] = round(spread, 1)
    anomaly.update(score_confidence(anomaly.get("signal_strength", 0.5), len(frames), spread,
                                    anomaly.get("num_points")))
    return anomaly
