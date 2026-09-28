"""Unit tests for tools/midair_adapter.py conversion helpers (no dataset needed)."""
import importlib.util
import math
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "midair_adapter", Path(__file__).resolve().parents[1] / "tools" / "midair_adapter.py")
ma = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ma)


def test_ned_origin_maps_to_origin():
    out = ma.ned_to_geodetic(np.zeros((1, 3)), 50.0, 5.0, 100.0)
    assert np.allclose(out[0], [50.0, 5.0, 100.0])


def test_ned_north_east_down():
    out = ma.ned_to_geodetic(np.array([[111.32, 0, 0], [0, 0, -10.0]]), 0.0, 0.0, 100.0)
    assert abs(out[0, 0] - 0.001) < 1e-5      # ~111 m north = 0.001 deg lat at equator
    assert out[1, 2] == 110.0                  # 10 m "up" (negative down) raises altitude


def test_quat_identity_and_yaw():
    half = math.radians(90) / 2
    q = np.array([[1, 0, 0, 0], [math.cos(half), 0, 0, math.sin(half)]], dtype=float)
    e = ma.quat_to_euler_deg(q, "wxyz")
    assert np.allclose(e[0], [0, 0, 0])
    assert np.allclose(e[1], [0, 0, 90], atol=1e-6)


def test_quat_order_detection():
    assert ma.detect_quat_order(np.array([1.0, 0, 0, 0])) == "wxyz"
    assert ma.detect_quat_order(np.array([0, 0, 0, 1.0])) == "xyzw"
