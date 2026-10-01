"""
run_on_test_images.py

Runs the FlightPrint 3D reconstruction pipeline directly on the pre-extracted
testing/auair2019data/images frames (bypassing Stage 1 which expects a video).

Stages run:
  2 - Camera calibration (generic drone preset)
  3 - SIFT feature detection + matching
  4 - Pose estimation + sparse triangulation
  5 - Dense stereo reconstruction (multi-view stereo)

Then generates an interactive 3D map viewer: output/3d_map/index.html
"""

import sys
import os
import json
import time
from pathlib import Path

# Force UTF-8 output so Unicode log chars don't crash on cp1252 consoles
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Make pipeline importable
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Config
IMAGES_DIR = ROOT / "testing" / "auair2019data" / "images"
OUTPUT_DIR = ROOT / "output" / "test_run"
VIEWER_DIR = ROOT / "output" / "3d_map"
MAX_FRAMES = 60      # SfM scales O(n^2) - 60 frames is plenty
# Take consecutive frames from the START of the sorted list.
# The AuAir dataset has 32k+ frames across many sequences; striding
# picks frames from completely different scenes with zero visual overlap.
# Consecutive frames from the same sequence guarantee overlap for SfM.
FRAME_START = 0

print("=" * 60)
print("FlightPrint -- Running on AuAir test images")
print("=" * 60)

# Collect frames
all_images = sorted(IMAGES_DIR.glob("*.jpg"))
if not all_images:
    print(f"ERROR: No JPEGs found in {IMAGES_DIR}")
    sys.exit(1)

selected = all_images[FRAME_START : FRAME_START + MAX_FRAMES]
print(f"Found {len(all_images)} images -> using {len(selected)} consecutive "
      f"(frames {FRAME_START} to {FRAME_START + len(selected) - 1})")

# Bootstrap PipelineContext manually (skip Stage 1 - images already extracted)
from pipeline.utils.io import PipelineContext
from pipeline.scale_and_georef import detect_mode

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ctx = PipelineContext(
    video_path=Path("testing/auair2019data/images"),  # synthetic - not used
    metadata_path=None,
    output_dir=OUTPUT_DIR,
)
ctx.metadata = {}
ctx.frame_paths = selected
ctx.frame_timestamps = [float(i) for i in range(len(selected))]

# Set reconstruction mode (vision-only: no GPS or IMU available)
mode_decision = detect_mode({}, {})
ctx.mode_decision = mode_decision
ctx.reconstruction_mode = mode_decision.mode.value
ctx.scale_status = mode_decision.scale_status.value
print(f"Reconstruction mode: {ctx.reconstruction_mode}")

# Stage 2: Camera Calibration
print("\n[Stage 2] Camera calibration ...")
t0 = time.perf_counter()
from pipeline.stage2_calibration import calibrate_camera
ctx = calibrate_camera(ctx)
print(f"  OK  fx = {ctx.camera_matrix[0,0]:.1f} px  ({time.perf_counter()-t0:.1f}s)")

# Stage 3: Feature Detection & Matching
print("\n[Stage 3] Feature detection & matching ...")
t0 = time.perf_counter()
from pipeline.stage3_features import detect_and_match
ctx = detect_and_match(ctx, {"max_features": 2000, "match_neighbors": 4})
n_pairs = len(ctx.matches)
print(f"  OK  {n_pairs} matched pairs  ({time.perf_counter()-t0:.1f}s)")

# Stage 4: Pose Estimation
print("\n[Stage 4] Pose estimation & sparse triangulation ...")
t0 = time.perf_counter()
from pipeline.stage4_poses import estimate_poses
ctx = estimate_poses(ctx, {"use_bundle_adjustment": False})
n_poses = sum(1 for p in ctx.poses if p is not None)
n_sparse = len(ctx.sparse_cloud) if ctx.sparse_cloud is not None else 0
print(f"  OK  {n_poses}/{len(ctx.frame_paths)} poses,  {n_sparse} sparse points  ({time.perf_counter()-t0:.1f}s)")

# Stage 5: Dense Reconstruction
print("\n[Stage 5] Dense reconstruction ...")
t0 = time.perf_counter()
from pipeline.stage5_reconstruction import densify
ctx = densify(ctx, {"sample_frames": 20, "num_disparities": 64, "block_size": 11})
n_dense = len(ctx.dense_cloud) if ctx.dense_cloud is not None else 0
print(f"  OK  {n_dense} dense points  ({time.perf_counter()-t0:.1f}s)")

# Export point cloud to JSON for the WebGL viewer
print("\n[Export] Serialising scene for 3D viewer ...")
import numpy as np


def cloud_to_json(points, colors, max_pts=35000):
    """Downsample and encode a point cloud for the web viewer."""
    if len(points) == 0:
        return {"points": [], "colors": []}
    if len(points) > max_pts:
        idx = np.random.choice(len(points), max_pts, replace=False)
        points, colors = points[idx], colors[idx]
    # Normalise colors to [0,1]
    col = (colors.astype(float) / 255.0) if (colors.size > 0 and colors.max() > 1.5) else colors.astype(float)
    return {"points": points.tolist(), "colors": col.tolist()}


cloud = ctx.dense_cloud  if ctx.dense_cloud  is not None else np.empty((0, 3))
cols  = ctx.dense_colors if ctx.dense_colors is not None else np.empty((0, 3))
cloud_data = cloud_to_json(cloud, cols)

# Camera trajectory (world positions of each camera)
traj = []
for i, pose in enumerate(ctx.poses):
    if pose is None:
        continue
    R_c = pose[:3, :3]
    t_c = pose[:3, 3]
    cam_pos = (-R_c.T @ t_c).tolist()
    traj.append({"frame": i, "position": cam_pos})

payload = {
    "point_cloud": cloud_data,
    "trajectory": traj,
    "n_frames": len(ctx.frame_paths),
    "n_poses": n_poses,
    "n_sparse": n_sparse,
    "n_dense": n_dense,
    "mode": ctx.reconstruction_mode,
}

VIEWER_DIR.mkdir(parents=True, exist_ok=True)
data_path = VIEWER_DIR / "scene_data.json"
with open(data_path, "w") as f:
    json.dump(payload, f)
print(f"  OK  Scene data -> {data_path}")

# Build the HTML viewer
from build_viewer import build_viewer
viewer_path = build_viewer(VIEWER_DIR)

# Summary
print("\n" + "=" * 60)
print("DONE!")
print(f"  Frames used:     {len(ctx.frame_paths)}")
print(f"  Poses estimated: {n_poses}")
print(f"  Sparse points:   {n_sparse}")
print(f"  Dense points:    {n_dense}")
print(f"  3D map viewer:   {viewer_path}")
print("=" * 60)
print(f"\nOpen in browser:")
print(f"  {viewer_path.as_uri()}")
