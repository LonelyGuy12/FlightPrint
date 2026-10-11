"""Unit tests for tools/evidence_accuracy.py (no dataset needed)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "evidence_accuracy", Path(__file__).resolve().parents[1] / "tools" / "evidence_accuracy.py")
ea = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ea)


def _gt():
    # Straight 100 m pass at 10 Hz, NED metres, down = -100 (100 m altitude).
    return {"poses": [
        {"timestamp": round(i * 0.1, 2), "north": i * 1.0, "east": 0.0, "down": -100.0}
        for i in range(1000)
    ]}


def _report(**kw):
    base = {"schema_version": 2, "scale_status": "metric_approximate", "anomalies": []}
    base.update(kw)
    return base


def _anom(aid="anom_000", pos=(0.0, 50.0, 100.0), stamps=(4.9, 5.0, 5.1)):
    # ENU (east=0, north=50, up=100) sits right above the trajectory at t=5 s.
    return {"id": aid, "type": "elevation_high", "evidence_level": "strong",
            "confidence": 0.8, "position_enu": list(pos),
            "supporting_frames": [
                {"frame_index": i, "timestamp": t, "pixel": [320.0, 240.0], "depth": 100.0}
                for i, t in enumerate(stamps)]}


def test_nearby_verified_anomaly_scores_well():
    out = ea.evaluate(_report(anomalies=[_anom()]), _gt(), True, 25.0)
    e = out["per_anomaly"][0]
    assert e["temporal_coverage"] == 1.0
    assert e["nearest_pose_distance_m"] == 0.0
    assert e["inside_trajectory_bbox"] is True
    assert out["summary"]["n_verified"] == 1


def test_outside_bbox_and_time_flagged():
    a = _anom(pos=(5000.0, 5000.0, 100.0), stamps=(9999.0,))
    out = ea.evaluate(_report(anomalies=[a]), _gt(), True, 25.0)
    e = out["per_anomaly"][0]
    assert e["temporal_coverage"] == 0.0
    assert e["inside_trajectory_bbox"] is False
    assert e["nearest_pose_distance_m"] > 1000
    assert out["summary"]["n_no_temporal_coverage"] == 1
    assert out["summary"]["n_outside_trajectory_bbox"] == 1


def test_vision_only_skips_spatial_with_warning():
    rep = _report(anomalies=[_anom()])
    rep["scale_status"] = "relative_unscaled"
    out = ea.evaluate(rep, _gt(), False, 25.0)
    e = out["per_anomaly"][0]
    assert e["nearest_pose_distance_m"] is None
    assert e["inside_trajectory_bbox"] is None
    assert e["temporal_coverage"] == 1.0  # temporal metrics still work
    assert out["warnings"] and out["summary"]["spatial_metrics"] is False


def test_unverified_anomaly_without_frames():
    a = _anom(stamps=())
    a["evidence_level"] = "unverified"
    out = ea.evaluate(_report(anomalies=[a]), _gt(), True, 25.0)
    e = out["per_anomaly"][0]
    assert e["n_supporting_frames"] == 0
    assert e["temporal_coverage"] is None
    assert e["nearest_pose_distance_m"] == 0.0  # position still checkable
    assert out["summary"]["n_verified"] == 0


def test_enu_to_ned_mapping():
    assert ea.enu_to_ned_approx([10.0, 20.0, 30.0]) == (20.0, 10.0, -30.0)
