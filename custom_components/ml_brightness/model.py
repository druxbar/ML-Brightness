from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    dim: int
    ridge: float = 1.0
    huber_k: float = 12.0  # pct residual threshold for downweight


def _huber_weight(residual: float, k: float) -> float:
    r = abs(residual)
    if r <= k:
        return 1.0
    return k / r


def predict(w: list[float], x: list[float]) -> float:
    # w[0] bias, x excludes bias
    y = w[0] if w else 0.0
    for i, xi in enumerate(x, start=1):
        if i < len(w):
            y += w[i] * xi
    return y


def ensure_state(w: list[float], p: list[float], dim: int, ridge: float) -> tuple[list[float], list[float]]:
    # size: dim+1 (bias + features)
    need = dim + 1
    if len(w) != need:
        w = (w + [0.0] * need)[:need]
    if len(p) != need:
        # diagonal P init: 1/ridge
        p = ([1.0 / max(ridge, 1e-6)] * need)
    return w, p


def online_update_diag(
    *,
    cfg: ModelConfig,
    w: list[float],
    p: list[float],
    x: list[float],
    y: float,
    example_weight: float,
) -> tuple[list[float], list[float], float]:
    """
    Cheap online ridge-ish update with diagonal preconditioner.
    Not full RLS; good enough, stable, no deps.
    """
    w, p = ensure_state(w, p, cfg.dim, cfg.ridge)

    # build xb with bias
    xb = [1.0] + list(x)
    yhat = 0.0
    for i in range(cfg.dim + 1):
        yhat += w[i] * xb[i]
    residual = y - yhat

    # robust downweight
    rw = _huber_weight(residual, cfg.huber_k)
    lr = min(0.3, max(0.02, 1.0 / math.sqrt(1.0 + (p[0] if p else 1.0))))
    step = example_weight * rw * lr

    for i in range(cfg.dim + 1):
        gi = residual * xb[i]
        w[i] += step * p[i] * gi

        # decay p slowly (more seen -> smaller steps)
        p[i] = p[i] / (1.0 + step * xb[i] * xb[i] + cfg.ridge * 1e-3)

    return w, p, residual

