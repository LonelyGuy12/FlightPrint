#!/usr/bin/env python3
"""Mid-Air -> FlightPrint adapter.

Converts one Mid-Air trajectory (JPEG frames + sensor_records.hdf5) into the
two inputs FlightPrint expects:

  trajectory.mp4   video stitched from the camera frames (25 fps)
  metadata.json    gps_track (lat/lon/alt), camera intrinsics, imu (roll/pitch/yaw, degrees)

It also writes groundtruth_poses.json (100 Hz ground-truth position + attitude)
so pose-estimation output can be checked for accuracy later.

Mid-Air facts this relies on (https://midair.ulg.ac.be/tech_specs.html):
  - Positions are NED metres in a World frame whose origin is the trajectory start.
  - Attitude is a quaternion; GPS is 1 Hz, IMU/ground truth are 100 Hz, cameras 25 Hz.
  - All cameras: fx = cx = w/2, fy = cy = h/2 (90 deg FOV), images are 1024x1024.

Usage:
  python tools/midair_adapter.py --climate-dir path/to/Kite_training/sunny \
      --trajectory 0 --out out/traj0

  # then
  python -m pipeline.cli --video out/traj0/trajectory.mp4 \
      --metadata out/traj0/metadata.json --output runs/traj0 --stages 1 2 3 4

Requires: numpy, h5py, opencv-python (ffmpeg is used if installed, for H.264).
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


VIDEO_FPS = 25.0
GPS_HZ = 1.0
IMU_HZ = 100.0
EARTH_RADIUS_M = 6378137.0  # WGS84 equatorial radius

# Default geo origin: Liege, Belgium (where Mid-Air was made). Any point works,
# since the scene is synthetic; override with --origin-lat/--origin-lon/--origin-alt.
DEFAULT_ORIGIN = (50.5833, 5.5667, 100.0)


# ---------------------------------------------------------------- geometry

def ned_to_geodetic(ned: np.ndarray, lat0: float, lon0: float, alt0: float) -> np.ndarray:
    """Convert Nx3 NED metres (relative to origin) to Nx3 [lat, lon, alt].

    Uses a local tangent-plane approximation, which is accurate to well under
    a centimetre over the few hundred metres a Mid-Air trajectory covers.
    """
    north, east, down = ned[:, 0], ned[:, 1], ned[:, 2]
    lat0_rad = math.radians(lat0)
    lat = lat0 + np.degrees(north / EARTH_RADIUS_M)
    lon = lon0 + np.degrees(east / (EARTH_RADIUS_M * math.cos(lat0_rad)))
    alt = alt0 - down  # NED "down" is positive toward the ground
    return np.stack([lat, lon, alt], axis=1)


def detect_quat_order(q0: np.ndarray) -> str:
    """Guess quaternion component order from the first sample.

    Mid-Air's World frame is aligned so the drone starts with yaw = 0, and it
    starts near level, so the first attitude is close to identity. Identity is
    (1,0,0,0) in wxyz order and (0,0,0,1) in xyzw order.
    """
    return "wxyz" if abs(q0[0]) >= abs(q0[3]) else "xyzw"


def quat_to_euler_deg(q: np.ndarray, order: str) -> np.ndarray:
    """Nx4 quaternions -> Nx3 [roll, pitch, yaw] in degrees (aerospace ZYX)."""
    if order == "wxyz":
        w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    else:
        x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    norm = np.sqrt(w * w + x * x + y * y + z * z)
    norm[norm == 0] = 1.0
    w, x, y, z = w / norm, x / norm, y / norm, z / norm

    roll = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = np.arcsin(np.clip(2 * (w * y - z * x), -1.0, 1.0))
    yaw = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return np.degrees(np.stack([roll, pitch, yaw], axis=1))


# ---------------------------------------------------------------- hdf5 helpers

def _decode(p) -> str:
    return p.decode() if isinstance(p, (bytes, np.bytes_)) else str(p)


def find_trajectory_group(h5, trajectory: str):
    names = list(h5.keys())
    candidates = [trajectory, f"trajectory_{trajectory}"]
    if trajectory.isdigit():
        candidates.append(f"trajectory_{int(trajectory):04d}")
    for c in candidates:
        if c in h5:
            return h5[c]
    sys.exit(f"Trajectory '{trajectory}' not found. Available: {', '.join(names[:20])}"
             + (" ..." if len(names) > 20 else ""))


# ---------------------------------------------------------------- video

def write_video(frame_paths: list[Path], out_path: Path, fps: float) -> None:
    missing = [p for p in frame_paths if not p.exists()]
    if missing:
        sys.exit(f"{len(missing)} frame files missing, e.g. {missing[0]}. "
                 "Did you download the camera you selected (--camera)?")

    if shutil.which("ffmpeg"):
        # Symlink frames into a clean numbered sequence so ffmpeg can read them.
        with tempfile.TemporaryDirectory() as tmp:
            ext = frame_paths[0].suffix
            for i, p in enumerate(frame_paths):
                (Path(tmp) / f"{i:06d}{ext}").symlink_to(p.resolve())
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                   "-i", str(Path(tmp) / f"%06d{ext}"),
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out_path)]
            if subprocess.run(cmd).returncode == 0:
                return
            print("ffmpeg failed, falling back to OpenCV writer", file=sys.stderr)

    import cv2
    first = cv2.imread(str(frame_paths[0]))
    if first is None:
        sys.exit(f"Could not read {frame_paths[0]}")
    h, w = first.shape[:2]
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for p in frame_paths:
        img = cv2.imread(str(p))
        if img is None:
            sys.exit(f"Could not read {p}")
        writer.write(img)
    writer.release()


def image_size(path: Path) -> tuple[int, int]:
    import cv2
    img = cv2.imread(str(path))
    if img is None:
        sys.exit(f"Could not read {path}")
    return img.shape[1], img.shape[0]


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--climate-dir", required=True, type=Path,
                    help="Folder containing sensor_records.hdf5 and the color_* folders")
    ap.add_argument("--trajectory", required=True, help="Trajectory number or group name, e.g. 0 or trajectory_0000")
    ap.add_argument("--out", required=True, type=Path, help="Output folder")
    ap.add_argument("--camera", default="color_left", choices=["color_left", "color_right", "color_down"])
    ap.add_argument("--max-seconds", type=float, default=None, help="Only convert the first N seconds")
    ap.add_argument("--position-source", default="gps", choices=["gps", "groundtruth"],
                    help="gps = noisy 1 Hz simulated GPS (realistic); groundtruth = exact 100 Hz positions")
    ap.add_argument("--imu-rate", type=float, default=25.0,
                    help="Rate (Hz) to downsample attitude to for metadata.json (default: one per frame)")
    ap.add_argument("--quat-order", default="auto", choices=["auto", "wxyz", "xyzw"])
    ap.add_argument("--origin-lat", type=float, default=DEFAULT_ORIGIN[0])
    ap.add_argument("--origin-lon", type=float, default=DEFAULT_ORIGIN[1])
    ap.add_argument("--origin-alt", type=float, default=DEFAULT_ORIGIN[2],
                    help="Altitude (m) assigned to the trajectory start point")
    ap.add_argument("--skip-video", action="store_true", help="Only write the JSON files")
    args = ap.parse_args()

    try:
        import h5py
    except ImportError:
        sys.exit("h5py is required: pip install h5py")

    h5_path = args.climate_dir / "sensor_records.hdf5"
    if not h5_path.exists():
        sys.exit(f"Not found: {h5_path}")
    args.out.mkdir(parents=True, exist_ok=True)

    with h5py.File(h5_path, "r") as h5:
        traj = find_trajectory_group(h5, args.trajectory)
        print(f"Using {traj.name}")

        # --- frames
        frame_rel = [_decode(p) for p in traj["camera_data"][args.camera][()]]
        if args.max_seconds:
            frame_rel = frame_rel[: int(args.max_seconds * VIDEO_FPS)]
        frame_paths = [args.climate_dir / p for p in frame_rel]
        duration = len(frame_paths) / VIDEO_FPS

        # --- positions
        if args.position_source == "gps":
            pos = np.asarray(traj["gps"]["position"][()], dtype=np.float64)
            pos_hz = GPS_HZ
        else:
            pos = np.asarray(traj["groundtruth"]["position"][()], dtype=np.float64)
            pos_hz = IMU_HZ
        n_pos = min(len(pos), int(math.floor(duration * pos_hz)) + 1)
        pos = pos[:n_pos]
        pos_t = np.arange(n_pos) / pos_hz

        # --- attitude
        att = np.asarray(traj["groundtruth"]["attitude"][()], dtype=np.float64)
        n_att = min(len(att), int(math.floor(duration * IMU_HZ)) + 1)
        att = att[:n_att]
        att_t = np.arange(n_att) / IMU_HZ
        gt_pos = np.asarray(traj["groundtruth"]["position"][()], dtype=np.float64)[:n_att]

    order = detect_quat_order(att[0]) if args.quat_order == "auto" else args.quat_order
    print(f"Quaternion order: {order}  (first sample {np.round(att[0], 3).tolist()})")
    euler = quat_to_euler_deg(att, order)
    geo = ned_to_geodetic(pos, args.origin_lat, args.origin_lon, args.origin_alt)

    step = max(1, int(round(IMU_HZ / args.imu_rate)))
    imu_idx = np.arange(0, n_att, step)

    width, height = image_size(frame_paths[0]) if frame_paths else (1024, 1024)
    metadata = {
        "gps_track": [
            {"timestamp": round(float(t), 4), "lat": float(g[0]), "lon": float(g[1]), "alt": round(float(g[2]), 3)}
            for t, g in zip(pos_t, geo)
        ],
        "camera": {
            # Mid-Air: fx = w/2. FlightPrint computes fx = focal_mm / sensor_mm * w,
            # so any focal/sensor ratio of 0.5 is exact; 18/36 is used here.
            "focal_length_mm": 18.0,
            "sensor_width_mm": 36.0,
            "focal_length_px": width / 2.0,
            "cx": width / 2.0,
            "cy": height / 2.0,
            "image_width": width,
            "image_height": height,
            "distortion": [0, 0, 0, 0, 0],
        },
        "imu": [
            {"timestamp": round(float(att_t[i]), 4),
             "roll": round(float(euler[i, 0]), 4),
             "pitch": round(float(euler[i, 1]), 4),
             "yaw": round(float(euler[i, 2]), 4)}
            for i in imu_idx
        ],
        "source": {
            "dataset": "Mid-Air (CC BY-NC-SA 4.0, https://midair.ulg.ac.be)",
            "climate_dir": str(args.climate_dir),
            "trajectory": traj.name.strip("/"),
            "camera": args.camera,
            "position_source": args.position_source,
            "geo_origin": {"lat": args.origin_lat, "lon": args.origin_lon, "alt": args.origin_alt},
            "quaternion_order": order,
            "note": "Positions converted from local NED metres; origin is arbitrary.",
        },
    }
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=1))

    groundtruth = {
        "frame": "NED metres relative to trajectory start; attitude as roll/pitch/yaw degrees",
        "rate_hz": IMU_HZ,
        "poses": [
            {"timestamp": round(float(att_t[i]), 4),
             "north": float(gt_pos[i, 0]), "east": float(gt_pos[i, 1]), "down": float(gt_pos[i, 2]),
             "roll": float(euler[i, 0]), "pitch": float(euler[i, 1]), "yaw": float(euler[i, 2])}
            for i in range(min(len(gt_pos), n_att))
        ],
    }
    (args.out / "groundtruth_poses.json").write_text(json.dumps(groundtruth))

    if not args.skip_video:
        print(f"Writing video from {len(frame_paths)} frames ({duration:.1f}s)...")
        write_video(frame_paths, args.out / "trajectory.mp4", VIDEO_FPS)

    print(f"Done -> {args.out}")
    print(f"  {len(metadata['gps_track'])} GPS points, {len(metadata['imu'])} IMU samples, "
          f"{width}x{height} @ {VIDEO_FPS:g} fps, {duration:.1f}s")


if __name__ == "__main__":
    main()
