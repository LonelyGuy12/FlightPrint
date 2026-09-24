"""Stage 9: AI Scene Understanding Agent.

Analyzes the reconstructed scene to identify anomalies and regions of interest:
- Damaged structures
- Blocked roads
- Unusual objects
- Elevation anomalies

Uses an LLM/vision API for scene description when available, with fallback
to geometric heuristics.
"""

import json
import cv2
import numpy as np
from pathlib import Path

from .utils.logging import get_logger, log_stage
from .utils.io import PipelineContext


DEFAULT_CONFIG = {
    "use_llm": False,                # Set True + provide API key for LLM analysis
    "llm_model": "gpt-4o",
    "max_rendered_views": 6,         # Views to render for LLM analysis
    "elevation_anomaly_std": 2.5,    # Std devs for elevation anomaly
    "density_anomaly_quantile": 0.05, # Low-density regions
    "min_anomaly_points": 10,
}


def _is_metric(ctx) -> bool:
    """True when the reconstruction has metric (absolute or approximate) scale."""
    return getattr(ctx, "scale_status", "relative_unscaled") != "relative_unscaled"


def detect_elevation_anomalies(points: np.ndarray, colors: np.ndarray | None,
                                config: dict,
                                metric: bool = True) -> list[dict]:
    """Find regions with unusual elevation (very high/low compared to surroundings).

    When *metric* is False the descriptions use relative language (ratios)
    instead of absolute metre values.
    """
    if len(points) < 50:
        return []

    z = points[:, 2]
    z_mean = np.mean(z)
    z_std = np.std(z)

    if z_std < 0.01:
        return []

    anomalies = []
    threshold = config["elevation_anomaly_std"] * z_std

    # Find high points
    high_mask = z > z_mean + threshold
    if high_mask.sum() >= config["min_anomaly_points"]:
        high_pts = points[high_mask]
        centroid = high_pts.mean(axis=0)
        delta = centroid[2] - z_mean
        if metric:
            desc = f"Elevated structure or object ({delta:.1f}m above average)"
        else:
            ratio = delta / z_std if z_std > 0 else 0
            desc = f"Elevated structure or object (~{ratio:.1f}× std-dev above average elevation)"
        anomalies.append({
            "type": "elevation_high",
            "description": desc,
            "position_enu": centroid.tolist(),
            "num_points": int(high_mask.sum()),
            "confidence": min(0.95, 0.5 + 0.05 * high_mask.sum()),
            "severity": "medium",
        })

    # Find low points (potential depressions/damage)
    low_mask = z < z_mean - threshold
    if low_mask.sum() >= config["min_anomaly_points"]:
        low_pts = points[low_mask]
        centroid = low_pts.mean(axis=0)
        delta = z_mean - centroid[2]
        if metric:
            desc = f"Depression or damage ({delta:.1f}m below average)"
        else:
            ratio = delta / z_std if z_std > 0 else 0
            desc = f"Depression or damage (~{ratio:.1f}× std-dev below average elevation)"
        anomalies.append({
            "type": "elevation_low",
            "description": desc,
            "position_enu": centroid.tolist(),
            "num_points": int(low_mask.sum()),
            "confidence": min(0.95, 0.5 + 0.05 * low_mask.sum()),
            "severity": "high",
        })

    return anomalies


def detect_density_anomalies(points: np.ndarray, config: dict) -> list[dict]:
    """Find spatial regions with anomalous point density."""
    if len(points) < 100:
        return []

    # Simple grid-based density
    xy = points[:, :2]
    x_range = xy[:, 0].max() - xy[:, 0].min()
    y_range = xy[:, 1].max() - xy[:, 1].min()

    if x_range < 1 or y_range < 1:
        return []

    grid_size = max(x_range, y_range) / 20
    cols = max(1, int(x_range / grid_size) + 1)
    rows = max(1, int(y_range / grid_size) + 1)

    density = np.zeros((rows, cols))
    x_min, y_min = xy[:, 0].min(), xy[:, 1].min()

    for pt in xy:
        c = min(int((pt[0] - x_min) / grid_size), cols - 1)
        r = min(int((pt[1] - y_min) / grid_size), rows - 1)
        density[r, c] += 1

    # Find very sparse regions surrounded by dense regions
    anomalies = []
    mean_density = density[density > 0].mean() if (density > 0).any() else 0

    if mean_density > 0:
        sparse_thresh = mean_density * config["density_anomaly_quantile"]
        for r in range(1, rows - 1):
            for c in range(1, cols - 1):
                neighbors = density[r-1:r+2, c-1:c+2]
                if density[r, c] < sparse_thresh and neighbors.mean() > mean_density:
                    center_x = x_min + (c + 0.5) * grid_size
                    center_y = y_min + (r + 0.5) * grid_size
                    center_z = points[:, 2].mean()

                    anomalies.append({
                        "type": "density_gap",
                        "description": "Sparse region surrounded by dense coverage — possible occlusion, moving object, or structural gap",
                        "position_enu": [float(center_x), float(center_y), float(center_z)],
                        "confidence": 0.6,
                        "severity": "low",
                    })

    return anomalies


