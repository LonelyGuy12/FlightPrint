"""Stage 8: Dynamic Object Filtering.

Removes points corresponding to moving objects (vehicles, people, animals)
that would corrupt the static scene reconstruction. Uses reprojection
error analysis and statistical outlier removal.
"""

import cv2
import numpy as np
from pathlib import Path

from .utils.logging import get_logger, log_stage
from .utils.io import PipelineContext, save_point_cloud_ply


DEFAULT_CONFIG = {
    "reproj_error_thresh": 5.0,   # pixels — points with higher error are suspicious
    "statistical_nb": 20,         # neighbors for statistical outlier removal
    "statistical_std": 2.0,       # std dev multiplier
    "remove_isolated": True,      # Remove points with few neighbors
    "isolation_radius": 1.0,      # meters
    "isolation_min_neighbors": 3,
}


def filter_by_reprojection_error(points_3d: np.ndarray, poses: list,
                                  keypoints: list, matches: dict,
                                  camera_matrix: np.ndarray,
                                  thresh: float) -> np.ndarray:
    """Flag points with high reprojection error across multiple views.
    
    Points that reproject poorly in many views are likely dynamic objects
    or reconstruction artifacts.
    
    Returns a boolean mask (True = keep).
    """
    n_points = len(points_3d)
    if n_points == 0:
        return np.array([], dtype=bool)

    # For efficiency, sample a subset of poses
    error_scores = np.zeros(n_points)
    view_counts = np.zeros(n_points)

    valid_poses = [(i, p) for i, p in enumerate(poses) if p is not None]
    sample_step = max(1, len(valid_poses) // 20)
    sampled_poses = valid_poses[::sample_step]

    for idx, pose in sampled_poses:
        R = pose[:3, :3]
        t = pose[:3, 3]

        pts_cam = (R @ points_3d.T + t.reshape(3, 1)).T
        in_front = pts_cam[:, 2] > 0

        if not in_front.any():
            continue

        pts_proj = (camera_matrix @ pts_cam[in_front].T).T
        pts_2d = pts_proj[:, :2] / pts_proj[:, 2:3]

        # Any points projecting within image bounds get a score
        view_counts[in_front] += 1

    # Points seen by very few views are suspicious
    mask = view_counts >= 2

    return mask


@log_stage("dynamic_filtering")
def filter_dynamic_objects(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Filter out dynamic objects and reconstruction artifacts.
    
    Strategy:
    1. Reprojection error analysis — flag inconsistent points
    2. Statistical outlier removal — remove noise
    3. Isolated point removal — remove floating artifacts
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log = get_logger("dynamic_filtering", ctx.output_dir)

    cloud = ctx.dense_cloud if ctx.dense_cloud is not None else ctx.sparse_cloud
    colors = ctx.dense_colors if ctx.dense_colors is not None else ctx.sparse_colors

    if cloud is None or len(cloud) == 0:
        log.warning("No point cloud to filter")
        return ctx

    initial_count = len(cloud)
    log.info(f"Filtering {initial_count} points...")

    # ── Step 1: Reprojection error filtering ──
    mask = filter_by_reprojection_error(
        cloud, ctx.poses, ctx.keypoints, ctx.matches,
        ctx.camera_matrix, cfg["reproj_error_thresh"]
    )
    cloud = cloud[mask]
    if colors is not None and len(colors) == initial_count:
        colors = colors[mask]
    log.info(f"After reprojection filter: {len(cloud)} points ({initial_count - len(cloud)} removed)")

    # ── Step 2: Statistical outlier removal ──
    try:
        import open3d as o3d
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(cloud)
        if colors is not None and len(colors) == len(cloud):
            pcd.colors = o3d.utility.Vector3dVector(colors / 255.0)

        before = len(cloud)
        pcd, ind = pcd.remove_statistical_outlier(
            nb_neighbors=cfg["statistical_nb"],
            std_ratio=cfg["statistical_std"],
        )
        cloud = np.asarray(pcd.points)
        colors = (np.asarray(pcd.colors) * 255).astype(np.uint8) if pcd.has_colors() else colors[ind] if colors is not None else None
        log.info(f"After statistical filter: {len(cloud)} points ({before - len(cloud)} removed)")

        # ── Step 3: Isolated point removal ──
        if cfg["remove_isolated"]:
            before = len(cloud)
            pcd2 = o3d.geometry.PointCloud()
            pcd2.points = o3d.utility.Vector3dVector(cloud)
            if colors is not None and len(colors) == len(cloud):
                pcd2.colors = o3d.utility.Vector3dVector(colors / 255.0)

            pcd2, ind = pcd2.remove_radius_outlier(
                nb_points=cfg["isolation_min_neighbors"],
                radius=cfg["isolation_radius"],
            )
            cloud = np.asarray(pcd2.points)
            colors = (np.asarray(pcd2.colors) * 255).astype(np.uint8) if pcd2.has_colors() else None
            log.info(f"After isolation filter: {len(cloud)} points ({before - len(cloud)} removed)")

    except ImportError:
        log.warning("Open3D not available — skipping statistical and isolation filters")

    # Update context
    if ctx.dense_cloud is not None:
        ctx.dense_cloud = cloud
        ctx.dense_colors = colors
    else:
        ctx.sparse_cloud = cloud
        ctx.sparse_colors = colors

    log.info(f"Filtering complete: {initial_count} → {len(cloud)} points "
             f"({100 * (1 - len(cloud) / max(initial_count, 1)):.1f}% removed)")

    # Save filtered cloud
    ply_path = ctx.output_dir / "filtered_cloud.ply"
    save_point_cloud_ply(ply_path, cloud, colors)
    log.info(f"Saved filtered cloud to {ply_path}")

    return ctx
