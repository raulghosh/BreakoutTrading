"""L0 — Universe & liquidity (gate). Drops untradeable / noisy names."""
from __future__ import annotations

import pandas as pd

from ..indicators import avg_dollar_volume
from .types import LayerResult


def evaluate(df: pd.DataFrame, cfg: dict, *, is_leveraged_etf: bool = False) -> LayerResult:
    n = len(df)
    last = df.iloc[-1]
    adv = avg_dollar_volume(df, period=20).iloc[-1]

    checks = {
        "price_ok": float(last["close"]) >= cfg["min_price"],
        "dollar_vol_ok": pd.notna(adv) and adv >= cfg["min_dollar_volume"],
        "history_ok": n >= cfg["min_history_days"],
        "not_excluded_etf": not (cfg.get("exclude_leveraged_etfs", True) and is_leveraged_etf),
    }
    return LayerResult(
        name="L0_universe",
        kind="gate",
        passed=all(checks.values()),
        detail={"price": float(last["close"]), "avg_dollar_volume": float(adv) if pd.notna(adv) else None,
                "bars": n, **checks},
    )
