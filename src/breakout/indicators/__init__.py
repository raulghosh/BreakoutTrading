"""Shared indicator library — the SINGLE source used by both the live screen and the backtest.

Never duplicate this math elsewhere: a divergence between screen and backtest indicators is the
#1 cause of "works in backtest, fails live" (design doc, Section 3).
"""

from .core import (  # noqa: F401
    OHLCV_COLUMNS,
    all_time_high,
    atr,
    avg_dollar_volume,
    bollinger_width,
    dollar_volume,
    pct_return,
    percentile_rank,
    rolling_high,
    rolling_low,
    rs_line,
    sma,
    true_range,
    validate_ohlcv,
)
