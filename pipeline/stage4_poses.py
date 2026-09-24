"""Stage 4: Pose Estimation with Mode-Aware Scale Recovery.

Estimates camera poses (position + orientation) for each frame by:
1. Computing relative poses from essential matrix decomposition
2. Delegating scale/georef to ``scale_and_georef.apply_scale_and_georef``
   which branches per the detected mode (FULL / SCALE_ASSISTED / VISION_ONLY)
3. Triangulating a sparse point cloud from matched features

The core visual odometry chain (essential matrix → chained poses →
triangulation) is mode-agnostic.  Only the *scale recovery* step
changes depending on available metadata.
"""

import cv2
import numpy as np
from pathlib import Path
from scipy.spatial.transform import Rotation as R
from scipy.optimize import least_squares

from .utils.logging import get_logger, log_stage
from .utils.io import PipelineContext
from .scale_and_georef import apply_scale_and_georef


# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "essential_ransac_thresh": 1.0,   # pixels
    "pnp_ransac_thresh": 8.0,        # pixels
    "min_inliers": 15,               # minimum inliers for valid pose
    "gps_weight": 10.0,              # Weight for GPS in fusion (higher = trust GPS more)
    "use_bundle_adjustment": True,    # Lightweight BA on sliding window
    "ba_window_size": 10,            # BA window
}


# ─── Relative Pose from Essential Matrix ──────────────────────────────────────

def estimate_relative_pose(kp_a, kp_b, matches, camera_matrix, config):
    """Estimate relative pose between two frames using the essential matrix.
    
    Returns:
        (R, t, inlier_mask) or None if estimation fails.
        R is 3x3 rotation, t is 3x1 translation (unit scale).
    """
    if len(matches) < 8:
        return None

    pts_a = np.float64([kp_a[m.queryIdx].pt for m in matches])
    pts_b = np.float64([kp_b[m.trainIdx].pt for m in matches])

    E, mask = cv2.findEssentialMat(
        pts_a, pts_b, camera_matrix,
        method=cv2.RANSAC,
        prob=0.999,
        threshold=config["essential_ransac_thresh"],
    )

    if E is None or mask is None:
        return None

    inlier_count = int(mask.sum())
    if inlier_count < config["min_inliers"]:
        return None

    # Recover pose (R, t) from essential matrix
    _, R_rel, t_rel, pose_mask = cv2.recoverPose(
        E, pts_a, pts_b, camera_matrix, mask=mask
    )

    return R_rel, t_rel, mask


def estimate_pose_pnp(points_3d, kp, matches_3d_to_2d, camera_matrix, dist_coeffs, config):
    """Estimate absolute pose using PnP from known 3D points.
    
    Args:
        points_3d: Nx3 array of triangulated 3D points.
        kp: Keypoints in the target frame.
        matches_3d_to_2d: List of (3d_idx, keypoint_idx) correspondences.
        camera_matrix: 3x3 intrinsic matrix.
        dist_coeffs: Distortion coefficients.
        config: Configuration dict.
    
    Returns:
        4x4 world-to-camera transform or None.
    """
    if len(matches_3d_to_2d) < 6:
        return None

    obj_pts = np.array([points_3d[i] for i, _ in matches_3d_to_2d], dtype=np.float64)
    img_pts = np.array([kp[j].pt for _, j in matches_3d_to_2d], dtype=np.float64)

    success, rvec, tvec, inliers = cv2.solvePnPRansac(
        obj_pts, img_pts, camera_matrix, dist_coeffs,
        iterationsCount=300,
        reprojectionError=config["pnp_ransac_thresh"],
        flags=cv2.SOLVEPNP_ITERATIVE,
    )

    if not success or inliers is None or len(inliers) < config["min_inliers"]:
        return None

    R_mat, _ = cv2.Rodrigues(rvec)
    pose = np.eye(4)
    pose[:3, :3] = R_mat
    pose[:3, 3] = tvec.ravel()

    return pose


# ─── GPS Fusion ───────────────────────────────────────────────────────────────

