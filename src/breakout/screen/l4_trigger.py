"""L4 — Breakout trigger (gate). Fixes original Rules 1 & 3.

- CLOSE (not intraday) above pivot = max(52wk high, base high).
- Buffer normalized to volatility: pivot + max(atr_buffer_mult*ATR, pct_buffer*price). NOT 0.25R.
- Volume surge >= volume_mult * 50d avg on the breakout bar.
- Range expansion on the breakout bar (true range > recent average TR).
- Flags whether the breakout is also an all-time high ('blue sky', no overhead supply).
"""
from __future__ import annotations

import pandas as pd

from ..indicators import all_time_high, atr, rolling_high, true_range
from .types import LayerResult


def evaluate(df: pd.DataFrame, cfg: dict) -> LayerResult:
    close = df["close"]
    last = float(close.iloc[-1])

    # Pivot uses data THROUGH THE PRIOR bar (the level being broken), avoiding self-reference.
    hi_252_prior = float(rolling_high(close.shift(1), cfg["pivot_lookback"]).iloc[-1])
    base_hi_prior = float(rolling_high(close.shift(1), 60).iloc[-1])
    pivot = max(hi_252_prior, base_hi_prior)

    atr_now = float(atr(df, 20).iloc[-1])
    buffer = max(cfg["atr_buffer_mult"] * atr_now, cfg["pct_buffer"] * last)
    trigger_level = pivot + buffer

    tr = true_range(df)
    avg_tr = tr.iloc[-21:-1].mean()  # average TR of prior 20 bars
    range_expansion = bool(tr.iloc[-1] > avg_tr) if pd.notna(avg_tr) else False

    vol = float(df["volume"].iloc[-1])
    avg_vol = df["volume"].rolling(cfg["volume_avg_period"], min_periods=cfg["volume_avg_period"]).mean().iloc[-1]
    vol_surge = bool(pd.notna(avg_vol) and vol >= cfg["volume_mult"] * avg_vol)

    ath_prior = float(all_time_high(close.shift(1)).iloc[-1])
    is_ath = last > ath_prior

    checks = {
        "close_above_trigger": last >= trigger_level,
        "volume_surge": vol_surge,
        "range_expansion": range_expansion if cfg.get("require_range_expansion", True) else True,
    }
    return LayerResult(
        name="L4_trigger",
        kind="gate",
        passed=all(checks.values()),
        detail={"pivot": pivot, "buffer": buffer, "trigger_level": trigger_level,
                "close": last, "atr": atr_now, "volume": vol,
                "avg_volume": float(avg_vol) if pd.notna(avg_vol) else None,
                "is_ath_breakout": is_ath, **checks},
    )
