"""Synthetic OHLCV generators — let tests and the CLI demo run with no API keys.

`make_breakout_series` produces a textbook setup: uptrend -> tight base (volatility contraction)
-> breakout bar with volume + range expansion. `make_benchmark` is an uptrending index.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _frame(dates, close, volume) -> pd.DataFrame:
    close = np.asarray(close, dtype=float)
    high = close * 1.005
    low = close * 0.995
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=pd.DatetimeIndex(dates, name="date"),
    )


def make_benchmark(n: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)
    drift = np.linspace(0, 0.35, n)  # steady uptrend -> above rising 200d MA
    noise = np.cumsum(rng.normal(0, 0.004, n))
    close = 400 * np.exp(drift + noise)
    return _frame(dates, close, np.full(n, 1_000_000.0))


def make_breakout_series(n: int = 400, seed: int = 7) -> pd.DataFrame:
    """Stage-2 uptrend, then a tight base, then a clean breakout on the final bar."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)

    base_len = 25
    trend_len = n - base_len - 1

    # 1) uptrend
    trend = np.cumsum(rng.normal(0.0016, 0.012, trend_len))
    trend_close = 20 * np.exp(trend)
    pivot = trend_close[-1]

    # 2) tight base just below the pivot — volatility contraction
    base_close = pivot * (1 + rng.normal(0, 0.006, base_len)) * 0.985

    # 3) breakout bar: clear the actual prior 52wk high (a random walk can peak above its
    #    last value) plus a comfortable ATR/%% buffer.
    prior_high = max(trend_close.max(), base_close.max())
    breakout = np.array([prior_high * 1.08])

    close = np.concatenate([trend_close, base_close, breakout])

    volume = np.full(n, 1_200_000.0)
    volume[trend_len:-1] = 900_000.0  # quieter base (but still liquid)
    volume[-1] = 3_000_000.0  # volume surge on breakout (> 1.5x 50d avg)

    df = _frame(dates, close, volume)
    df.iloc[-1, df.columns.get_loc("high")] = float(close[-1]) * 1.02  # range expansion
    df.iloc[-1, df.columns.get_loc("low")] = float(close[-2]) * 1.0
    return df


def make_trade_path(outcome: str = "win", seed: int = 7) -> pd.DataFrame:
    """A full trade path for the backtest: warmup uptrend → base → breakout → continuation.

    `make_breakout_series` ends ON the breakout bar, so it cannot be backtested (there is no bar
    to enter on). This appends a deterministic continuation that produces a known outcome:

    - "win"     : runs well past the first target, then drops sharply → scale-out + trailing exit
    - "loss"    : falls straight through the initial stop → ~ -1R stop-out
    - "timeout" : drifts flat (no target, no stop) past the time stop → time-decay exit
    """
    base = make_breakout_series(seed=seed)            # ends on the breakout bar
    breakout_close = float(base["close"].iloc[-1])
    last_date = base.index[-1]

    P = breakout_close
    if outcome == "win":
        # ramp up ~25% over 12 bars, then one sharp -20% bar to trip the trailing stop
        path = [P * m for m in (1.05, 1.10, 1.14, 1.17, 1.20, 1.22, 1.24,
                                1.25, 1.26, 1.27, 1.28, 1.29)] + [P * 1.03]
    elif outcome == "loss":
        # gap/slide straight down through any reasonable stop within a few bars
        path = [P * 0.97, P * 0.93, P * 0.88, P * 0.85]
    elif outcome == "timeout":
        # hover around the entry: above the stop, below the target, for > time_stop_days bars
        path = [P * 1.005, P * 0.998] * 12
    else:
        raise ValueError(f"unknown outcome: {outcome!r}")

    cont_dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=len(path))
    cont_close = np.asarray(path, dtype=float)
    cont = pd.DataFrame(
        {
            "open": np.r_[breakout_close, cont_close[:-1]],
            "high": cont_close * 1.01,
            "low": cont_close * 0.99,
            "close": cont_close,
            "volume": np.full(len(path), 1_200_000.0),
        },
        index=pd.DatetimeIndex(cont_dates, name="date"),
    )
    return pd.concat([base, cont])
