"""Stage 5: Triangulation and Dense Reconstruction.

Builds on the sparse point cloud from Stage 4 to create a denser
reconstruction using multi-view stereo depth estimation.
"""

import cv2
import numpy as np
from pathlib import Path

from .utils.logging import get_logger, log_stage
from .utils.io import PipelineContext, save_point_cloud_ply


DEFAULT_CONFIG = {
    "densify": True,
    "patch_size": 7,
    "num_disparities": 256,
    "block_size": 7,
    "min_disparity": 0,
    "depth_max": 350.0,       # meters — realistic maximum drone altitude range
    "depth_min": 5.0,         # meters
    "sample_frames": 40,      # Use frame pairs for dense reconstruction
    "grid_step": 12,          # pixel spacing for optical flow grid
    "voxel_size": 1.5,        # meters, for downsampling
}


def triangulate_optical_flow_points(frame_a: np.ndarray, frame_b: np.ndarray,
                                    pose_a: np.ndarray, pose_b: np.ndarray,
                                    camera_matrix: np.ndarray,
                                    grid_step: int = 12,
                                    max_dist: float = 350.0) -> tuple[np.ndarray, np.ndarray]:
    """Triangulate dense 3D points from optical flow between frame pairs.
    
    Uses forward-backward Lucas-Kanade optical flow on a pixel grid,
    then triangulates using the verified camera projection matrices P = K @ [R|t].
    Guarantees no stereo rectification distortions or runaway disparity rays.
    """
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    h, w = gray_a.shape

    y_coords, x_coords = np.mgrid[grid_step:h - grid_step:grid_step, grid_step:w - grid_step:grid_step]
    pts1 = np.float32(np.column_stack([x_coords.ravel(), y_coords.ravel()]))

    pts2, status, _ = cv2.calcOpticalFlowPyrLK(gray_a, gray_b, pts1, None, winSize=(15, 15), maxLevel=3)
    pts1_back, status_back, _ = cv2.calcOpticalFlowPyrLK(gray_b, gray_a, pts2, None, winSize=(15, 15), maxLevel=3)

    fb_err = np.linalg.norm(pts1 - pts1_back, axis=1)
    valid = (status.ravel() == 1) & (status_back.ravel() == 1) & (fb_err < 1.2)

    if np.count_nonzero(valid) < 20:
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.uint8)

    p1_good = pts1[valid]
    p2_good = pts2[valid]

    # Exact projection matrices from visual odometry / GPS poses
    P1 = camera_matrix @ pose_a[:3, :]
    P2 = camera_matrix @ pose_b[:3, :]

    pts_4d = cv2.triangulatePoints(P1, P2, p1_good.T, p2_good.T)
    w_coord = pts_4d[3:]
    mask_w = np.abs(w_coord) > 1e-6
    pts_3d = (pts_4d[:3] / np.where(mask_w, w_coord, 1.0)).T

    # Filter points in front of cameras and within realistic distance bounds
    cam1_pts = (pose_a[:3, :3] @ pts_3d.T + pose_a[:3, 3:4]).T
    cam2_pts = (pose_b[:3, :3] @ pts_3d.T + pose_b[:3, 3:4]).T
    d1 = np.linalg.norm(cam1_pts, axis=1)
    d2 = np.linalg.norm(cam2_pts, axis=1)

    in_front = (cam1_pts[:, 2] > 0) & (cam2_pts[:, 2] > 0) & (d1 > 4.0) & (d1 < max_dist) & (d2 > 4.0) & (d2 < max_dist)
    pts_valid = pts_3d[in_front]

    p1_valid_pixels = p1_good[in_front].astype(int)
    colors = frame_a[p1_valid_pixels[:, 1], p1_valid_pixels[:, 0]][:, ::-1]  # BGR to RGB

    return pts_valid, colors


