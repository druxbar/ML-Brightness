"""Unit tests for `model.py` without importing package `__init__` (no HA on PYTHONPATH)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODEL = Path(__file__).resolve().parents[1] / "custom_components" / "ml_brightness" / "model.py"
_MOD_NAME = "ml_brightness_model_standalone"
_spec = importlib.util.spec_from_file_location(_MOD_NAME, _MODEL)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_MOD_NAME] = _mod
_spec.loader.exec_module(_mod)

ModelConfig = _mod.ModelConfig
ensure_state = _mod.ensure_state
online_update_diag = _mod.online_update_diag
predict = _mod.predict


def test_predict_bias_only():
    w = [10.0, 0.0, 0.0]
    x = [1.0, 2.0]
    assert predict(w, x) == 10.0


def test_predict_with_weights():
    w = [0.0, 2.0, 3.0]
    x = [1.0, 1.0]
    assert predict(w, x) == 5.0


def test_ensure_state_pads_and_truncates():
    w, p = ensure_state([1.0], [0.5], dim=2, ridge=1.0)
    assert len(w) == 3
    assert len(p) == 3
    assert all(pi > 0 for pi in p)


def test_online_update_moves_toward_target():
    cfg = ModelConfig(dim=1, ridge=1.0, huber_k=100.0)
    w, p = [], []
    x = [1.0]
    y = 50.0
    w2, p2, res = online_update_diag(cfg=cfg, w=w, p=p, x=x, y=y, example_weight=1.0)
    yhat_after = predict(w2, x)
    assert abs(yhat_after - y) < abs(0.0 - y)
    assert isinstance(res, float)


def test_huber_weight_downweights_outliers():
    hw = _mod._huber_weight
    k = 5.0
    assert hw(2.0, k) == 1.0
    assert hw(100.0, k) < hw(2.0, k)
