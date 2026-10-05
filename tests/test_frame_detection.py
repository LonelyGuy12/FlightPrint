"""Tests for Stage 9 frame detection (Oct 7, M2). No weights or network needed.

Run:
    python -m pytest tests/test_frame_detection.py -v
"""

import json
import logging as _logging
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import stage9_ai_agent as s9  # noqa: E402
from pipeline import stage9_detection as det  # noqa: E402
from pipeline.utils.io import PipelineContext  # noqa: E402

W, H = 640, 480
K = np.array([[500.0, 0, W / 2], [0, 500.0, H / 2], [0, 0, 1]])
N_CLASSES = len(det.COCO_LABELS)
CAR = det.COCO_LABELS.index("car")


def _close_stage_handlers():
    lg = _logging.getLogger("flightprint.ai_agent")
    for h in list(lg.handlers):
        if isinstance(h, _logging.FileHandler):
            h.close()
            lg.removeHandler(h)


# ---------------------------------------------------------------- output parsing

def _v5_row(cx, cy, w, h, obj, cls_id, cls_conf, n=N_CLASSES):
    r = np.zeros(5 + n, dtype=np.float32)
    r[0], r[1], r[2], r[3], r[4] = cx, cy, w, h, obj
    r[5 + cls_id] = cls_conf
    return r


def test_parse_yolov5_layout():
    out = np.array([[
        _v5_row(320, 240, 128, 96, 0.9, CAR, 0.8),   # conf 0.72, kept
        _v5_row(330, 245, 128, 96, 0.8, CAR, 0.7),   # overlaps, weaker -> NMS'd
        _v5_row(100, 100, 40, 40, 0.9, CAR, 0.1),    # conf 0.09 < thr -> dropped
    ]])
    dets = det.parse_detections([out], W, H, 640, 0.4, 0.45)
    assert len(dets) == 1
    d = dets[0]
    assert d["class_name"] == "car"
    assert d["confidence"] == round(0.9 * 0.8, 3)
    # Plain resize 640x480 -> 640x640: x maps 1:1, y maps by 0.75.
    assert d["bbox"] == [256.0, 144.0, 128.0, 72.0]


def test_parse_yolov8_transposed_layout():
    # (1, 84, N): [cx, cy, w, h, cls...], no objectness.
    cols = []
    for cx, cy, w, h, cls_id, cls_conf in [
        (320, 320, 100, 100, CAR, 0.85),
        (50, 50, 20, 20, 0, 0.1),   # person, below threshold
    ]:
        c = np.zeros(4 + N_CLASSES, dtype=np.float32)
        c[0], c[1], c[2], c[3] = cx, cy, w, h
        c[4 + cls_id] = cls_conf
        cols.append(c)
    out = np.stack(cols, axis=1)[None, :, :]
    assert out.shape == (1, 4 + N_CLASSES, 2)
    dets = det.parse_detections([out], W, H, 640, 0.4, 0.45)
    assert len(dets) == 1 and dets[0]["class_name"] == "car"
    assert dets[0]["confidence"] == round(0.85, 3)


def test_parse_malformed_output_returns_empty():
    assert det.parse_detections([np.zeros((7, 7))], W, H, 640, 0.4, 0.45) == []
    assert det.parse_detections([], W, H, 640, 0.4, 0.45) == []


def test_point_in_bbox():
    assert det.point_in_bbox([386.7, 240.0], [300, 150, 200, 200])
    assert not det.point_in_bbox([10.0, 10.0], [300, 150, 200, 200])


# ---------------------------------------------------------------- fusion

def _anomaly(pixel, confidence=0.6):
    return {
        "id": "anom_000",
        "confidence": confidence,
        "confidence_factors": {"signal": 0.5, "views": 0.5,
                               "diversity": 0.5, "points": 0.5},
        "supporting_frames": [{"frame_index": 0, "pixel": pixel}],
    }


def test_fuse_boosts_confidence_on_overlap():
    a = _anomaly([386.7, 240.0])
    n = det.fuse_detections(
        [a], {0: [{"bbox": [300, 150, 200, 200], "class_id": CAR,
                   "class_name": "car", "confidence": 0.8}]}, weight=0.15)
    assert n == 1
    assert len(a["overlapping_detections"]) == 1
    assert a["confidence_factors"]["detections"] == 0.8
    assert a["confidence"] == round(0.85 * 0.6 + 0.15 * 0.8, 3) > 0.6


def test_fuse_leaves_confidence_without_overlap():
    a = _anomaly([10.0, 10.0])
    n = det.fuse_detections(
        [a], {0: [{"bbox": [300, 150, 200, 200], "class_id": CAR,
                   "class_name": "car", "confidence": 0.8}]})
    assert n == 0
    assert a["overlapping_detections"] == []
    assert a["confidence"] == 0.6  # untouched: absence is not evidence


