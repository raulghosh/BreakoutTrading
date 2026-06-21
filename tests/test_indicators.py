import numpy as np
import pandas as pd

from breakout.indicators import (
    all_time_high,
    atr,
    avg_dollar_volume,
    bollinger_width,
    pct_return,
    percentile_rank,
    rolling_high,
    rs_line,
    sma,
)
from breakout.synthetic import make_breakout_series


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = sma(s, 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == 2.0
    assert out.iloc[4] == 4.0


def test_atr_positive_and_warmup():
    df = make_breakout_series(n=120)
    a = atr(df, 20)
    assert a.iloc[:19].isna().all()
    assert (a.dropna() > 0).all()


def test_rolling_and_ath():
    s = pd.Series([1, 3, 2, 5, 4], dtype=float)
    assert list(rolling_high(s, 2)) == [1, 3, 3, 5, 5]
    assert list(all_time_high(s)) == [1, 3, 3, 5, 5]


def test_percentile_rank_bounds():
    s = pd.Series(np.arange(100, dtype=float))
    pr = percentile_rank(s, 50)
    last = pr.iloc[-1]
    assert 0.0 <= last <= 1.0
    assert last > 0.9  # latest is the max in its window


def test_bollinger_width_contraction():
    # tight series -> small width; widening series -> larger width
    tight = pd.Series(np.r_[np.full(40, 100.0)] + np.random.default_rng(0).normal(0, 0.05, 40))
    wide = pd.Series(100 + np.cumsum(np.random.default_rng(0).normal(0, 2, 40)))
    assert bollinger_width(tight, 20).iloc[-1] < bollinger_width(wide, 20).iloc[-1]


def test_dollar_volume_and_returns():
    df = make_breakout_series(n=60)
    assert (avg_dollar_volume(df, 20).dropna() > 0).all()
    assert not np.isnan(pct_return(df["close"], 20).iloc[-1])


def test_rs_line_alignment():
    df = make_breakout_series(n=60)
    bench = df.copy()
    rsl = rs_line(df["close"], bench["close"])
    assert np.allclose(rsl.dropna(), 1.0)  # identical series -> RS line flat at 1
