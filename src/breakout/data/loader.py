"""Convenience loader: read bars from the local cache, fetching from Alpaca if missing.

Used by the notebooks and any quick script so they don't each re-implement the
cache-then-fetch dance. The CLI `fetch` command remains the canonical way to populate
the cache in bulk.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from .store import BarStore


def load_or_fetch(
    symbol: str,
    *,
    lookback_days: int = 730,
    cache: str = "data/cache",
    fetch_if_missing: bool = True,
    refetch: bool = False,
) -> pd.DataFrame:
    """Return split-adjusted daily bars for `symbol`.

    Reads the Parquet cache first. If the symbol is missing (or `refetch=True`) and
    `fetch_if_missing` is set, downloads `lookback_days` of history from Alpaca and caches it.
    Raises a clear error if the symbol is absent and fetching is disabled or has no credentials.
    """
    store = BarStore(cache)
    if store.has(symbol) and not refetch:
        return store.load(symbol)

    if not fetch_if_missing:
        raise FileNotFoundError(
            f"{symbol} not in cache ({cache}). Run: breakout fetch {symbol}"
        )

    # Lazy import so the package stays importable without the [data] extra.
    from .alpaca import AlpacaProvider

    provider = AlpacaProvider()
    end = datetime.today()
    start = end - timedelta(days=lookback_days)
    df = provider.daily_bars(symbol, start, end)
    if df.empty:
        raise ValueError(f"no bars returned for {symbol} from Alpaca")
    store.save(symbol, df)
    return df