def render_views_for_llm(ctx: PipelineContext, n_views: int) -> list[Path]:
    """Render a set of representative views from the reconstruction for LLM analysis."""
    view_paths = []
    views_dir = ctx.output_dir / "llm_views"
    views_dir.mkdir(exist_ok=True)

    n_frames = len(ctx.frame_paths)
    step = max(1, n_frames // n_views)

    for i in range(0, n_frames, step):
        if len(view_paths) >= n_views:
            break
        src = ctx.frame_paths[i]
        # Resize for API efficiency
        img = cv2.imread(str(src))
        if img is None:
            continue
        h, w = img.shape[:2]
        if w > 1280:
            scale = 1280 / w
            img = cv2.resize(img, (1280, int(h * scale)))

        dst = views_dir / f"view_{len(view_paths):02d}.jpg"
        cv2.imwrite(str(dst), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        view_paths.append(dst)

    return view_paths


async def analyze_with_llm(view_paths: list[Path], anomalies: list[dict],
                           config: dict) -> list[dict]:
    """Use GPT-4o or similar to analyze rendered views and enrich anomalies."""
    try:
        import openai
        import base64
    except ImportError:
        return anomalies

    try:
        client = openai.OpenAI()

        # Encode images
        images = []
        for path in view_paths[:4]:  # Limit for API cost
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            images.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })

        messages = [
            {"role": "system", "content": (
                "You are an expert aerial/drone image analyst for FlightPrint. "
                "Analyze these drone reconstruction views and identify:\n"
                "1. Damaged structures or infrastructure\n"
                "2. Blocked roads or paths\n"
                "3. Unusual objects or changes\n"
                "4. Areas of interest for further inspection\n\n"
                "Output a JSON array of findings, each with: type, description, "
                "severity (low/medium/high), confidence (0-1)."
            )},
            {"role": "user", "content": [
                {"type": "text", "text": "Analyze these drone reconstruction views:"},
                *images,
            ]},
        ]

        response = client.chat.completions.create(
            model=config["llm_model"],
            messages=messages,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        llm_anomalies = result.get("findings", result.get("anomalies", []))

        # Merge with geometric anomalies
        for finding in llm_anomalies:
            finding["source"] = "llm"
            anomalies.append(finding)

    except Exception as e:
        pass  # LLM analysis is optional

    return anomalies


@log_stage("ai_agent")
def analyze_scene(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Run AI scene understanding on the reconstructed scene.
    
    Combines geometric heuristics with optional LLM vision analysis.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log = get_logger("ai_agent", ctx.output_dir)

    cloud = ctx.dense_cloud if ctx.dense_cloud is not None else ctx.sparse_cloud

    if cloud is None or len(cloud) == 0:
        log.warning("No point cloud for analysis")
        ctx.anomalies = []
        return ctx

    log.info(f"Analyzing scene ({len(cloud)} points)...")

    metric = _is_metric(ctx)
    if not metric:
        log.info("Scale is relative/unscaled — anomaly descriptions will use relative language")

    anomalies = []

    # ── Geometric analysis ──
    log.info("Running elevation anomaly detection...")
    elev_anomalies = detect_elevation_anomalies(cloud, ctx.dense_colors, cfg, metric=metric)
    anomalies.extend(elev_anomalies)
    log.info(f"Found {len(elev_anomalies)} elevation anomalies")

    log.info("Running density anomaly detection...")
    density_anomalies = detect_density_anomalies(cloud, cfg)
    anomalies.extend(density_anomalies)
    log.info(f"Found {len(density_anomalies)} density anomalies")

    # ── LLM analysis (optional) ──
    if cfg["use_llm"]:
        log.info("Rendering views for LLM analysis...")
        views = render_views_for_llm(ctx, cfg["max_rendered_views"])
        if views:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already in async context
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        anomalies = pool.submit(
                            asyncio.run, analyze_with_llm(views, anomalies, cfg)
                        ).result()
                else:
                    anomalies = asyncio.run(analyze_with_llm(views, anomalies, cfg))
            except Exception as e:
                log.warning(f"LLM analysis failed: {e}")

    # Rank anomalies by confidence
    anomalies.sort(key=lambda a: a.get("confidence", 0), reverse=True)

    # Add GPS coordinates if origin is available and mode supports it
    if ctx.geo_origin and ctx.scale_status != "relative_unscaled":
        from .utils.geo import local_enu_to_gps
        for anomaly in anomalies:
            pos = anomaly.get("position_enu")
            if pos:
                gps = local_enu_to_gps(np.array([pos]), ctx.geo_origin)
                if gps:
                    anomaly["position_gps"] = gps[0]

    ctx.anomalies = anomalies

    # Save anomaly report
    report = {
        "total_anomalies": len(anomalies),
        "reconstruction_mode": ctx.reconstruction_mode,
        "scale_status": ctx.scale_status,
        "anomalies": anomalies,
        "analysis_config": cfg,
    }

    report_path = ctx.output_dir / "anomaly_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    log.info(f"Scene analysis complete: {len(anomalies)} anomalies found")
    log.info(f"Anomaly report saved to {report_path}")

    return ctx