def fuse_poses_with_gps(visual_poses: list, frame_timestamps: list[float],
                        gps_track: list[dict], config: dict) -> tuple[list, dict]:
    """Fuse visual odometry poses with GPS track to establish absolute scale.
    
    The key insight: visual odometry gives relative poses up to an unknown
    scale factor. GPS gives absolute positions but with noise. We:
    
    1. Interpolate GPS positions at frame timestamps
    2. Convert GPS to local ENU coordinates
    3. Compute scale factor by comparing VO distances with GPS distances
    4. Apply Sim(3) alignment (scale + rotation + translation) to align
       the VO trajectory with GPS
    
    Returns:
        (aligned_poses, geo_origin) — poses in ENU coordinates, and the
        GPS origin used for the ENU transform.
    """
    if not gps_track:
        return visual_poses, {}

    # Interpolate GPS at frame timestamps
    gps_at_frames = []
    for ts in frame_timestamps:
        gps_pt = interpolate_gps(gps_track, ts)
        gps_at_frames.append(gps_pt)

    # Convert GPS to local ENU
    gps_enu, origin = gps_to_local_enu(gps_at_frames)

    # Collect valid VO positions (frames with estimated poses)
    vo_positions = []
    gps_positions = []
    valid_indices = []

    for i, pose in enumerate(visual_poses):
        if pose is not None and i < len(gps_enu):
            # Camera position from pose (inverse of extrinsic)
            R_cam = pose[:3, :3]
            t_cam = pose[:3, 3]
            cam_pos = -R_cam.T @ t_cam
            vo_positions.append(cam_pos)
            gps_positions.append(gps_enu[i])
            valid_indices.append(i)

    if len(vo_positions) < 3:
        # Not enough poses for alignment — just use GPS directly
        aligned = []
        for i, pose in enumerate(visual_poses):
            if pose is not None and i < len(gps_enu):
                new_pose = pose.copy()
                # Set translation to GPS position
                R_cam = new_pose[:3, :3]
                new_pose[:3, 3] = -R_cam @ gps_enu[i]
                aligned.append(new_pose)
            else:
                aligned.append(pose)
        return aligned, {"lat": origin["lat"], "lon": origin["lon"], "alt": origin["alt"]}

    vo_pts = np.array(vo_positions)
    gps_pts = np.array(gps_positions)

    # ── Sim(3) alignment: find scale, rotation, translation ──
    # that maps VO coordinates to GPS/ENU coordinates
    aligned_poses = sim3_alignment(visual_poses, vo_pts, gps_pts, valid_indices)

    return aligned_poses, {"lat": origin["lat"], "lon": origin["lon"], "alt": origin["alt"]}


def sim3_alignment(poses: list, src_pts: np.ndarray, dst_pts: np.ndarray,
                   valid_indices: list) -> list:
    """Compute Sim(3) alignment from source to destination point sets.
    
    Finds scale (s), rotation (R), translation (t) that minimizes:
        ||dst - (s * R @ src + t)||^2
    
    Uses Umeyama algorithm.
    """
    n = len(src_pts)
    if n < 3:
        return poses

    # Centroids
    mu_src = src_pts.mean(axis=0)
    mu_dst = dst_pts.mean(axis=0)

    # Center the points
    src_c = src_pts - mu_src
    dst_c = dst_pts - mu_dst

    # Covariance matrix
    H = src_c.T @ dst_c / n

    U, S, Vt = np.linalg.svd(H)

    # Rotation
    d = np.linalg.det(Vt.T @ U.T)
    D = np.diag([1, 1, np.sign(d)])
    R_align = Vt.T @ D @ U.T

    # Scale
    var_src = np.sum(src_c ** 2) / n
    scale = np.sum(S * np.diag(D)) / var_src if var_src > 1e-10 else 1.0

    # Translation
    t_align = mu_dst - scale * R_align @ mu_src

    # Apply Sim(3) to all poses
    aligned = []
    for i, pose in enumerate(poses):
        if pose is None:
            aligned.append(None)
            continue

        new_pose = np.eye(4)

        # Transform rotation
        R_cam = pose[:3, :3]
        t_cam = pose[:3, 3]

        # Camera center in original coords
        center = -R_cam.T @ t_cam

        # Transform center to GPS/ENU coords
        new_center = scale * R_align @ center + t_align

        # Transform rotation
        new_R = R_cam @ R_align.T

        new_pose[:3, :3] = new_R
        new_pose[:3, 3] = -new_R @ new_center

        aligned.append(new_pose)

    return aligned


# ─── IMU Fusion ───────────────────────────────────────────────────────────────

def apply_imu_orientation(poses: list, frame_timestamps: list[float],
                          imu_data: list[dict]) -> list:
    """Refine pose orientations using IMU (roll, pitch, yaw) data.
    
    IMU provides absolute orientation that can correct for visual odometry
    drift in rotation estimates.
    """
    if not imu_data:
        return poses

    refined = []
    for i, pose in enumerate(poses):
        if pose is None:
            refined.append(None)
            continue

        ts = frame_timestamps[i] if i < len(frame_timestamps) else None
        if ts is None:
            refined.append(pose)
            continue

        # Find nearest IMU reading
        imu_reading = _find_nearest_imu(imu_data, ts)
        if imu_reading is None:
            refined.append(pose)
            continue

        # Convert IMU Euler angles to rotation matrix
        roll = imu_reading.get("roll", 0.0)
        pitch = imu_reading.get("pitch", 0.0)
        yaw = imu_reading.get("yaw", 0.0)

        R_imu = R.from_euler("xyz", [roll, pitch, yaw], degrees=True).as_matrix()

        # Blend: weighted average using SLERP-like approach
        # For now, use IMU for yaw (most reliable from magnetometer)
        # and keep visual rotation for roll/pitch
        R_visual = pose[:3, :3]
        
        # Extract yaw from IMU, roll/pitch from visual
        r_visual = R.from_matrix(R_visual)
        euler_visual = r_visual.as_euler("xyz", degrees=True)
        
        blended_euler = [euler_visual[0], euler_visual[1], yaw]
        R_blended = R.from_euler("xyz", blended_euler, degrees=True).as_matrix()

        new_pose = pose.copy()
        new_pose[:3, :3] = R_blended
        refined.append(new_pose)

    return refined


