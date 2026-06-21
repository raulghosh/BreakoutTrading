"""Core indicators. All functions take back-adjusted OHLCV and use only past/current data
(no look-ahead) so they are safe in a point-in-time backtest.

Conventions:
- `df` is a DataFrame indexed by date (ascending) with columns: open, high, low, close, volume.
- Functions return a Series aligned to `df.index` (NaN during warm-up) unless noted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def validate_ohlcv(df: pd.DataFrame) -> None:
    """Raise if df is missing columns or is not sorted ascending by index."""
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV frame missing columns: {missing}")
    if not df.index.is_monotonic_increasing:
        raise ValueError("OHLCV frame must be sorted ascending by date index")


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=period).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    """True range = max(high-low, |high-prev_close|, |low-prev_close|)."""
    prev_close = df["close"].shift(1)
    hl = df["high"] - df["low"]
    hc = (df["high"] - prev_close).abs()
    lc = (df["low"] - prev_close).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Average True Range via Wilder's smoothing (RMA)."""
    tr = true_range(df)
    # Wilder's smoothing == EMA with alpha = 1/period.
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def rolling_high(series: pd.Series, period: int) -> pd.Series:
    """Highest value over the trailing `period` bars (inclusive)."""
    return series.rolling(window=period, min_periods=1).max()


def rolling_low(series: pd.Series, period: int) -> pd.Series:
    """Lowest value over the trailing `period` bars (inclusive)."""
    return series.rolling(window=period, min_periods=1).min()


def all_time_high(series: pd.Series) -> pd.Series:
    """Expanding (point-in-time) all-time high — for the 'blue-sky' ATH flag (L4)."""
    return series.expanding(min_periods=1).max()


def dollar_volume(df: pd.DataFrame) -> pd.Series:
    """Per-bar traded dollar volume (close * volume) — liquidity proxy (L0)."""
    return df["close"] * df["volume"]


def avg_dollar_volume(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Trailing average dollar volume."""
    return dollar_volume(df).rolling(window=period, min_periods=period).mean()


def bollinger_width(close: pd.Series, period: int = 20, n_std: float = 2.0) -> pd.Series:
    """Bollinger-band width normalized by the mid band: (upper-lower)/mid.

    Low values = volatility contraction / squeeze (the L3 'early' setup).
    """
    mid = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    return (2 * n_std * std) / mid


def percentile_rank(series: pd.Series, lookback: int) -> pd.Series:
    """Rolling percentile (0-1) of the latest value within its trailing window.

    Used to express 'ATR%/BB-width sitting in a low percentile vs its own year' (L3).
    A value of 0.05 means tighter than 95% of the lookback window.
    """

    def _rank(window: np.ndarray) -> float:
        last = window[-1]
        return float((window <= last).sum() - 1) / (len(window) - 1) if len(window) > 1 else np.nan

    return series.rolling(window=lookback, min_periods=max(2, lookback // 4)).apply(_rank, raw=True)


def pct_return(close: pd.Series, lookback: int) -> pd.Series:
    """Trailing simple return over `lookback` bars — basis for RS rank (L3/L5)."""
    return close / close.shift(lookback) - 1.0


def rs_line(close: pd.Series, benchmark_close: pd.Series) -> pd.Series:
    """Relative-strength line = stock / benchmark, aligned on index.

    New highs in the RS line often lead price (L3). Benchmark is reindexed to the stock's dates.
    """
    bench = benchmark_close.reindex(close.index).ffill()
    return close / bench
