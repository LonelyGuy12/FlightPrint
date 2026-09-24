"""Stage 7: Georeferencing.

Transforms the reconstructed coordinate frame into WGS84/UTM so
outputs have real-world coordinates. Uses the GPS-aligned poses
from Stage 4 and the ENU origin to produce georeferenced outputs.
"""

import json
import numpy as np
from pathlib import Path

from .utils.logging import get_logger, log_stage
from .utils.io import PipelineContext, save_point_cloud_ply
from .utils.geo import local_enu_to_gps, gps_to_local_enu


DEFAULT_CONFIG = {
    "output_crs": "EPSG:4326",   # WGS84
    "generate_dsm": True,         # Digital Surface Model
    "dsm_resolution": 0.5,        # meters per pixel
}


def generate_dsm(points: np.ndarray, resolution: float, output_path: Path) -> dict:
    """Generate a Digital Surface Model (DSM) from the point cloud.
    
    A DSM is a 2D grid where each cell contains the highest Z (elevation)
    value of points falling in that cell.
    
    Returns metadata about the DSM.
    """
    if len(points) < 10:
        return {}

    x, y, z = points[:, 0], points[:, 1], points[:, 2]

    x_min, x_max = x.min(), x.max()
    y_min, y_max = y.min(), y.max()

    cols = max(1, int((x_max - x_min) / resolution) + 1)
    rows = max(1, int((y_max - y_min) / resolution) + 1)

    # Cap size for memory
    if rows * cols > 4_000_000:
        scale = np.sqrt(4_000_000 / (rows * cols))
        resolution = resolution / scale
        cols = max(1, int((x_max - x_min) / resolution) + 1)
        rows = max(1, int((y_max - y_min) / resolution) + 1)

    dsm = np.full((rows, cols), np.nan)

    # Bin points into grid
    col_idx = np.clip(((x - x_min) / resolution).astype(int), 0, cols - 1)
    row_idx = np.clip(((y_max - y) / resolution).astype(int), 0, rows - 1)

    for r, c, height in zip(row_idx, col_idx, z):
        if np.isnan(dsm[r, c]) or height > dsm[r, c]:
            dsm[r, c] = height

    # Save as raw binary + metadata (for simplicity — could use GeoTIFF with rasterio)
    np.save(str(output_path.with_suffix('.npy')), dsm)

    # Also save as a JSON-compatible format for the web viewer
    dsm_clean = np.nan_to_num(dsm, nan=-9999)
    meta = {
        "rows": rows,
        "cols": cols,
        "resolution": resolution,
        "origin_x": float(x_min),
        "origin_y": float(y_max),
        "min_elevation": float(np.nanmin(dsm)) if not np.all(np.isnan(dsm)) else 0,
        "max_elevation": float(np.nanmax(dsm)) if not np.all(np.isnan(dsm)) else 0,
        "nodata": -9999,
    }

    with open(output_path.with_suffix('.json'), "w") as f:
        json.dump(meta, f, indent=2)

    return meta


@log_stage("georeferencing")
def georeference(ctx: PipelineContext, config: dict | None = None) -> PipelineContext:
    """Transform reconstructed outputs into real-world coordinates.

    Behaviour depends on ``ctx.reconstruction_mode``:

    * **full** / **scale_assisted with GPS** — convert ENU cloud to WGS84,
      generate georeferenced DSM, write GeoJSON.
    * **scale_assisted (altitude only)** — no WGS84 (no GPS origin), but
      generate a local-coordinate DSM labelled "approximate".
    * **vision_only** — skip georeferencing entirely; output stays in
      arbitrary local frame.  Log why and return immediately.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    log = get_logger("georeferencing", ctx.output_dir)

    cloud = ctx.dense_cloud if ctx.dense_cloud is not None else ctx.sparse_cloud
    colors = ctx.dense_colors if ctx.dense_colors is not None else ctx.sparse_colors

    if cloud is None or len(cloud) == 0:
        log.warning("No point cloud to georeference")
        return ctx

    # ── Vision-only: nothing to do ──
    if ctx.scale_status == "relative_unscaled":
        log.info("Vision-only mode — skipping georeferencing (output is relative/unscaled)")
        return ctx

    origin = ctx.geo_origin

    # ── No geo origin → local DSM only ──
    if not origin:
        log.info("No geo origin available — outputs remain in local coordinates")
        if cfg["generate_dsm"] and len(cloud) > 10:
            dsm_path = ctx.output_dir / "dsm"
            dsm_meta = generate_dsm(cloud, cfg["dsm_resolution"], dsm_path)
            if dsm_meta:
                dsm_meta["scale_note"] = "approximate metric scale, not georeferenced"
                log.info(f"Generated local DSM: {dsm_meta.get('rows')}x{dsm_meta.get('cols')}")
        return ctx

    log.info(f"Georeferencing {len(cloud)} points (origin: {origin['lat']:.6f}, {origin['lon']:.6f})")

    # Convert point cloud from ENU to WGS84
    gps_points = local_enu_to_gps(cloud, origin)

    # Save georeferenced point cloud as GeoJSON-like format
    geo_cloud = {
        "type": "FeatureCollection",
        "crs": cfg["output_crs"],
        "origin": origin,
        "features": [],
    }

    # Sample for the GeoJSON (full cloud would be too large)
    sample_step = max(1, len(gps_points) // 10000)
    for i in range(0, len(gps_points), sample_step):
        pt = gps_points[i]
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [pt["lon"], pt["lat"], pt.get("alt", 0)],
            },
            "properties": {
                "index": i,
            },
        }
        if colors is not None and i < len(colors):
            feature["properties"]["color"] = colors[i].tolist()
        geo_cloud["features"].append(feature)

    geojson_path = ctx.output_dir / "georef_cloud.geojson"
    with open(geojson_path, "w") as f:
        json.dump(geo_cloud, f)
    log.info(f"Saved georeferenced cloud ({len(geo_cloud['features'])} sampled points)")

    # Generate DSM in ENU coordinates
    if cfg["generate_dsm"] and len(cloud) > 10:
        dsm_path = ctx.output_dir / "dsm"
        dsm_meta = generate_dsm(cloud, cfg["dsm_resolution"], dsm_path)
        dsm_meta["geo_origin"] = origin
        if dsm_meta:
            log.info(f"Generated DSM: {dsm_meta.get('rows')}x{dsm_meta.get('cols')} @ {cfg['dsm_resolution']}m/px")

    # Save georeferencing report
    report = {
        "origin": origin,
        "crs": cfg["output_crs"],
        "num_points": len(cloud),
        "bounds_enu": {
            "min": cloud.min(axis=0).tolist(),
            "max": cloud.max(axis=0).tolist(),
        },
        "bounds_wgs84": {
            "min_lat": min(p["lat"] for p in gps_points),
            "max_lat": max(p["lat"] for p in gps_points),
            "min_lon": min(p["lon"] for p in gps_points),
            "max_lon": max(p["lon"] for p in gps_points),
        },
    }
    with open(ctx.output_dir / "georef_report.json", "w") as f:
        json.dump(report, f, indent=2)

    return ctx
