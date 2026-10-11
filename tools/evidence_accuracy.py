#!/usr/bin/env python3
"""Evidence accuracy check (Oct 16 task, M2 AI & Evidence).

Compares a Stage 9 ``anomaly_report.json`` against the Mid-Air adapter's
``groundtruth_poses.json`` (+ ``metadata.json``) and reports honest
geometric-consistency metrics per anomaly:

* ``temporal_coverage`` — share of supporting frames whose timestamps fall
  inside the ground-truth time range.
* ``nearest_pose_distance_m`` — 3D distance from the anomaly to the closest
  ground-truth camera position. Approximate: anomaly ``position_enu`` is
  mapped to NED-ish ``(north=enu_y, east=enu_x, down=-enu_z)``, which is only
  valid for GPS-anchored (FULL / SCALE_ASSISTED) runs. For vision-only
  (relative-scale) runs the spatial metrics are skipped with a warning.
* ``nearest_pose_time_offset_s`` — time gap between the anomaly's median
  supporting-frame timestamp and its nearest ground-truth pose.
* ``inside_trajectory_bbox`` — whether the anomaly sits within the flown
  bounding box plus ``--bbox-margin`` metres.

Usage:
  python tools/evidence_accuracy.py --report output/traj0/anomaly_report.json
      --groundtruth data/midair_traj0/groundtruth_poses.json
      --metadata data/midair_traj0/metadata.json --out output/traj0/evidence_accuracy.json

Exit code 0 always (this is a measurement, not a gate); the JSON report
carries a ``summary`` with means/medians/counts. A real Mid-Air measurement
still requires converted dataset trajectory outputs.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path


def load_json(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"Cannot read {path}: {e}")


def enu_to_ned_approx(position_enu: list[float]) -> tuple[float, float, float]:
    """Map ENU metres to NED-ish metres (valid near the geo origin only)."""
    e, n, u = (float(v) for v in position_enu)
    return (n, e, -u)


def dist3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def evaluate(report: dict, groundtruth: dict, spatial_ok: bool,
             bbox_margin: float) -> dict:
    """Compute per-anomaly metrics + summary. Pure function (unit-tested)."""
    poses = groundtruth.get("poses", []) or []
    pose_times = [float(p["timestamp"]) for p in poses if "timestamp" in p]
    pose_xyz = [
        (float(p["north"]), float(p["east"]), float(p["down"]))
        for p in poses
        if all(k in p for k in ("north", "east", "down"))
    ]
    t_min = min(pose_times) if pose_times else None
    t_max = max(pose_times) if pose_times else None

    if pose_xyz:
        ns = [p[0] for p in pose_xyz]
        es = [p[1] for p in pose_xyz]
        ds = [p[2] for p in pose_xyz]
        bbox = {
            "north": [min(ns) - bbox_margin, max(ns) + bbox_margin],
            "east": [min(es) - bbox_margin, max(es) + bbox_margin],
            "down": [min(ds) - bbox_margin, max(ds) + bbox_margin],
        }
    else:
        bbox = None

    per_anomaly = []
    for a in report.get("anomalies", []) or []:
        frames = a.get("supporting_frames", []) or []
        stamps = [float(f["timestamp"]) for f in frames if f.get("timestamp") is not None]

        if t_min is not None and stamps:
            covered = sum(1 for t in stamps if t_min <= t <= t_max)
            temporal_coverage = round(covered / len(stamps), 3)
        else:
            temporal_coverage = None

        entry: dict = {
            "id": a.get("id"),
            "type": a.get("type"),
            "evidence_level": a.get("evidence_level"),
            "confidence": a.get("confidence"),
            "n_supporting_frames": len(frames),
            "temporal_coverage": temporal_coverage,
            "nearest_pose_distance_m": None,
            "nearest_pose_time_offset_s": None,
            "inside_trajectory_bbox": None,
        }

        pos = a.get("position_enu")
        if spatial_ok and pos is not None and pose_xyz:
            ned = enu_to_ned_approx(pos)
            best = min(
                ((dist3(ned, xyz), abs(median(stamps) - t) if stamps and t is not None else None, t)
                 for xyz, t in zip(pose_xyz, pose_times or [None] * len(pose_xyz))),
                key=lambda r: r[0],
            )
            entry["nearest_pose_distance_m"] = round(best[0], 2)
            entry["nearest_pose_time_offset_s"] = (
                round(best[1], 3) if best[1] is not None else None)
            if bbox is not None:
                entry["inside_trajectory_bbox"] = bool(
                    bbox["north"][0] <= ned[0] <= bbox["north"][1]
                    and bbox["east"][0] <= ned[1] <= bbox["east"][1]
                    and bbox["down"][0] <= ned[2] <= bbox["down"][1])
        per_anomaly.append(entry)

    def col(key):
        return [e[key] for e in per_anomaly if e[key] is not None]

    verified = [e for e in per_anomaly if (e["n_supporting_frames"] or 0) > 0]
    summary = {
        "n_anomalies": len(per_anomaly),
        "n_verified": len(verified),
        "spatial_metrics": bool(spatial_ok and pose_xyz),
        "mean_temporal_coverage": round(float(statistics.mean(col("temporal_coverage"))), 3)
        if col("temporal_coverage") else None,
        "median_nearest_pose_distance_m": round(float(statistics.median(col("nearest_pose_distance_m"))), 2)
        if col("nearest_pose_distance_m") else None,
        "n_outside_trajectory_bbox": sum(
            1 for e in per_anomaly if e["inside_trajectory_bbox"] is False),
        "n_no_temporal_coverage": sum(
            1 for e in per_anomaly if e["temporal_coverage"] == 0.0),
    }
    return {
        "per_anomaly": per_anomaly,
        "summary": summary,
        "warnings": [] if spatial_ok else [
            "position_enu is not metric-anchored (vision-only run?) — "
            "spatial metrics skipped; only temporal coverage reported.",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, type=Path, help="anomaly_report.json from a pipeline run")
    ap.add_argument("--groundtruth", required=True, type=Path, help="groundtruth_poses.json from the Mid-Air adapter")
    ap.add_argument("--metadata", required=False, type=Path, default=None,
                    help="metadata.json (only used to note the geo origin)")
    ap.add_argument("--out", required=False, type=Path, default=None, help="where to write the JSON report")
    ap.add_argument("--bbox-margin", type=float, default=25.0, help="bbox padding in metres")
    ap.add_argument("--no-spatial", action="store_true",
                    help="skip spatial metrics even for anchored runs")
    args = ap.parse_args()

    report = load_json(args.report)
    groundtruth = load_json(args.groundtruth)
    spatial_ok = not args.no_spatial and report.get("scale_status") in (
        "metric_absolute", "metric_approximate")

    result = evaluate(report, groundtruth, spatial_ok, args.bbox_margin)
    result["inputs"] = {
        "report": str(args.report),
        "groundtruth": str(args.groundtruth),
        "n_groundtruth_poses": len(groundtruth.get("poses", []) or []),
    }
    if args.metadata and args.metadata.exists():
        meta = load_json(args.metadata)
        result["inputs"]["geo_origin"] = ((meta.get("source") or {}).get("geo_origin"))

    text = json.dumps(result, indent=1)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"Wrote {args.out}")
    s = result["summary"]
    print(f"anomalies={s['n_anomalies']} verified={s['n_verified']} "
          f"mean_temporal_coverage={s['mean_temporal_coverage']} "
          f"median_pose_distance_m={s['median_nearest_pose_distance_m']} "
          f"outside_bbox={s['n_outside_trajectory_bbox']}")
    for w in result["warnings"]:
        print(f"warning: {w}")


if __name__ == "__main__":
    main()