def _find_nearest_imu(imu_data: list[dict], timestamp: float) -> dict | None:
    """Find the IMU reading closest to a given timestamp."""
    if not imu_data:
        return None

    best = None
    best_dt = float("inf")

    for reading in imu_data:
        dt = abs(reading.get("timestamp", 0) - timestamp)
        if dt < best_dt:
            best_dt = dt
            best = reading

    # Don't use if too far away (> 0.5s)
    if best_dt > 0.5:
        return None

    return best


# ─── Triangulation of Sparse Points ──────────────────────────────────────────

def triangulate_points(poses: list, keypoints: list, matches: dict,
                       camera_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Triangulate matched feature points across frame pairs.
    
    Returns:
        (points_3d, colors) — Nx3 point cloud and Nx3 RGB colors.
    """
    all_points = []
    all_colors = []

    for (i, j), match_list in matches.items():
        if poses[i] is None or poses[j] is None:
            continue
        if len(match_list) < 10:
            continue

        # Projection matrices: P = K @ [R|t]
        P1 = camera_matrix @ poses[i][:3, :]
        P2 = camera_matrix @ poses[j][:3, :]

        pts_a = np.float64([keypoints[i][m.queryIdx].pt for m in match_list])
        pts_b = np.float64([keypoints[j][m.trainIdx].pt for m in match_list])

        # Triangulate
        points_4d = cv2.triangulatePoints(P1, P2, pts_a.T, pts_b.T)
        points_3d = (points_4d[:3] / points_4d[3:]).T

        # Filter: remove points behind cameras or too far away
        for k, pt in enumerate(points_3d):
            # Check if point is in front of both cameras
            pt_cam1 = poses[i][:3, :3] @ pt + poses[i][:3, 3]
            pt_cam2 = poses[j][:3, :3] @ pt + poses[j][:3, 3]

            if pt_cam1[2] > 0 and pt_cam2[2] > 0:
                # Check reasonable distance (< 500m from camera)
                if np.linalg.norm(pt_cam1) < 500 and np.linalg.norm(pt_cam2) < 500:
                    all_points.append(pt)
                    # Default color (will be textured later)
                    all_colors.append([128, 128, 128])

    if all_points:
        return np.array(all_points), np.array(all_colors)
    return np.empty((0, 3)), np.empty((0, 3))


def color_points_from_frames(points_3d: np.ndarray, poses: list,
                              frame_paths: list, camera_matrix: np.ndarray) -> np.ndarray:
    """Project 3D points back into frames to get their color."""
    if len(points_3d) == 0:
        return np.empty((0, 3))

    colors = np.full((len(points_3d), 3), 128, dtype=np.uint8)
    color_counts = np.zeros(len(points_3d), dtype=int)

    # Sample a subset of frames for speed
    frame_indices = list(range(0, len(poses), max(1, len(poses) // 20)))

    for idx in frame_indices:
        if poses[idx] is None or idx >= len(frame_paths):
            continue

        img = cv2.imread(str(frame_paths[idx]))
        if img is None:
            continue

        h, w = img.shape[:2]
        R_cam = poses[idx][:3, :3]
        t_cam = poses[idx][:3, 3]

        # Project all points into this frame
        pts_cam = (R_cam @ points_3d.T + t_cam.reshape(3, 1)).T

        # Keep points in front of camera
        mask_front = pts_cam[:, 2] > 0

        if not mask_front.any():
            continue

        # Project to image
        pts_proj = (camera_matrix @ pts_cam[mask_front].T).T
        pts_2d = pts_proj[:, :2] / pts_proj[:, 2:3]

        # Get valid pixel coords
        valid_x = (pts_2d[:, 0] >= 0) & (pts_2d[:, 0] < w)
        valid_y = (pts_2d[:, 1] >= 0) & (pts_2d[:, 1] < h)
        valid = valid_x & valid_y

        front_indices = np.where(mask_front)[0]

        for sub_idx in np.where(valid)[0]:
            global_idx = front_indices[sub_idx]
            px = int(pts_2d[sub_idx, 0])
            py = int(pts_2d[sub_idx, 1])
            color = img[py, px]  # BGR
            colors[global_idx] = [color[2], color[1], color[0]]  # RGB
            color_counts[global_idx] += 1

    return colors


# ─── Main Stage ───────────────────────────────────────────────────────────────

@log_stage("pose_estimation")
def estimate_poses(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Estimate camera poses with mode-aware scale recovery.

    Pipeline:
    1. Initialize first camera at origin
    2. For each subsequent frame, estimate relative pose from essential matrix
    3. Chain relative poses to get trajectory
    4. Call ``apply_scale_and_georef`` which handles FULL / SCALE_ASSISTED /
       VISION_ONLY modes internally (GPS fusion, altitude scaling, or no-op)
    5. Triangulate sparse point cloud from matched features
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log = get_logger("pose_estimation", ctx.output_dir)

    n_frames = len(ctx.frame_paths)
    K = ctx.camera_matrix

    if K is None:
        raise RuntimeError("Camera matrix not set — run stage 2 first")
    if not ctx.matches:
        raise RuntimeError("No matches available — run stage 3 first")

    log.info(f"Estimating poses for {n_frames} frames...")

    # ── Step 1: Initialize poses from chained relative transforms ──
    poses = [None] * n_frames

    # First frame at origin
    poses[0] = np.eye(4)
    estimated_count = 1

    for i in range(1, n_frames):
        # Try matching with previous estimated frames (nearest first)
        best_pose = None
        best_inliers = 0

        for offset in range(1, min(i + 1, cfg.get("match_neighbors", 5) + 1)):
            j = i - offset
            if poses[j] is None:
                continue
            if (j, i) not in ctx.matches:
                continue

            result = estimate_relative_pose(
                ctx.keypoints[j], ctx.keypoints[i],
                ctx.matches[(j, i)], K, cfg
            )

            if result is None:
                continue

            R_rel, t_rel, mask = result
            inlier_count = int(mask.sum()) if mask is not None else 0

            if inlier_count > best_inliers:
                # Chain: pose_i = relative @ pose_j
                rel_pose = np.eye(4)
                rel_pose[:3, :3] = R_rel
                rel_pose[:3, 3] = t_rel.ravel()

                best_pose = rel_pose @ poses[j]
                best_inliers = inlier_count

        if best_pose is not None:
            poses[i] = best_pose
            estimated_count += 1
        else:
            log.warning(f"Frame {i}: could not estimate pose (no valid matches)")

    log.info(f"Visual odometry: {estimated_count}/{n_frames} poses estimated")

    # ── Step 2: Mode-aware scale & georeferencing ──
    mode_decision = ctx.mode_decision
    if mode_decision is None:
        # Fallback — shouldn't happen if runner sets it, but be safe
        from .scale_and_georef import detect_mode
        mode_decision = detect_mode(ctx.metadata, cfg)

    log.info(f"Reconstruction mode: {mode_decision.mode.value} "
             f"(scale: {mode_decision.scale_status.value})")
    for reason in mode_decision.reasons:
        log.info(f"  → {reason}")

    poses, geo_origin, pose_gps = apply_scale_and_georef(
        poses, ctx.frame_timestamps, ctx.metadata, K,
        mode_decision, ctx.output_dir,
    )

    ctx.poses = poses
    ctx.geo_origin = geo_origin
    ctx.pose_gps = pose_gps

    # ── Step 3: Triangulate sparse point cloud ──
    log.info("Triangulating sparse point cloud...")
    sparse_cloud, sparse_colors = triangulate_points(
        poses, ctx.keypoints, ctx.matches, K
    )

    if len(sparse_cloud) > 0:
        # Color points from original frames
        log.info(f"Coloring {len(sparse_cloud)} sparse points from frames...")
        sparse_colors = color_points_from_frames(
            sparse_cloud, poses, ctx.frame_paths, K
        )

    ctx.sparse_cloud = sparse_cloud
    ctx.sparse_colors = sparse_colors

    log.info(f"Sparse cloud: {len(sparse_cloud)} points")

    # ── Save outputs ──
    from .utils.io import save_point_cloud_ply, save_camera_trajectory

    if len(sparse_cloud) > 0:
        ply_path = ctx.output_dir / "sparse_cloud.ply"
        save_point_cloud_ply(ply_path, sparse_cloud, sparse_colors)
        log.info(f"Saved sparse cloud to {ply_path}")

    traj_path = ctx.output_dir / "camera_trajectory.json"
    save_camera_trajectory(
        traj_path, poses, ctx.frame_timestamps, ctx.pose_gps,
        mode_decision=mode_decision,
    )
    log.info(f"Saved camera trajectory to {traj_path}")

    return ctx
