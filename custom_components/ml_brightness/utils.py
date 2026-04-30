"""Pure helpers (no Home Assistant imports) for ML Brightness."""

from __future__ import annotations

import math
from datetime import datetime


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def weighted_median(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    pairs = sorted(pairs, key=lambda t: t[0])
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    acc = 0.0
    for y, w in pairs:
        acc += w
        if acc >= total * 0.5:
            return y
    return pairs[-1][0]


def knn_predict_median(examples: list[dict], x: list[float]) -> tuple[float | None, float]:
    if not examples:
        return None, 0.0
    scored: list[tuple[float, float]] = []
    for ex in examples[-250:]:
        xv = ex.get("x")
        yv = ex.get("y")
        if not isinstance(xv, list) or yv is None:
            continue
        d = 0.0
        for i in range(min(len(x), len(xv))):
            di = float(x[i]) - float(xv[i])
            d += di * di
        d = math.sqrt(d)
        w = 1.0 / (0.15 + d)
        scored.append((float(yv), w))
    scored.sort(key=lambda t: t[1], reverse=True)
    top = scored[:25]
    pred = weighted_median(top)
    conf = min(1.0, len(top) / 40.0)
    return pred, conf


def parse_hhmm(s: str) -> tuple[int, int] | None:
    try:
        parts = s.strip().split(":")
        if len(parts) != 2:
            return None
        h = int(parts[0])
        m = int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return h, m
    except (ValueError, AttributeError):
        return None


def in_time_window(now: datetime, start: str, end: str) -> bool:
    st = parse_hhmm(start)
    en = parse_hhmm(end)
    if not st or not en:
        return False
    cur = now.hour * 60 + now.minute
    s = st[0] * 60 + st[1]
    e = en[0] * 60 + en[1]
    if s == e:
        return False
    if s < e:
        return s <= cur < e
    return cur >= s or cur < e
