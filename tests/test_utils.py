"""Unit tests for `utils.py` (importlib load, no HA package)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

_UTILS = Path(__file__).resolve().parents[1] / "custom_components" / "ml_brightness" / "utils.py"
_NAME = "ml_brightness_utils_standalone"
_spec = importlib.util.spec_from_file_location(_NAME, _UTILS)
assert _spec and _spec.loader
_u = importlib.util.module_from_spec(_spec)
sys.modules[_NAME] = _u
_spec.loader.exec_module(_u)


def test_clamp():
    assert _u.clamp(5.0, 0.0, 10.0) == 5.0
    assert _u.clamp(-1.0, 0.0, 10.0) == 0.0
    assert _u.clamp(99.0, 0.0, 10.0) == 10.0


def test_parse_hhmm():
    assert _u.parse_hhmm("23:00") == (23, 0)
    assert _u.parse_hhmm("bad") is None


def test_in_time_window_wrap_midnight():
    now = datetime(2026, 4, 30, 1, 0, tzinfo=timezone.utc)
    assert _u.in_time_window(now, "23:00", "06:00") is True
    now2 = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    assert _u.in_time_window(now2, "23:00", "06:00") is False


def test_knn_predict_median():
    x = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    examples = [{"x": list(x), "y": 40.0, "t": 1}, {"x": list(x), "y": 42.0, "t": 2}]
    pred, conf = _u.knn_predict_median(examples, x)
    assert pred is not None
    assert 40.0 <= pred <= 42.0
    assert conf >= 0.0
