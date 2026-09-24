"""Stage 1: Adaptive Frame Extraction from Drone Video.

Extracts frames at an adaptive rate — denser where the drone moves slowly
(hovering, turning) and sparser during fast straight-line flight. Deduplicates
near-identical frames using histogram difference and optional optical flow.
Includes basic quality filtering to reject motion-blurred frames.
"""

import cv2
import numpy as np
from pathlib import Path

from .utils.logging import get_logger, log_stage
from .utils.io import PipelineContext


# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "min_frame_interval_s": 0.1,    # Never extract faster than 10 fps
    "max_frame_interval_s": 2.0,    # Never go slower than 0.5 fps
    "target_fps": 2.0,              # Base extraction rate
    "histogram_diff_thresh": 0.15,  # Below this = duplicate (0-1, lower=stricter)
    "blur_thresh": 50.0,            # Laplacian variance below this = blurry
    "optical_flow_thresh": 2.0,     # Mean flow magnitude for adaptive rate
    "max_frames": 500,              # Hard cap for demo/memory
    "resize_for_analysis": 640,     # Resize width for flow/blur analysis (speed)
}


# ─── Frame Quality ────────────────────────────────────────────────────────────

def compute_blur_score(frame: np.ndarray) -> float:
    """Laplacian variance — higher = sharper."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def compute_histogram_diff(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    """Normalized histogram difference between two frames (0 = identical, 1 = max diff)."""
    hist_a = cv2.calcHist([frame_a], [0, 1, 2], None, [8, 8, 8], [0, 256] * 3)
    hist_b = cv2.calcHist([frame_b], [0, 1, 2], None, [8, 8, 8], [0, 256] * 3)
    cv2.normalize(hist_a, hist_a)
    cv2.normalize(hist_b, hist_b)
    # Correlation: 1 = identical, -1 = inverse
    corr = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)
    return 1.0 - max(0.0, corr)


def compute_optical_flow_magnitude(prev_gray: np.ndarray, curr_gray: np.ndarray) -> float:
    """Mean optical flow magnitude between two grayscale frames."""
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, curr_gray,
        None,
        pyr_scale=0.5, levels=3, winsize=15,
        iterations=3, poly_n=5, poly_sigma=1.2,
        flags=0,
    )
    mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    return float(np.mean(mag))


# ─── Main Extraction ──────────────────────────────────────────────────────────

@log_stage("frame_extraction")
def extract_frames(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Extract frames from the video with adaptive sampling and quality filtering.
    
    Strategy:
    1. Read frames at the base target_fps
    2. Compute optical flow to adjust sampling rate (more flow = keep frame, less = skip)
    3. Reject blurry frames (low Laplacian variance)
    4. Reject near-duplicate frames (high histogram correlation with previous kept frame)
    
    Writes extracted frames to ctx.output_dir / "frames" as JPEG files.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log = get_logger("frame_extraction", ctx.output_dir)

    video = cv2.VideoCapture(str(ctx.video_path))
    if not video.isOpened():
        raise RuntimeError(f"Cannot open video: {ctx.video_path}")

    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = video.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps if fps > 0 else 0

    log.info(f"Video: {total_frames} frames, {fps:.1f} fps, {duration:.1f}s")

    frames_dir = ctx.output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    ctx.frames_dir = frames_dir

    # Calculate base frame interval
    base_interval = 1.0 / cfg["target_fps"]
    min_interval = cfg["min_frame_interval_s"]
    max_interval = cfg["max_frame_interval_s"]

    extracted_frames = []
    frame_timestamps = []
    prev_kept_frame = None
    prev_gray_small = None
    frame_idx = 0
    next_extract_time = 0.0

    while True:
        ret, frame = video.read()
        if not ret:
            break

        timestamp = frame_idx / fps if fps > 0 else 0.0
        frame_idx += 1

        # Skip if before next extraction time
        if timestamp < next_extract_time:
            continue

        # Resize for analysis (speed)
        h, w = frame.shape[:2]
        analysis_w = cfg["resize_for_analysis"]
        scale = analysis_w / w if w > analysis_w else 1.0
        if scale < 1.0:
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        else:
            small = frame

        gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        # ── Quality check: blur ──
        blur_score = compute_blur_score(gray_small)
        if blur_score < cfg["blur_thresh"]:
            log.debug(f"Frame {frame_idx}: rejected (blur={blur_score:.1f} < {cfg['blur_thresh']})")
            continue

        # ── Deduplication: histogram diff ──
        if prev_kept_frame is not None:
            hist_diff = compute_histogram_diff(small, prev_kept_frame)
            if hist_diff < cfg["histogram_diff_thresh"]:
                log.debug(f"Frame {frame_idx}: rejected (duplicate, hist_diff={hist_diff:.3f})")
                continue

        # ── Adaptive rate: optical flow ──
        current_interval = base_interval
        if prev_gray_small is not None:
            flow_mag = compute_optical_flow_magnitude(prev_gray_small, gray_small)
            # High motion → shorter interval (more frames), low motion → longer
            if flow_mag > cfg["optical_flow_thresh"] * 2:
                current_interval = min_interval
            elif flow_mag < cfg["optical_flow_thresh"] * 0.5:
                current_interval = max_interval
            else:
                # Linear interpolation
                ratio = (flow_mag - cfg["optical_flow_thresh"] * 0.5) / (cfg["optical_flow_thresh"] * 1.5)
                current_interval = max_interval - ratio * (max_interval - min_interval)

        # ── Save frame ──
        frame_name = f"frame_{len(extracted_frames):05d}.jpg"
        frame_path = frames_dir / frame_name
        cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

        extracted_frames.append(frame_path)
        frame_timestamps.append(timestamp)

        prev_kept_frame = small.copy()
        prev_gray_small = gray_small.copy()
        next_extract_time = timestamp + current_interval

        if len(extracted_frames) % 20 == 0:
            log.info(f"Extracted {len(extracted_frames)} frames (at {timestamp:.1f}s / {duration:.1f}s)")

        if len(extracted_frames) >= cfg["max_frames"]:
            log.warning(f"Hit max frame cap ({cfg['max_frames']}), stopping extraction")
            break

    video.release()

    ctx.frame_paths = extracted_frames
    ctx.frame_timestamps = frame_timestamps

    log.info(f"Extracted {len(extracted_frames)} frames from {frame_idx} total "
             f"({100 * len(extracted_frames) / max(frame_idx, 1):.1f}% kept)")

    return ctx
