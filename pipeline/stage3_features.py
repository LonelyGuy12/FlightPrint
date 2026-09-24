"""Stage 3: Feature Detection and Matching.

Detects SIFT (preferred) or ORB features per frame and matches them across
sequential AND nearby frames (not just adjacent pairs) to handle motion blur
dropouts. Uses ratio test (Lowe's) for robust matching, plus geometric
verification via fundamental matrix RANSAC.
"""

import cv2
import numpy as np
from pathlib import Path
from itertools import combinations

from .utils.logging import get_logger, log_stage
from .utils.io import PipelineContext


# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "detector": "sift",           # "sift" or "orb"
    "max_features": 3000,         # Max features per frame
    "match_neighbors": 5,         # Match each frame with this many neighbors
    "ratio_thresh": 0.75,         # Lowe's ratio test threshold
    "min_matches": 20,            # Minimum good matches to keep a pair
    "ransac_thresh": 3.0,         # Fundamental matrix RANSAC threshold (pixels)
    "resize_for_features": 1920,  # Max width for feature detection
}


# ─── Feature Detection ───────────────────────────────────────────────────────

def create_detector(config: dict):
    """Create feature detector + descriptor extractor."""
    if config["detector"] == "sift":
        return cv2.SIFT_create(nfeatures=config["max_features"])
    elif config["detector"] == "orb":
        return cv2.ORB_create(nfeatures=config["max_features"])
    else:
        raise ValueError(f"Unknown detector: {config['detector']}")


def create_matcher(config: dict):
    """Create feature matcher appropriate for the detector."""
    if config["detector"] == "sift":
        # FLANN-based matcher for SIFT (float descriptors)
        index_params = dict(algorithm=1, trees=5)  # FLANN_INDEX_KDTREE
        search_params = dict(checks=50)
        return cv2.FlannBasedMatcher(index_params, search_params)
    else:
        # BFMatcher for ORB (binary descriptors)
        return cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)


def detect_features(frame_path: Path, detector, max_width: int) -> tuple:
    """Detect features in a single frame.
    
    Returns:
        (keypoints, descriptors, scale_factor) where scale_factor can be used
        to map keypoint coords back to original resolution.
    """
    img = cv2.imread(str(frame_path))
    if img is None:
        return [], None, 1.0

    h, w = img.shape[:2]
    scale = 1.0
    if w > max_width:
        scale = max_width / w
        img = cv2.resize(img, (max_width, int(h * scale)))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    keypoints, descriptors = detector.detectAndCompute(gray, None)

    # Scale keypoints back to original resolution
    if scale != 1.0:
        inv_scale = 1.0 / scale
        for kp in keypoints:
            kp.pt = (kp.pt[0] * inv_scale, kp.pt[1] * inv_scale)
            kp.size *= inv_scale

    return keypoints, descriptors, scale


def match_pair(desc_a: np.ndarray, desc_b: np.ndarray, 
               matcher, config: dict) -> list[cv2.DMatch]:
    """Match descriptors between two frames using ratio test.
    
    Returns list of good matches (after Lowe's ratio test).
    """
    if desc_a is None or desc_b is None:
        return []
    if len(desc_a) < 2 or len(desc_b) < 2:
        return []

    try:
        raw_matches = matcher.knnMatch(desc_a, desc_b, k=2)
    except cv2.error:
        return []

    # Lowe's ratio test
    good = []
    for match_pair in raw_matches:
        if len(match_pair) == 2:
            m, n = match_pair
            if m.distance < config["ratio_thresh"] * n.distance:
                good.append(m)

    return good


def geometric_verification(kp_a: list, kp_b: list, 
                           matches: list[cv2.DMatch],
                           config: dict) -> list[cv2.DMatch]:
    """Filter matches using fundamental matrix RANSAC.
    
    Removes matches that are geometrically inconsistent (epipolar geometry).
    """
    if len(matches) < 8:
        return matches

    pts_a = np.float32([kp_a[m.queryIdx].pt for m in matches])
    pts_b = np.float32([kp_b[m.trainIdx].pt for m in matches])

    F, mask = cv2.findFundamentalMat(pts_a, pts_b, cv2.FM_RANSAC, 
                                      config["ransac_thresh"])

    if mask is None:
        return matches

    inliers = [m for m, flag in zip(matches, mask.ravel()) if flag]
    return inliers


# ─── Main Stage ───────────────────────────────────────────────────────────────

@log_stage("feature_detection")
def detect_and_match(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Detect features in all frames and match across neighboring frames.
    
    Matching strategy: each frame is matched with up to `match_neighbors`
    frames ahead (not just adjacent) to create a robust match graph that
    survives motion blur and exposure changes.
    
    Match pairs: (i, i+1), (i, i+2), ..., (i, i+match_neighbors)
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log = get_logger("feature_detection", ctx.output_dir)

    n_frames = len(ctx.frame_paths)
    if n_frames < 2:
        raise RuntimeError("Need at least 2 frames for feature matching")

    log.info(f"Detecting {cfg['detector'].upper()} features in {n_frames} frames...")

    detector = create_detector(cfg)
    matcher = create_matcher(cfg)

    # ── Detect features in all frames ──
    all_keypoints = []
    all_descriptors = []

    for i, frame_path in enumerate(ctx.frame_paths):
        kps, descs, _ = detect_features(frame_path, detector, cfg["resize_for_features"])
        all_keypoints.append(kps)
        all_descriptors.append(descs)

        if (i + 1) % 20 == 0:
            avg_kps = np.mean([len(k) for k in all_keypoints])
            log.info(f"Detected features: {i + 1}/{n_frames} frames (avg {avg_kps:.0f} kps/frame)")

    avg_kps = np.mean([len(k) for k in all_keypoints])
    log.info(f"Feature detection complete: avg {avg_kps:.0f} keypoints/frame")

    # ── Match across neighbor frames ──
    log.info(f"Matching features (neighbor window = {cfg['match_neighbors']})...")
    all_matches = {}
    total_good = 0
    total_pairs = 0

    for i in range(n_frames):
        for offset in range(1, cfg["match_neighbors"] + 1):
            j = i + offset
            if j >= n_frames:
                break

            raw_matches = match_pair(
                all_descriptors[i], all_descriptors[j], matcher, cfg
            )

            if len(raw_matches) < cfg["min_matches"]:
                continue

            # Geometric verification
            verified = geometric_verification(
                all_keypoints[i], all_keypoints[j], raw_matches, cfg
            )

            if len(verified) >= cfg["min_matches"]:
                all_matches[(i, j)] = verified
                total_good += len(verified)
                total_pairs += 1

    log.info(f"Matching complete: {total_pairs} valid pairs, "
             f"{total_good} total matches (avg {total_good / max(total_pairs, 1):.0f}/pair)")

    # Store in context
    ctx.keypoints = all_keypoints
    ctx.descriptors = all_descriptors
    ctx.matches = all_matches

    # Save match summary
    match_summary = {
        "total_frames": n_frames,
        "avg_keypoints_per_frame": float(avg_kps),
        "total_pairs": total_pairs,
        "total_matches": total_good,
        "detector": cfg["detector"],
    }

    import json
    summary_path = ctx.output_dir / "match_summary.json"
    with open(summary_path, "w") as f:
        json.dump(match_summary, f, indent=2)

    return ctx
