"""Test suite for the three reconstruction modes.

Exercises detect_mode() and the scale_and_georef module directly,
then runs a lightweight simulation for each mode to verify outputs
carry the correct reconstruction_mode / scale_status tags.

Run:
    python -m pytest tests/test_modes.py -v
    # or simply
    python tests/test_modes.py
"""

import json
import sys
import tempfile
from pathlib import Path

# Ensure the repo root is on the path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.scale_and_georef import (
    detect_mode,
    ReconstructionMode,
    ScaleStatus,
    ModeDecision,
    save_mode_report,
)
from pipeline.utils.io import load_metadata


# ── Sample metadata fixtures ────────────────────────────────────────────────

FULL_METADATA = {
    "gps_track": [
        {"timestamp": 0.0, "lat": 37.7749, "lon": -122.4194, "alt": 100.0},
        {"timestamp": 1.0, "lat": 37.7750, "lon": -122.4193, "alt": 100.5},
        {"timestamp": 2.0, "lat": 37.7751, "lon": -122.4192, "alt": 101.0},
    ],
    "camera": {
        "focal_length_mm": 24.0,
        "sensor_width_mm": 13.2,
        "image_width": 1920,
        "image_height": 1080,
    },
    "imu": [
        {"timestamp": 0.0, "roll": 0.1, "pitch": -0.2, "yaw": 45.0},
        {"timestamp": 1.0, "roll": 0.3, "pitch": -0.1, "yaw": 45.2},
        {"timestamp": 2.0, "roll": 0.2, "pitch": -0.3, "yaw": 45.5},
    ],
}

GPS_ONLY_METADATA = {
    "gps_track": FULL_METADATA["gps_track"],
    "camera": FULL_METADATA["camera"],
    # No IMU
}

ALTITUDE_ONLY_METADATA = {
    "camera": FULL_METADATA["camera"],
    "flight_altitude_m": 80.0,
    # No GPS, no IMU
}

EMPTY_METADATA: dict = {}


# ── Mode Detection Tests ────────────────────────────────────────────────────

def test_full_mode():
    """GPS + IMU present → FULL mode."""
    decision = detect_mode(FULL_METADATA)
    assert decision.mode == ReconstructionMode.FULL, \
        f"Expected FULL, got {decision.mode}"
    assert decision.scale_status == ScaleStatus.METRIC_GEOREFERENCED
    assert decision.has_gps is True
    assert decision.has_imu is True
    print(f"  ✓ FULL mode: {decision.mode.value}, reasons: {decision.reasons}")


def test_scale_assisted_gps_only():
    """GPS present but no IMU → SCALE_ASSISTED."""
    decision = detect_mode(GPS_ONLY_METADATA)
    assert decision.mode == ReconstructionMode.SCALE_ASSISTED, \
        f"Expected SCALE_ASSISTED, got {decision.mode}"
    assert decision.scale_status == ScaleStatus.METRIC_GEOREFERENCED
    assert decision.has_gps is True
    assert decision.has_imu is False
    print(f"  ✓ SCALE_ASSISTED (GPS only): {decision.mode.value}, reasons: {decision.reasons}")


def test_scale_assisted_altitude_only():
    """No GPS/IMU, but flight_altitude_m present → SCALE_ASSISTED (approximate)."""
    decision = detect_mode(ALTITUDE_ONLY_METADATA)
    assert decision.mode == ReconstructionMode.SCALE_ASSISTED, \
        f"Expected SCALE_ASSISTED, got {decision.mode}"
    assert decision.scale_status == ScaleStatus.METRIC_APPROX
    assert decision.has_gps is False
    assert decision.has_altitude is True
    print(f"  ✓ SCALE_ASSISTED (altitude): {decision.mode.value}, reasons: {decision.reasons}")


def test_scale_assisted_user_altitude():
    """No metadata at all, but user provides altitude via config → SCALE_ASSISTED."""
    decision = detect_mode({}, {"user_altitude_m": 50.0})
    assert decision.mode == ReconstructionMode.SCALE_ASSISTED
    assert decision.scale_status == ScaleStatus.METRIC_APPROX
    print(f"  ✓ SCALE_ASSISTED (user altitude): {decision.mode.value}, reasons: {decision.reasons}")


def test_vision_only_mode():
    """No metadata at all → VISION_ONLY."""
    decision = detect_mode(EMPTY_METADATA)
    assert decision.mode == ReconstructionMode.VISION_ONLY, \
        f"Expected VISION_ONLY, got {decision.mode}"
    assert decision.scale_status == ScaleStatus.RELATIVE_UNSCALED
    assert decision.has_gps is False
    assert decision.has_imu is False
    assert decision.has_altitude is False
    print(f"  ✓ VISION_ONLY: {decision.mode.value}, reasons: {decision.reasons}")


def test_vision_only_none_metadata():
    """load_metadata(None) returns empty dict → VISION_ONLY."""
    meta = load_metadata(None)
    assert meta == {}
    decision = detect_mode(meta)
    assert decision.mode == ReconstructionMode.VISION_ONLY
    print(f"  ✓ VISION_ONLY (None path): {decision.mode.value}")


def test_mode_report_serialization():
    """ModeDecision serializes to JSON and back correctly."""
    decision = detect_mode(FULL_METADATA)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        save_mode_report(out, decision)
        report_path = out / "reconstruction_mode.json"
        assert report_path.exists()
        with open(report_path) as f:
            data = json.load(f)
        assert data["reconstruction_mode"] == "full"
        assert data["scale_status"] == "metric_georeferenced"
        assert "GPS track present" in str(data["reasons"])
    print(f"  ✓ Mode report serialization OK")


def test_partial_gps_no_alt():
    """GPS track without alt fields + no IMU → SCALE_ASSISTED but still georef'd."""
    meta = {
        "gps_track": [
            {"timestamp": 0.0, "lat": 37.77, "lon": -122.42},
            {"timestamp": 1.0, "lat": 37.78, "lon": -122.41},
        ]
    }
    decision = detect_mode(meta)
    assert decision.mode == ReconstructionMode.SCALE_ASSISTED
    assert decision.has_gps is True
    assert decision.has_imu is False
    print(f"  ✓ GPS without alt: {decision.mode.value}, scale={decision.scale_status.value}")


# ── Run all ──────────────────────────────────────────────────────────────────

def run_all():
    tests = [
        test_full_mode,
        test_scale_assisted_gps_only,
        test_scale_assisted_altitude_only,
        test_scale_assisted_user_altitude,
        test_vision_only_mode,
        test_vision_only_none_metadata,
        test_mode_report_serialization,
        test_partial_gps_no_alt,
    ]

    print("=" * 60)
    print("FlightPrint Mode Detection Tests")
    print("=" * 60)

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