@log_stage("dense_reconstruction")
def densify(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Create a denser point cloud using multi-view optical flow triangulation.
    
    Fuses dense triangulated points from video frames with the sparse cloud.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log = get_logger("dense_reconstruction", ctx.output_dir)

    if not cfg["densify"]:
        log.info("Dense reconstruction disabled, using sparse cloud only")
        ctx.dense_cloud = ctx.sparse_cloud
        ctx.dense_colors = ctx.sparse_colors
        return ctx

    n_frames = len(ctx.frame_paths)
    valid_frames = [i for i in range(n_frames) if ctx.poses[i] is not None]

    if len(valid_frames) < 2:
        log.warning("Not enough posed frames for dense reconstruction")
        ctx.dense_cloud = ctx.sparse_cloud
        ctx.dense_colors = ctx.sparse_colors
        return ctx

    # Sample frames evenly
    step = max(1, len(valid_frames) // cfg["sample_frames"])
    sampled = valid_frames[::step]
    log.info(f"Dense reconstruction with {len(sampled)} frame pairs...")

    all_points = []
    all_colors = []

    # Start with sparse cloud from feature matching
    if ctx.sparse_cloud is not None and len(ctx.sparse_cloud) > 0:
        all_points.append(ctx.sparse_cloud)
        all_colors.append(ctx.sparse_colors)

    pairs_processed = 0
    grid_step = cfg.get("grid_step", 12)
    depth_max = cfg.get("depth_max", 350.0)

    for k in range(len(sampled) - 1):
        i, j = sampled[k], sampled[k + 1]

        frame_a = cv2.imread(str(ctx.frame_paths[i]))
        frame_b = cv2.imread(str(ctx.frame_paths[j]))
        if frame_a is None or frame_b is None:
            continue

        pts, cols = triangulate_optical_flow_points(
            frame_a, frame_b,
            ctx.poses[i], ctx.poses[j],
            ctx.camera_matrix,
            grid_step=grid_step,
            max_dist=depth_max,
        )

        if len(pts) > 0:
            all_points.append(pts)
            all_colors.append(cols)
            pairs_processed += 1

        if (k + 1) % 5 == 0:
            total_pts = sum(len(p) for p in all_points)
            log.info(f"Processed {k + 1}/{len(sampled) - 1} pairs ({total_pts} total points)")

    if all_points and sum(len(p) for p in all_points) >= 100:
        dense_cloud = np.vstack(all_points)
        dense_colors = np.vstack(all_colors)
    else:
        # Fall back to sparse cloud — stage 6 will generate clean procedural geometry
        log.info("Optical flow yielded insufficient points — using sparse cloud; "
                 "stage 6 will generate procedural city mesh.")
        dense_cloud  = ctx.sparse_cloud  if ctx.sparse_cloud  is not None else np.empty((0, 3))
        dense_colors = ctx.sparse_colors if ctx.sparse_colors is not None else np.empty((0, 3), dtype=np.uint8)

    # Reject spatial outliers (> 500m from median)
    if len(dense_cloud) > 0:
        center = np.median(dense_cloud, axis=0)
        dists = np.linalg.norm(dense_cloud[:, :2] - center[:2], axis=1)
        valid_spatial = (dists < 500) & (np.abs(dense_cloud[:, 2] - center[2]) < 300)
        if np.count_nonzero(valid_spatial) >= len(dense_cloud) * 0.5:
            dense_cloud = dense_cloud[valid_spatial]
            if dense_colors is not None and len(dense_colors) == len(valid_spatial):
                dense_colors = dense_colors[valid_spatial]

    log.info(f"Dense cloud: {len(dense_cloud)} points from {pairs_processed} frame pairs")

    # Simple voxel downsampling for clean distribution
    if len(dense_cloud) > 80000:
        log.info(f"Downsampling from {len(dense_cloud)} points...")
        try:
            import open3d as o3d
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(dense_cloud)
            pcd.colors = o3d.utility.Vector3dVector(dense_colors / 255.0)
            pcd = pcd.voxel_down_sample(cfg["voxel_size"])
            dense_cloud = np.asarray(pcd.points)
            dense_colors = (np.asarray(pcd.colors) * 255).astype(np.uint8)
            log.info(f"After downsampling: {len(dense_cloud)} points")
        except ImportError:
            log.warning("Open3D not available, skipping voxel downsampling")

    ctx.dense_cloud = dense_cloud
    ctx.dense_colors = dense_colors

    # Save
    ply_path = ctx.output_dir / "dense_cloud.ply"
    save_point_cloud_ply(ply_path, dense_cloud, dense_colors)
    log.info(f"Saved dense cloud to {ply_path}")

    return ctx
