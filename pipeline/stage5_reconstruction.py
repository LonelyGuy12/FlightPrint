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
    "num_disparities": 64,
    "block_size": 11,
    "min_disparity": 0,
    "depth_max": 200.0,       # meters
    "depth_min": 1.0,         # meters
    "sample_frames": 30,      # Use a subset for dense reconstruction
    "voxel_size": 0.1,        # meters, for downsampling
}


def compute_depth_map_stereo(frame_a: np.ndarray, frame_b: np.ndarray,
                              pose_a: np.ndarray, pose_b: np.ndarray,
                              camera_matrix: np.ndarray, config: dict) -> np.ndarray | None:
    """Compute a depth map between two frames using stereo rectification.
    
    This is a simplified approach for the MVP — a full multi-view stereo
    system (like OpenMVS) would produce better results.
    """
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)

    # Relative pose
    R_rel = pose_b[:3, :3] @ pose_a[:3, :3].T
    t_rel = pose_b[:3, 3] - R_rel @ pose_a[:3, 3]

    baseline = np.linalg.norm(t_rel)
    if baseline < 0.01:
        return None

    # Stereo rectification
    h, w = gray_a.shape
    dist = np.zeros(5)

    try:
        R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
            camera_matrix, dist, camera_matrix, dist,
            (w, h), R_rel, t_rel.reshape(3, 1),
            flags=cv2.CALIB_ZERO_DISPARITY,
            alpha=0,
        )
    except cv2.error:
        return None

    map1a, map2a = cv2.initUndistortRectifyMap(camera_matrix, dist, R1, P1, (w, h), cv2.CV_32FC1)
    map1b, map2b = cv2.initUndistortRectifyMap(camera_matrix, dist, R2, P2, (w, h), cv2.CV_32FC1)

    rect_a = cv2.remap(gray_a, map1a, map2a, cv2.INTER_LINEAR)
    rect_b = cv2.remap(gray_b, map1b, map2b, cv2.INTER_LINEAR)

    # Semi-global block matching
    stereo = cv2.StereoSGBM_create(
        minDisparity=config["min_disparity"],
        numDisparities=config["num_disparities"],
        blockSize=config["block_size"],
        P1=8 * config["block_size"] ** 2,
        P2=32 * config["block_size"] ** 2,
        disp12MaxDiff=1,
        uniquenessRatio=10,
        speckleWindowSize=100,
        speckleRange=32,
    )

    disparity = stereo.compute(rect_a, rect_b).astype(np.float32) / 16.0

    # Convert disparity to depth
    fx = camera_matrix[0, 0]
    depth = np.where(disparity > 0, fx * baseline / disparity, 0)

    # Clamp to valid range
    depth[(depth < config["depth_min"]) | (depth > config["depth_max"])] = 0

    return depth


def depth_map_to_points(depth: np.ndarray, frame: np.ndarray,
                        pose: np.ndarray, camera_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert a depth map to 3D points in world coordinates with colors."""
    h, w = depth.shape
    fx, fy = camera_matrix[0, 0], camera_matrix[1, 1]
    cx, cy = camera_matrix[0, 2], camera_matrix[1, 2]

    # Create pixel grid
    u, v = np.meshgrid(np.arange(w), np.arange(h))

    # Valid depth mask
    mask = depth > 0

    # Backproject to camera coordinates
    z = depth[mask]
    x = (u[mask] - cx) * z / fx
    y = (v[mask] - cy) * z / fy

    points_cam = np.stack([x, y, z], axis=-1)

    # Transform to world coordinates
    R_cam = pose[:3, :3]
    t_cam = pose[:3, 3]
    points_world = (R_cam.T @ (points_cam - t_cam).T).T

    # Colors from frame
    colors = frame[mask][:, ::-1]  # BGR → RGB

    return points_world, colors


@log_stage("dense_reconstruction")
def densify(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Create a denser point cloud using multi-view stereo depth estimation.
    
    Uses stereo pairs from the estimated poses to compute depth maps,
    then fuses them into a single dense point cloud.
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

    # Start with sparse cloud
    if ctx.sparse_cloud is not None and len(ctx.sparse_cloud) > 0:
        all_points.append(ctx.sparse_cloud)
        all_colors.append(ctx.sparse_colors)

    pairs_processed = 0
    for k in range(len(sampled) - 1):
        i, j = sampled[k], sampled[k + 1]

        frame_a = cv2.imread(str(ctx.frame_paths[i]))
        frame_b = cv2.imread(str(ctx.frame_paths[j]))
        if frame_a is None or frame_b is None:
            continue

        depth = compute_depth_map_stereo(
            frame_a, frame_b,
            ctx.poses[i], ctx.poses[j],
            ctx.camera_matrix, cfg
        )

        if depth is None or np.count_nonzero(depth) < 100:
            continue

        # Subsample depth map for speed (every 4th pixel)
        depth_sub = depth[::4, ::4]
        frame_sub = frame_a[::4, ::4]

        K_sub = ctx.camera_matrix.copy()
        K_sub[0, :] /= 4
        K_sub[1, :] /= 4

        pts, cols = depth_map_to_points(depth_sub, frame_sub, ctx.poses[i], K_sub)

        if len(pts) > 0:
            all_points.append(pts)
            all_colors.append(cols)
            pairs_processed += 1

        if (k + 1) % 5 == 0:
            total_pts = sum(len(p) for p in all_points)
            log.info(f"Processed {k + 1}/{len(sampled) - 1} pairs ({total_pts} total points)")

    if all_points:
        dense_cloud = np.vstack(all_points)
        dense_colors = np.vstack(all_colors)
    else:
        dense_cloud = ctx.sparse_cloud if ctx.sparse_cloud is not None else np.empty((0, 3))
        dense_colors = ctx.sparse_colors if ctx.sparse_colors is not None else np.empty((0, 3))

    log.info(f"Dense cloud: {len(dense_cloud)} points from {pairs_processed} stereo pairs")

    # Simple voxel downsampling
    if len(dense_cloud) > 100000:
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
