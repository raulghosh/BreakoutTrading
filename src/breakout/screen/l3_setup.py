"""L3 — Setup quality (score) — the 'early' fix.

Rewards volatility CONTRACTION before the break (squeeze), a tight/shallow base, and strong
relative strength. Score in [0, 1]; higher = better setup.
"""
from __future__ import annotations

import pandas as pd

from ..indicators import atr, bollinger_width, percentile_rank, rolling_high, rs_line
from .types import LayerResult


def evaluate(df: pd.DataFrame, cfg: dict, *, benchmark_df: pd.DataFrame | None = None,
             rs_rank_pct: float | None = None) -> LayerResult:
    close = df["close"]

    # --- volatility contraction (squeeze): low BB-width percentile = tight ---
    bbw = bollinger_width(close, period=cfg["bbwidth_period"])
    bbw_pctile = percentile_rank(bbw, cfg["bbwidth_lookback"]).iloc[-1]
    squeeze_score = (1.0 - bbw_pctile) if pd.notna(bbw_pctile) else 0.0

    # --- base tightness/depth: shallow drawdown from recent base high = tight ---
    base_hi = float(rolling_high(close, cfg["base_lookback"]).iloc[-1])
    last = float(close.iloc[-1])
    depth = (base_hi - last) / base_hi if base_hi else 1.0  # 0 = at highs
    tightness_score = max(0.0, 1.0 - depth / 0.15)  # full credit if within 15% of base high

    # --- ATR% also low (corroborates squeeze) ---
    atr_pct = (atr(df, cfg["atr_period"]).iloc[-1] / last) if last else None

    # --- relative strength: RS line near its own highs + cross-sectional rank (if provided) ---
    rs_score = 0.0
    rs_detail: dict = {}
    if benchmark_df is not None:
        rsl = rs_line(close, benchmark_df["close"])
        rs_hi = rolling_high(rsl, cfg["rs_lookback"]).iloc[-1]
        rs_now = rsl.iloc[-1]
        if pd.notna(rs_hi) and rs_hi:
            near = float(rs_now / rs_hi)  # ~1.0 means RS line at new highs
            rs_score = max(0.0, min(1.0, (near - 0.9) / 0.1))
            rs_detail = {"rs_line_near_high": near}
    if rs_rank_pct is not None:  # cross-sectional percentile from the universe pass
        rs_score = max(rs_score, float(rs_rank_pct))
        rs_detail["rs_rank_pct"] = float(rs_rank_pct)

    score = 0.45 * squeeze_score + 0.25 * tightness_score + 0.30 * rs_score
    return LayerResult(
        name="L3_setup",
        kind="score",
        score=round(float(max(0.0, min(1.0, score))), 4),
        detail={"bbwidth_percentile": _f(bbw_pctile), "squeeze_score": round(squeeze_score, 4),
                "base_depth": round(depth, 4), "tightness_score": round(tightness_score, 4),
                "atr_pct": _f(atr_pct), "rs_score": round(rs_score, 4), **rs_detail},
    )


def _f(v) -> float | None:
    return float(v) if v is not None and pd.notna(v) else None
