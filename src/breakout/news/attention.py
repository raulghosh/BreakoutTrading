"""Attention / abnormality signals (Section 5.3). Cheap, powerful, often LEAD price.

- news-volume spike: z-score of daily article count for a ticker/theme
- options activity: call-volume & IV jumps (Schwab chains)
- optional: social-mention / search velocity

The news-volume z-score is implemented (pure function); options/IV need the Schwab feed (Phase 5).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def news_volume_zscore(daily_counts: pd.Series, lookback: int = 60) -> float:
    """Z-score of the latest day's article count vs its trailing window. >2 ≈ abnormal attention."""
    if len(daily_counts) < 2:
        return 0.0
    window = daily_counts.iloc[-lookback:]
    mean = window.mean()
    std = window.std(ddof=0)
    if not std or np.isnan(std):
        return 0.0
    return float((daily_counts.iloc[-1] - mean) / std)


def options_activity_score(call_volume: float, avg_call_volume: float, iv_change: float) -> float:
    """Placeholder blend of unusual call volume + IV jump. Wire to Schwab chains in Phase 5."""
    vol_ratio = (call_volume / avg_call_volume) if avg_call_volume else 0.0
    return float(np.clip(0.6 * np.tanh(vol_ratio - 1) + 0.4 * np.tanh(iv_change * 5), 0, 1))
