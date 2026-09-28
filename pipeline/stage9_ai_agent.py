"""Stage 9: Evidence-aware scene analysis.

Finds anomalies in the reconstruction and backs each one with evidence:

1. Geometric detection on the point cloud (elevation outliers, coverage gaps),
   each with a signal strength in [0, 1].
2. Evidence linking: every anomaly is projected into the posed video frames;
   the frames that show it are recorded (index, timestamp, pixel) and the best
   are saved as crops (see pipeline/evidence.py).
3. Confidence scoring from the evidence: detector signal, number of supporting
   frames, spread of viewing angles, and 3D point support.
4. Optional visual check with Amazon Bedrock: the model looks at each
   anomaly's evidence crops and says what is there (damage, obstruction,
   unusual object or nothing), which adjusts the confidence.

Output: anomaly_report.json (schema_version 2) plus evidence/ crops.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from .evidence import attach_evidence
from .utils.io import PipelineContext
from .utils.logging import get_logger, log_stage

SCHEMA_VERSION = 2

DEFAULT_CONFIG = {
    "elevation_anomaly_std": 2.5,     # std devs from mean elevation
    "density_anomaly_quantile": 0.05,  # cell density below this share of the mean = gap
    "density_grid_cells": 20,          # grid resolution along the longer side
    "min_anomaly_points": 10,
    "max_supporting_frames": 8,
    "max_crops_per_anomaly": 3,
    # Visual check with Amazon Bedrock (off by default; needs AWS credentials)
    "use_bedrock": False,
    "bedrock_model_id": os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0"),
    "bedrock_region": os.environ.get("AWS_REGION", "us-east-1"),
    "max_bedrock_anomalies": 10,        # cost cap: only the top-N anomalies are checked
    "visual_weight": 0.25,
}

VISUAL_LABELS = ("damage", "obstruction", "unusual_object", "none")


def _is_metric(ctx) -> bool:
    """True when the reconstruction has metric (absolute or approximate) scale."""
    return getattr(ctx, "scale_status", "relative_unscaled") != "relative_unscaled"


# ---------------------------------------------------------------- geometric detectors

def detect_elevation_anomalies(points: np.ndarray, colors: np.ndarray | None,
                               config: dict, metric: bool = True) -> list[dict]:
    """Regions much higher or lower than the scene's mean elevation.

    signal_strength grows with how far past the threshold the region sits:
    0.4 at the threshold, 1.0 at twice the threshold.
    """
    if len(points) < 50:
        return []

    z = points[:, 2]
    z_mean, z_std = float(np.mean(z)), float(np.std(z))
    if z_std < 0.01:
        return []

    k = config["elevation_anomaly_std"]
    threshold = k * z_std
    anomalies = []

    for kind, mask, severity in (
        ("elevation_high", z > z_mean + threshold, "medium"),
        ("elevation_low", z < z_mean - threshold, "high"),
    ):
        n = int(mask.sum())
        if n < config["min_anomaly_points"]:
            continue
        centroid = points[mask].mean(axis=0)
        delta = abs(float(centroid[2]) - z_mean)
        zscore = delta / z_std
        where = "above" if kind == "elevation_high" else "below"
        what = "Elevated structure or object" if kind == "elevation_high" else "Depression or damage"
        desc = (f"{what} ({delta:.1f}m {where} average)" if metric
                else f"{what} (~{zscore:.1f}× std-dev {where} average elevation)")
        anomalies.append({
            "type": kind,
            "description": desc,
            "position_enu": centroid.tolist(),
            "num_points": n,
            "signal_strength": round(float(np.clip(0.4 + 0.6 * (zscore - k) / k, 0.0, 1.0)), 3),
            "severity": severity,
            "source": "geometry",
        })
    return anomalies


def detect_density_anomalies(points: np.ndarray, config: dict) -> list[dict]:
    """Sparse cells surrounded by dense coverage (occlusion, moving object or gap).

    signal_strength = how empty the cell is compared with its neighbours.
    """
    if len(points) < 100:
        return []

    xy = points[:, :2]
    x_min, y_min = xy.min(axis=0)
    x_range, y_range = xy.max(axis=0) - xy.min(axis=0)
    if x_range < 1 or y_range < 1:
        return []

    cell = max(x_range, y_range) / config["density_grid_cells"]
    cols = max(1, int(x_range / cell) + 1)
    rows = max(1, int(y_range / cell) + 1)
    c_idx = np.minimum(((xy[:, 0] - x_min) / cell).astype(int), cols - 1)
    r_idx = np.minimum(((xy[:, 1] - y_min) / cell).astype(int), rows - 1)
    density = np.zeros((rows, cols))
    np.add.at(density, (r_idx, c_idx), 1)

    occupied = density[density > 0]
    if occupied.size == 0:
        return []
    mean_density = float(occupied.mean())
    sparse_thresh = mean_density * config["density_anomaly_quantile"]
    z_mean = float(points[:, 2].mean())

    anomalies = []
    for r in range(1, rows - 1):
        for c in range(1, cols - 1):
            nb = density[r - 1:r + 2, c - 1:c + 2]
            nb_mean = (nb.sum() - density[r, c]) / 8.0
            if density[r, c] < sparse_thresh and nb_mean > mean_density:
                anomalies.append({
                    "type": "density_gap",
                    "description": "Sparse region surrounded by dense coverage: possible occlusion, "
                                   "moving object, or structural gap",
                    "position_enu": [float(x_min + (c + 0.5) * cell), float(y_min + (r + 0.5) * cell), z_mean],
                    "num_points": int(density[r, c]),
                    "signal_strength": round(float(np.clip(1.0 - density[r, c] / nb_mean, 0.0, 1.0)), 3),
                    "severity": "low",
                    "source": "geometry",
                })
    return anomalies


# ---------------------------------------------------------------- Bedrock visual check

VISUAL_PROMPT = (
    "You are checking one finding from a drone-survey 3D reconstruction. "
    "The images are crops from different video frames; the red ring marks the location of the finding. "
    "Geometric detector says: {description}.\n"
    "What is at the ringed location? Answer with JSON only:\n"
    '{{"label": one of "damage", "obstruction", "unusual_object", "none", '
    '"description": one short sentence on what you see, '
    '"confidence": number from 0 to 1}}'
)


def _bedrock_client(region: str):
    import boto3
    return boto3.client("bedrock-runtime", region_name=region)


def assess_with_bedrock(anomaly: dict, config: dict, client=None) -> dict | None:
    """Ask a Bedrock vision model what the evidence crops show. Returns the assessment or None."""
    crops = [f["crop_path"] for f in anomaly.get("supporting_frames", []) if f.get("crop_path")]
    if not crops:
        return None
    client = client or _bedrock_client(config["bedrock_region"])

    content = [{"text": VISUAL_PROMPT.format(description=anomaly.get("description", ""))}]
    for p in crops:
        content.append({"image": {"format": "jpeg", "source": {"bytes": Path(p).read_bytes()}}})

    response = client.converse(
        modelId=config["bedrock_model_id"],
        messages=[{"role": "user", "content": content}],
        inferenceConfig={"maxTokens": 300, "temperature": 0},
    )
    text = "".join(part.get("text", "") for part in response["output"]["message"]["content"])
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    result = json.loads(text[start:end + 1])

    label = result.get("label", "none")
    if label not in VISUAL_LABELS:
        label = "unusual_object"
    return {
        "label": label,
        "description": str(result.get("description", ""))[:300],
        "confidence": float(np.clip(float(result.get("confidence", 0.5)), 0.0, 1.0)),
        "model": config["bedrock_model_id"],
        "crops_checked": len(crops),
    }


def apply_visual_assessment(anomaly: dict, assessment: dict, weight: float) -> dict:
    """Blend the visual check into the confidence (in place).

    A model that sees something supports the finding with its confidence c;
    a model that sees nothing supports it with 1 - c.
    """
    c = assessment["confidence"]
    support = c if assessment["label"] != "none" else 1.0 - c
    anomaly["visual_assessment"] = assessment
    anomaly["confidence_factors"]["visual"] = round(support, 3)
    anomaly["confidence"] = round(float(np.clip((1 - weight) * anomaly["confidence"] + weight * support,
                                                0.01, 0.99)), 3)
    if assessment["label"] in ("damage", "obstruction") and c >= 0.6:
        anomaly["severity"] = "high"
    return anomaly


# ---------------------------------------------------------------- stage entry point

def _image_size(ctx: PipelineContext) -> tuple[int, int] | None:
    if ctx.frame_paths:
        import cv2
        img = cv2.imread(str(ctx.frame_paths[0]))
        if img is not None:
            return img.shape[1], img.shape[0]
    if ctx.camera_matrix is not None:
        return int(round(2 * ctx.camera_matrix[0, 2])), int(round(2 * ctx.camera_matrix[1, 2]))
    return None


@log_stage("ai_agent")
def analyze_scene(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Detect anomalies, link each to its supporting frames, and score confidence."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log = get_logger("ai_agent", ctx.output_dir)

    cloud = ctx.dense_cloud if ctx.dense_cloud is not None else ctx.sparse_cloud
    if cloud is None or len(cloud) == 0:
        log.warning("No point cloud for analysis")
        ctx.anomalies = []
        return ctx

    log.info(f"Analyzing scene ({len(cloud)} points)...")
    metric = _is_metric(ctx)

    # 1. Geometric detection
    anomalies = detect_elevation_anomalies(cloud, ctx.dense_colors, cfg, metric=metric)
    anomalies += detect_density_anomalies(cloud, cfg)
    for i, a in enumerate(anomalies):
        a["id"] = f"anom_{i:03d}"
    log.info(f"Geometric detection: {len(anomalies)} candidate anomalies")

    # 2 + 3. Evidence linking and confidence
    size = _image_size(ctx)
    crops_dir = ctx.output_dir / "evidence"
    for a in anomalies:
        attach_evidence(a, ctx.poses, ctx.camera_matrix, size or (1, 1),
                        ctx.frame_paths, ctx.frame_timestamps,
                        crops_dir=crops_dir if size else None,
                        max_frames=cfg["max_supporting_frames"],
                        max_crops=cfg["max_crops_per_anomaly"])
    verified = sum(1 for a in anomalies if a["supporting_frames"])
    log.info(f"Evidence linking: {verified}/{len(anomalies)} anomalies seen in at least one frame")

    # 4. Optional visual check with Bedrock
    if cfg["use_bedrock"]:
        client = None
        ranked = sorted(anomalies, key=lambda a: a["confidence"], reverse=True)
        for a in ranked[:cfg["max_bedrock_anomalies"]]:
            try:
                client = client or _bedrock_client(cfg["bedrock_region"])
                assessment = assess_with_bedrock(a, cfg, client)
                if assessment:
                    apply_visual_assessment(a, assessment, cfg["visual_weight"])
            except Exception as e:  # keep the geometric result if Bedrock fails
                log.warning(f"Bedrock check failed for {a['id']}: {e}")
                a["visual_assessment_error"] = str(e)[:200]

    anomalies.sort(key=lambda a: a.get("confidence", 0), reverse=True)

    # GPS coordinates when the reconstruction is georeferenced
    if ctx.geo_origin and ctx.scale_status != "relative_unscaled":
        from .utils.geo import local_enu_to_gps
        for a in anomalies:
            if a.get("position_enu"):
                gps = local_enu_to_gps(np.array([a["position_enu"]]), ctx.geo_origin)
                if gps:
                    a["position_gps"] = gps[0]

    ctx.anomalies = anomalies

    report = {
        "schema_version": SCHEMA_VERSION,
        "total_anomalies": len(anomalies),
        "verified_anomalies": verified,
        "reconstruction_mode": ctx.reconstruction_mode,
        "scale_status": ctx.scale_status,
        "anomalies": anomalies,
        "analysis_config": {k: v for k, v in cfg.items() if k != "bedrock_region"},
    }
    report_path = ctx.output_dir / "anomaly_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    log.info(f"Scene analysis complete: {len(anomalies)} anomalies ({verified} with frame evidence)")
    return ctx
