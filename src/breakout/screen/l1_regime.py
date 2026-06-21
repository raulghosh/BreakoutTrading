"""L1 — Market regime (gate that scales exposure).

Breakouts work when the broad market trends up; they fail in chop/bear. We return both a hard
`passed` and a soft `score` so callers can choose an on/off gate or scale sizing/position-count.
"""
from __future__ import annotations

import pandas as pd

from ..indicators import sma
from .types import LayerResult


def evaluate(benchmark_df: pd.DataFrame, cfg: dict) -> LayerResult:
    close = benchmark_df["close"]
    ma = sma(close, cfg["ma_period"])
    last_close = float(close.iloc[-1])
    last_ma = float(ma.iloc[-1])
    lookback = cfg.get("rising_lookback", 21)
    rising = bool(ma.iloc[-1] > ma.iloc[-1 - lookback]) if len(ma) > lookback else False

    above = last_close > last_ma
    passed = True
    if cfg.get("require_above_ma", True):
        passed = passed and above
    if cfg.get("require_rising_ma", True):
        passed = passed and rising

    # Soft score: blends "above MA" and "MA rising" for exposure scaling.
    above_pct = (last_close / last_ma - 1.0) if last_ma else 0.0
    score = max(0.0, min(1.0, 0.5 * (above_pct > 0) + 0.5 * rising + min(above_pct, 0.1) * 5))
    score = max(0.0, min(1.0, score))

    return LayerResult(
        name="L1_regime",
        kind="gate",
        passed=passed,
        score=score,
        detail={"benchmark_close": last_close, "ma": last_ma, "above_ma": above,
                "ma_rising": rising, "above_pct": above_pct},
    )
