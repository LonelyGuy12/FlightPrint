"""Stage 2: Camera Calibration.

Determines camera intrinsic parameters (focal length, principal point,
distortion coefficients). Uses provided intrinsics from metadata if available;
otherwise estimates from EXIF data or falls back to reasonable defaults
for common drone cameras.
"""

import cv2
import numpy as np
from pathlib import Path

from .utils.logging import get_logger, log_stage
from .utils.io import PipelineContext


# Common drone camera presets (focal_length_mm, sensor_width_mm)
DRONE_CAMERA_PRESETS = {
    "dji_mavic3":     {"focal_mm": 24.0, "sensor_w_mm": 17.3},
    "dji_mini3_pro":  {"focal_mm": 24.0, "sensor_w_mm": 9.7},
    "dji_air2s":      {"focal_mm": 22.0, "sensor_w_mm": 13.2},
    "dji_phantom4":   {"focal_mm": 24.0, "sensor_w_mm": 13.2},
    "dji_mavic2_pro": {"focal_mm": 28.0, "sensor_w_mm": 13.2},
    "generic_drone":  {"focal_mm": 24.0, "sensor_w_mm": 13.2},
}


def estimate_intrinsics_from_metadata(metadata: dict, image_w: int, image_h: int) -> tuple[np.ndarray, np.ndarray]:
    """Compute camera matrix from metadata (focal length + sensor size).
    
    Returns:
        (camera_matrix, dist_coeffs) where camera_matrix is 3x3 and dist_coeffs is 1x5.
    """
    cam = metadata.get("camera", {})

    focal_mm = cam.get("focal_length_mm")
    sensor_w_mm = cam.get("sensor_width_mm")

    if focal_mm is not None and sensor_w_mm is not None:
        # Convert focal length from mm to pixels
        fx = (focal_mm / sensor_w_mm) * image_w
        fy = fx  # Assume square pixels
    elif "focal_length_px" in cam:
        fx = fy = cam["focal_length_px"]
    else:
        # Fall back to generic drone preset
        preset = DRONE_CAMERA_PRESETS["generic_drone"]
        fx = (preset["focal_mm"] / preset["sensor_w_mm"]) * image_w
        fy = fx

    # Principal point at image center (standard assumption)
    cx = cam.get("cx", image_w / 2.0)
    cy = cam.get("cy", image_h / 2.0)

    camera_matrix = np.array([
        [fx,  0, cx],
        [ 0, fy, cy],
        [ 0,  0,  1],
    ], dtype=np.float64)

    # Distortion coefficients — use provided or assume zero
    dist = cam.get("distortion", [0, 0, 0, 0, 0])
    dist_coeffs = np.array(dist, dtype=np.float64).reshape(-1)

    return camera_matrix, dist_coeffs


def calibrate_from_checkerboard(frame_paths: list[Path], 
                                 board_size: tuple[int, int] = (9, 6),
                                 square_size: float = 0.025) -> tuple[np.ndarray, np.ndarray] | None:
    """Attempt checkerboard calibration from extracted frames.
    
    This is a fallback for when no metadata is provided and frames contain
    a calibration pattern. In practice for drone footage this rarely applies,
    but it's here for completeness.
    """
    objp = np.zeros((board_size[0] * board_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:board_size[0], 0:board_size[1]].T.reshape(-1, 2)
    objp *= square_size

    obj_points = []
    img_points = []
    img_size = None

    for path in frame_paths[:50]:  # Don't check all frames
        img = cv2.imread(str(path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if img_size is None:
            img_size = gray.shape[::-1]

        ret, corners = cv2.findChessboardCorners(gray, board_size, None)
        if ret:
            corners_refined = cv2.cornerSubPix(
                gray, corners, (11, 11), (-1, -1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            )
            obj_points.append(objp)
            img_points.append(corners_refined)

    if len(obj_points) < 3 or img_size is None:
        return None

    ret, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
        obj_points, img_points, img_size, None, None
    )

    if ret:
        return camera_matrix, dist_coeffs
    return None


@log_stage("camera_calibration")
def calibrate_camera(ctx: PipelineContext) -> PipelineContext:
    """Determine camera intrinsic parameters.
    
    Priority:
    1. Use intrinsics from metadata if provided
    2. Attempt checkerboard calibration (unlikely for drone footage)
    3. Fall back to generic drone camera preset
    """
    log = get_logger("camera_calibration", ctx.output_dir)

    if not ctx.frame_paths:
        raise RuntimeError("No frames available — run stage 1 first")

    # Get image dimensions from first frame
    first_frame = cv2.imread(str(ctx.frame_paths[0]))
    if first_frame is None:
        raise RuntimeError(f"Cannot read frame: {ctx.frame_paths[0]}")
    
    image_h, image_w = first_frame.shape[:2]
    log.info(f"Image dimensions: {image_w} x {image_h}")

    metadata = ctx.metadata

    # Priority 1: Metadata intrinsics
    if metadata.get("camera"):
        cam = metadata["camera"]
        if cam.get("focal_length_mm") or cam.get("focal_length_px"):
            camera_matrix, dist_coeffs = estimate_intrinsics_from_metadata(
                metadata, image_w, image_h
            )
            fx = camera_matrix[0, 0]
            log.info(f"Using metadata intrinsics: fx={fx:.1f}px "
                     f"(from {cam.get('focal_length_mm', '?')}mm)")
            ctx.camera_matrix = camera_matrix
            ctx.dist_coeffs = dist_coeffs
            return ctx

    # Priority 2: Checkerboard (unlikely but try a few frames)
    log.info("No metadata intrinsics — trying checkerboard calibration...")
    result = calibrate_from_checkerboard(ctx.frame_paths)
    if result is not None:
        camera_matrix, dist_coeffs = result
        log.info(f"Checkerboard calibration succeeded: fx={camera_matrix[0,0]:.1f}px")
        ctx.camera_matrix = camera_matrix
        ctx.dist_coeffs = dist_coeffs
        return ctx

    # Priority 3: Generic drone preset
    log.warning("No calibration source found — using generic drone preset")
    camera_matrix, dist_coeffs = estimate_intrinsics_from_metadata(
        {"camera": {}}, image_w, image_h
    )
    log.info(f"Generic preset: fx={camera_matrix[0, 0]:.1f}px "
             f"(assuming 24mm on 13.2mm sensor)")

    ctx.camera_matrix = camera_matrix
    ctx.dist_coeffs = dist_coeffs
    return ctx
