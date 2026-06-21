"""Data layer (Phase 1): provider interfaces, bar store, back-adjustment.

Indicators are computed from the cache so the backtest and live screen share one code path.
"""

from .base import BarProvider, NewsItem, NewsProvider  # noqa: F401
from .store import BarStore  # noqa: F401
