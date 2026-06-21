"""Alpaca adapter — bulk daily/weekly bars + news (Benzinga feed).

Phase 1 stub: typed and wired to config, but the network calls raise NotImplementedError until
the `data` extra is installed and keys are set. This keeps the package importable and the screen
runnable on cached/synthetic bars without the SDK.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..config import Secrets
from .base import BarProvider, NewsItem, NewsProvider


class AlpacaProvider(BarProvider, NewsProvider):
    def __init__(self, secrets: Secrets | None = None):
        self.secrets = secrets or Secrets.from_env()
        self._client = None

    def _require_client(self):
        if not (self.secrets.alpaca_key and self.secrets.alpaca_secret):
            raise NotImplementedError(
                "Alpaca credentials missing. Set ALPACA_API_KEY/ALPACA_SECRET_KEY in .env and "
                "install extras: pip install -e '.[data]'."
            )
        # TODO(Phase 1): lazily construct alpaca-py StockHistoricalDataClient / NewsClient.
        raise NotImplementedError("AlpacaProvider network calls not yet implemented (Phase 1).")

    def daily_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        self._require_client()

    def weekly_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        self._require_client()

    def news(self, symbol: str, start: datetime, end: datetime) -> list[NewsItem]:
        self._require_client()
