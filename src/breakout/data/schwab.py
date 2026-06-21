"""Schwab Trader API adapter — intraday cross-check, options chains (attention/IV), fundamentals,
movers. Phase 1 stub (see alpaca.py for the same pattern)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..config import Secrets
from .base import BarProvider


class SchwabProvider(BarProvider):
    def __init__(self, secrets: Secrets | None = None):
        self.secrets = secrets or Secrets.from_env()

    def _require_client(self):
        if not (self.secrets.schwab_app_key and self.secrets.schwab_app_secret):
            raise NotImplementedError(
                "Schwab credentials missing. Set SCHWAB_APP_KEY/SCHWAB_APP_SECRET in .env. "
                "Schwab uses OAuth — see docs/breakout_strategy_design.md Section 3."
            )
        raise NotImplementedError("SchwabProvider not yet implemented (Phase 1).")

    def daily_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        self._require_client()

    def weekly_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        self._require_client()

    # Phase 1+ extensions (options chains for IV/attention, fundamentals, movers) land here.
    def option_chain(self, symbol: str):  # pragma: no cover - stub
        self._require_client()

    def movers(self, index: str = "$SPX"):  # pragma: no cover - stub
        self._require_client()
