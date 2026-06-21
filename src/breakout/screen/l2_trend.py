"""L2 — Trend template (gate). Minervini-style Stage-2 uptrend.

Removes most failed breakouts, which originate in downtrends.
"""
from __future__ import annotations

import pandas as pd

from ..indicators import rolling_high, rolling_low, sma
from .types import LayerResult


def evaluate(df: pd.DataFrame, cfg: dict) -> LayerResult:
    close = df["close"]
    last = float(close.iloc[-1])
    tol = cfg.get("tolerance", 0.0)

    ma_f = sma(close, cfg["ma_fast"]).iloc[-1]
    ma_m = sma(close, cfg["ma_mid"]).iloc[-1]
    ma_s = sma(close, cfg["ma_slow"]).iloc[-1]

    slow_series = sma(close, cfg["ma_slow"])
    lb = cfg.get("slow_rising_lookback", 21)
    slow_rising = bool(slow_series.iloc[-1] > slow_series.iloc[-1 - lb]) if len(slow_series) > lb else False

    hi_52 = float(rolling_high(close, 252).iloc[-1])
    lo_52 = float(rolling_low(close, 252).iloc[-1])

    checks = {
        "close_gt_fast": pd.notna(ma_f) and last >= ma_f * (1 - tol),
        "fast_gt_mid": pd.notna(ma_m) and ma_f >= ma_m * (1 - tol),
        "mid_gt_slow": pd.notna(ma_s) and ma_m >= ma_s * (1 - tol),
        "slow_rising": slow_rising,
        "within_high": last >= hi_52 * (1 - cfg["within_high_pct"]),
        "above_low": last >= lo_52 * (1 + cfg["above_low_pct"]),
    }
    return LayerResult(
        name="L2_trend",
        kind="gate",
        passed=all(checks.values()),
        detail={"ma_fast": _f(ma_f), "ma_mid": _f(ma_m), "ma_slow": _f(ma_s),
                "high_52w": hi_52, "low_52w": lo_52, **checks},
    )


def _f(v) -> float | None:
    return float(v) if pd.notna(v) else None