def test_fuse_ignores_irrelevant_classes_for_boost_but_records_them():
    a = _anomaly([386.7, 240.0])
    n = det.fuse_detections(
        [a], {0: [{"bbox": [300, 150, 200, 200], "class_id": 47,
                   "class_name": "apple", "confidence": 0.9}]})
    assert n == 0 and len(a["overlapping_detections"]) == 1
    assert a["confidence"] == 0.6


# ---------------------------------------------------------------- stage 9 integration

def nadir_pose(cx, cy, alt):
    R = np.array([[1.0, 0, 0], [0, -1.0, 0], [0, 0, -1.0]])
    pose = np.eye(4)
    pose[:3, :3] = R
    pose[:3, 3] = -R @ np.array([cx, cy, alt])
    return pose


class StubDetector:
    """Pretends every frame contains one car at a fixed box."""

    def __init__(self, dets):
        self.dets = dets
        self.calls = []

    def detect_frame(self, frame_path, conf_thr, nms_thr):
        self.calls.append(str(frame_path))
        return [dict(d) for d in self.dets]


def _ctx(tmp: Path) -> PipelineContext:
    import cv2
    frames = []
    for i in range(10):
        p = tmp / "frames" / f"frame_{i:04d}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(p), np.full((H, W, 3), 90 + i, np.uint8))
        frames.append(p)
    rng = np.random.default_rng(0)
    xy = rng.uniform([-5, -8], [45, 8], size=(4000, 2))
    z = rng.normal(0, 0.05, size=4000)
    bump = (np.abs(xy[:, 0] - 20) < 1.5) & (np.abs(xy[:, 1]) < 1.5)
    z[bump] += 5.0
    ctx = PipelineContext(video_path=tmp / "v.mp4", metadata_path=None,
                          output_dir=tmp)
    ctx.frame_paths, ctx.frame_timestamps = frames, [i * 0.5 for i in range(10)]
    ctx.camera_matrix = K
    ctx.poses = [nadir_pose(i * 4.0, 0.0, 30.0) for i in range(10)]
    ctx.sparse_cloud = np.column_stack([xy, z])
    ctx.scale_status = "metric_approximate"
    return ctx


CAR_BOX = [{"bbox": [300, 150, 200, 200], "class_id": CAR,
            "class_name": "car", "confidence": 0.8}]


def test_detection_off_by_default_schema_unchanged():
    with tempfile.TemporaryDirectory() as d:
        try:
            ctx = s9.analyze_scene(_ctx(Path(d)), {})
            report = json.loads((Path(d) / "anomaly_report.json").read_text())
            assert report["schema_version"] == 2
            assert "frame_detection" not in report
            assert all("overlapping_detections" not in a for a in ctx.anomalies)
        finally:
            _close_stage_handlers()


def test_analyze_scene_with_injected_detector_fuses_and_keeps_schema():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        try:
            stub = StubDetector(CAR_BOX)
            ctx = s9.analyze_scene(
                _ctx(tmp),
                {"use_frame_detection": True, "_detector": stub,
                 "yolo_frame_stride": 1},
            )
            report = json.loads((tmp / "anomaly_report.json").read_text())
            assert report["schema_version"] == 2
            # All v1/v2 anomaly fields still present (Hamza's panel contract).
            for a in ctx.anomalies:
                for field in ("id", "signal_strength", "supporting_frames",
                              "view_angle_spread_deg", "confidence",
                              "confidence_factors", "evidence_level"):
                    assert field in a, field
            high = next(a for a in ctx.anomalies if a["type"] == "elevation_high")
            assert len(high["overlapping_detections"]) >= 1
            assert high["confidence_factors"]["detections"] == 0.8
            assert "_detector" not in report["analysis_config"]
            fd = report["frame_detection"]
            assert fd["frames_checked"] == 10 and fd["total_detections"] == 10
            assert fd["anomalies_with_overlaps"] >= 1
            assert stub.calls  # detector actually ran on frames
        finally:
            _close_stage_handlers()


def test_detection_failure_does_not_fail_stage():
    class Broken:
        def detect_frame(self, *a):
            raise RuntimeError("no model")

    with tempfile.TemporaryDirectory() as d:
        try:
            ctx = s9.analyze_scene(
                _ctx(Path(d)),
                {"use_frame_detection": True, "_detector": Broken()})
            assert ctx.anomalies  # geometric result kept
        finally:
            _close_stage_handlers()


def test_run_frame_detection_sampling_caps():
    stub = StubDetector(CAR_BOX)
    paths = [f"f{i}.jpg" for i in range(10)]
    out = det.run_frame_detection(paths, {"yolo_frame_stride": 3,
                                           "yolo_max_frames": 2},
                                  detector=stub)
    assert sorted(out) == [0, 3]  # stride 3, capped at 2 frames


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
