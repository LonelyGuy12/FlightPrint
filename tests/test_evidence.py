"""Tests for evidence linking, confidence scoring and Stage 9 (no dataset or AWS needed).

Run:
    python -m pytest tests/test_evidence.py -v
    # or
    python tests/test_evidence.py
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.evidence import (  # noqa: E402
    attach_evidence, find_supporting_frames, project_point, score_confidence,
    viewing_angle_spread,
)
from pipeline import stage9_ai_agent as s9  # noqa: E402
from pipeline.utils.io import PipelineContext  # noqa: E402

W, H = 640, 480
K = np.array([[500.0, 0, W / 2], [0, 500.0, H / 2], [0, 0, 1]])


def nadir_pose(cx: float, cy: float, alt: float) -> np.ndarray:
    """World-to-camera pose for a camera at (cx, cy, alt) looking straight down (ENU world)."""
    R = np.array([[1.0, 0, 0], [0, -1.0, 0], [0, 0, -1.0]])
    C = np.array([cx, cy, alt])
    pose = np.eye(4)
    pose[:3, :3] = R
    pose[:3, 3] = -R @ C
    return pose


def flight(n=10, alt=30.0, step=4.0):
    """A straight pass along x at a fixed altitude."""
    return [nadir_pose(i * step, 0.0, alt) for i in range(n)]


# ---------------------------------------------------------------- projection

def test_point_below_camera_projects_to_centre():
    u, v, d = project_point([8.0, 0.0, 0.0], nadir_pose(8.0, 0.0, 30.0), K)
    assert abs(u - W / 2) < 1e-6 and abs(v - H / 2) < 1e-6 and abs(d - 30.0) < 1e-6


def test_point_behind_camera_is_rejected():
    _, _, d = project_point([0.0, 0.0, 50.0], nadir_pose(0.0, 0.0, 30.0), K)
    assert d < 0


def test_supporting_frames_are_the_cameras_that_see_it():
    poses = flight() + [None]
    frames = find_supporting_frames(np.array([16.0, 0.0, 0.0]), poses, K, (W, H),
                                    frame_timestamps=[i * 0.5 for i in range(11)])
    idx = [f["frame_index"] for f in frames]
    # Footprint half-width at 30 m = 30 * 320 / 500 = 19.2 m (minus 5% margin),
    # so cameras at x = 0..32 see x = 16; the camera right above it ranks first.
    assert idx[0] == 4
    assert set(idx) <= set(range(0, 9)) and 10 not in idx
    assert frames[0]["timestamp"] == 2.0


def test_point_outside_all_frames_has_no_support():
    assert find_supporting_frames(np.array([500.0, 500.0, 0.0]), flight(), K, (W, H)) == []


def test_viewing_angle_spread():
    poses = flight()
    spread = viewing_angle_spread(np.array([16.0, 0.0, 0.0]), poses, [0, 8])
    # Cameras 16 m either side at 30 m altitude: 2 * atan(16/30) = 56.1 degrees
    assert abs(spread - 56.1) < 0.2


# ---------------------------------------------------------------- confidence

def test_confidence_rises_with_evidence():
    weak = score_confidence(0.5, 1, 0.0, 20)
    strong = score_confidence(0.5, 6, 40.0, 200)
    assert strong["confidence"] > weak["confidence"]
    assert strong["evidence_level"] == "strong" and weak["evidence_level"] == "weak"


def test_unverified_is_capped():
    s = score_confidence(1.0, 0, 0.0, 10_000)
    assert s["confidence"] <= 0.30 and s["evidence_level"] == "unverified"


def test_confidence_no_longer_saturates_on_point_count():
    # Old formula gave 0.95 to anything with >= 9 points.
    assert score_confidence(0.4, 1, 0.0, 12)["confidence"] < 0.6


# ---------------------------------------------------------------- stage 9 end to end

def _scene_with_bump():
    rng = np.random.default_rng(0)
    xy = rng.uniform([-5, -8], [45, 8], size=(4000, 2))
    z = rng.normal(0, 0.05, size=4000)
    bump = (np.abs(xy[:, 0] - 20) < 1.5) & (np.abs(xy[:, 1]) < 1.5)
    z[bump] += 5.0
    return np.column_stack([xy, z])


def _ctx(tmp: Path) -> PipelineContext:
    import cv2
    frames = []
    for i in range(10):
        p = tmp / "frames" / f"frame_{i:04d}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(p), np.full((H, W, 3), 90 + i, np.uint8))
        frames.append(p)
    ctx = PipelineContext(video_path=tmp / "v.mp4", metadata_path=None, output_dir=tmp)
    ctx.frame_paths, ctx.frame_timestamps = frames, [i * 0.5 for i in range(10)]
    ctx.camera_matrix, ctx.poses = K, flight()
    ctx.sparse_cloud = _scene_with_bump()
    ctx.scale_status = "metric_approximate"
    return ctx


def test_stage9_links_bump_to_frames_and_writes_report():
    import logging as _logging
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ctx = s9.analyze_scene(_ctx(tmp), {})
        report = json.loads((tmp / "anomaly_report.json").read_text())
        assert report["schema_version"] == 2
        high = next(a for a in ctx.anomalies if a["type"] == "elevation_high")
        assert abs(high["position_enu"][0] - 20) < 1.0
        assert len(high["supporting_frames"]) >= 3
        assert high["evidence_level"] in ("strong", "moderate")
        crops = [f["crop_path"] for f in high["supporting_frames"] if f.get("crop_path")]
        assert crops and all(Path(c).exists() for c in crops)
        assert set(high["confidence_factors"]) == {"signal", "views", "diversity", "points"}
        # On Windows, FileHandlers hold open file locks that prevent TemporaryDirectory
        # cleanup. Close all handlers on the stage logger before exiting the with-block.
        lg = _logging.getLogger("flightprint.ai_agent")
        for h in list(lg.handlers):
            if isinstance(h, _logging.FileHandler):
                h.close()
                lg.removeHandler(h)


class FakeBedrock:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def converse(self, **kw):
        self.calls.append(kw)
        return {"output": {"message": {"content": [{"text": self.reply}]}}}


def test_bedrock_assessment_adjusts_confidence():
    with tempfile.TemporaryDirectory() as d:
        ctx = s9.analyze_scene(_ctx(Path(d)), {})
        a = next(x for x in ctx.anomalies if x["type"] == "elevation_high")
        before = a["confidence"]
        fake = FakeBedrock('Sure: {"label": "damage", "description": "Collapsed wall", "confidence": 0.9}')
        assessment = s9.assess_with_bedrock(a, s9.DEFAULT_CONFIG, client=fake)
        s9.apply_visual_assessment(a, assessment, 0.25)
        sent = fake.calls[0]["messages"][0]["content"]
        assert sum(1 for c in sent if "image" in c) == assessment["crops_checked"] > 0
        assert a["visual_assessment"]["label"] == "damage" and a["severity"] == "high"
        assert a["confidence"] == round(0.75 * before + 0.25 * 0.9, 3)


def test_bedrock_says_nothing_there_lowers_confidence():
    a = {"supporting_frames": [], "confidence": 0.8, "confidence_factors": {}}
    s9.apply_visual_assessment(a, {"label": "none", "confidence": 0.9, "description": "", "model": "m",
                                   "crops_checked": 2}, 0.25)
    assert a["confidence"] < 0.8


# ---------------------------------------------------------------- Bedrock robustness (unit-level, FakeBedrock)

class ExplodingBedrock:
    """Fails the test if Bedrock is ever called (used when no call is expected)."""

    def converse(self, **kw):
        raise AssertionError("Bedrock should not have been called")


def _anomaly_with_real_crop(tmp: Path):
    import cv2
    frame = tmp / "frame.jpg"
    cv2.imwrite(str(frame), np.full((480, 640, 3), 128, np.uint8))
    crop = s9_save_crop(frame)
    return {"description": "test bump", "supporting_frames": [{"crop_path": str(crop)}]}


def s9_save_crop(frame: Path) -> Path:
    from pipeline.evidence import save_evidence_crop
    out = frame.parent / "crop.jpg"
    assert save_evidence_crop(frame, [320.0, 240.0], out) is not None
    return out


def test_bedrock_prose_without_json_returns_none():
    with tempfile.TemporaryDirectory() as d:
        a = _anomaly_with_real_crop(Path(d))
        fake = FakeBedrock("I cannot see anything clearly, try again later.")
        assert s9.assess_with_bedrock(a, s9.DEFAULT_CONFIG, client=fake) is None


def test_bedrock_garbage_json_returns_none():
    with tempfile.TemporaryDirectory() as d:
        a = _anomaly_with_real_crop(Path(d))
        fake = FakeBedrock('{"label": "damage", "confidence": ')  # truncated
        assert s9.assess_with_bedrock(a, s9.DEFAULT_CONFIG, client=fake) is None


def test_bedrock_missing_fields_use_defaults():
    with tempfile.TemporaryDirectory() as d:
        a = _anomaly_with_real_crop(Path(d))
        fake = FakeBedrock('{"label": "obstruction"}')
        out = s9.assess_with_bedrock(a, s9.DEFAULT_CONFIG, client=fake)
        assert out is not None
        assert out["label"] == "obstruction"
        assert out["description"] == "" and out["confidence"] == 0.5
        assert out["model"] == s9.DEFAULT_CONFIG["bedrock_model_id"]
        assert out["crops_checked"] == 1


def test_bedrock_invalid_label_falls_back():
    with tempfile.TemporaryDirectory() as d:
        a = _anomaly_with_real_crop(Path(d))
        fake = FakeBedrock('{"label": "alien", "description": "x", "confidence": 0.7}')
        out = s9.assess_with_bedrock(a, s9.DEFAULT_CONFIG, client=fake)
        assert out is not None and out["label"] == "unusual_object"


def test_bedrock_invalid_confidence_is_sanitised():
    with tempfile.TemporaryDirectory() as d:
        for raw in ('NaN', '"high"', "5.0", "-2"):
            a = _anomaly_with_real_crop(Path(d))
            fake = FakeBedrock(f'{{"label": "damage", "description": "x", "confidence": {raw}}}')
            out = s9.assess_with_bedrock(a, s9.DEFAULT_CONFIG, client=fake)
            assert out is not None
            assert 0.0 <= out["confidence"] <= 1.0, raw


def test_bedrock_missing_crop_files_skips_call():
    a = {"description": "ghost", "supporting_frames": [{"crop_path": "/nonexistent/crop.jpg"}]}
    assert s9.assess_with_bedrock(a, s9.DEFAULT_CONFIG, client=ExplodingBedrock()) is None
    assert s9.assess_with_bedrock({"description": "empty"}, s9.DEFAULT_CONFIG,
                                  client=ExplodingBedrock()) is None


def test_resolve_bedrock_config_env_and_explicit_precedence(monkeypatch):
    cfg = {"use_bedrock": False, "bedrock_model_id": "default-m", "bedrock_region": "default-r"}
    # Env applies when nothing was set explicitly.
    monkeypatch.setenv("BEDROCK_MODEL_ID", "env-model")
    monkeypatch.setenv("AWS_REGION", "env-region")
    monkeypatch.setenv("FLIGHTPRINT_USE_BEDROCK", "1")
    out = s9.resolve_bedrock_config(dict(cfg), {})
    assert out["bedrock_model_id"] == "env-model"
    assert out["bedrock_region"] == "env-region"
    assert out["use_bedrock"] is True
    # Explicit per-run config always wins over env (same merge order as analyze_scene).
    explicit = {"bedrock_model_id": "explicit-m", "use_bedrock": False}
    merged = {**cfg, **explicit}
    out = s9.resolve_bedrock_config(merged, explicit)
    assert out["bedrock_model_id"] == "explicit-m"
    assert out["use_bedrock"] is False


def test_bedrock_stays_off_by_default():
    assert s9.DEFAULT_CONFIG["use_bedrock"] is False


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    passed, skipped = 0, 0
    for t in tests:
        try:
            t()
        except TypeError as e:
            # Fixture-based tests (e.g. monkeypatch) need pytest; skip here.
            print(f"SKIP {t.__name__} ({e})")
            skipped += 1
            continue
        print(f"PASS {t.__name__}")
        passed += 1
    print(f"{passed} tests passed, {skipped} skipped (run under pytest for all)")
