"""Provider-agnostic interfaces. Concrete adapters (Alpaca, Schwab) implement these so the rest
of the system never imports a vendor SDK directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class BarProvider(Protocol):
    """Returns back-adjusted OHLCV bars indexed by date (ascending)."""

    def daily_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Columns: open, high, low, close, volume. Split/dividend adjusted."""
        ...

    def weekly_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        ...


@dataclass
class NewsItem:
    symbol: str
    timestamp: datetime
    headline: str
    body: str
    source: str
    url: str | None = None


@runtime_checkable
class NewsProvider(Protocol):
    """Time-stamped news for the catalyst overlay. MUST support point-in-time queries
    (only items <= `as_of`) to keep the backtest leak-free (design doc, Section 6)."""

    def news(self, symbol: str, start: datetime, end: datetime) -> list[NewsItem]:
        ...
