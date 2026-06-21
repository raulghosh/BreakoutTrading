"""Split/dividend back-adjustment. Must run BEFORE computing highs/MAs/ATR, or 52wk highs are
wrong around corporate actions (design doc, Section 3)."""
from __future__ import annotations

import pandas as pd


def back_adjust_splits(df: pd.DataFrame, splits: pd.Series) -> pd.DataFrame:
    """Adjust OHLC and volume for splits.

    `splits` is a Series indexed by ex-date with the split ratio (e.g. 2.0 for a 2:1 split).
    Prices before an ex-date are divided by the cumulative forward ratio; volume is multiplied.
    """
    if splits is None or splits.empty:
        return df.copy()

    out = df.copy()
    # Cumulative adjustment factor that applies to bars strictly before each ex-date.
    factor = pd.Series(1.0, index=out.index)
    for ex_date, ratio in splits.sort_index().items():
        mask = out.index < ex_date
        factor[mask] *= ratio

    for col in ("open", "high", "low", "close"):
        if col in out:
            out[col] = out[col] / factor
    if "volume" in out:
        out["volume"] = out["volume"] * factor
    return out
