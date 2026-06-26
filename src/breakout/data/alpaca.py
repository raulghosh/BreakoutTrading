"""Alpaca adapter — daily/weekly bars (split-adjusted + total-return) and news.

Requires:
    pip install -e '.[data]'

And in .env:
    ALPACA_API_KEY=your_key
    ALPACA_SECRET_KEY=your_secret
    ALPACA_DATA_FEED=iex          # or sip (paid tier, full tape)
    ALPACA_PAPER=true             # true = paper account endpoint, false = live

Adjustment policy (design doc §4):
    daily_bars()        → Adjustment.SPLIT   (for breakout levels, pivots, ATR, MAs)
    total_return_bars() → Adjustment.ALL     (for RS line and backtest P&L)
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ..config import Secrets
from .base import BarProvider, NewsItem, NewsProvider

_OHLCV = ["open", "high", "low", "close", "volume"]


def _to_df(response, symbol: str) -> pd.DataFrame:
    """Normalize an alpaca-py BarSet to our OHLCV DataFrame (date index, ascending)."""
    try:
        df = response.df
    except Exception:
        return pd.DataFrame(columns=_OHLCV)

    if df is None or df.empty:
        return pd.DataFrame(columns=_OHLCV)

    # BarSet.df has MultiIndex (symbol, timestamp) even for single-symbol requests
    if isinstance(df.index, pd.MultiIndex):
        if symbol not in df.index.get_level_values(0):
            return pd.DataFrame(columns=_OHLCV)
        df = df.xs(symbol, level=0)

    # Strip timezone, normalize timestamp → date (midnight)
    idx = df.index
    if hasattr(idx, "tz") and idx.tz is not None:
        idx = idx.tz_convert(None)
    df.index = pd.DatetimeIndex(idx).normalize()
    df.index.name = "date"

    missing = [c for c in _OHLCV if c not in df.columns]
    if missing:
        raise ValueError(f"Alpaca response missing columns for {symbol}: {missing}")

    return df[_OHLCV].sort_index()


class AlpacaProvider(BarProvider, NewsProvider):
    """Wraps alpaca-py for bar and news data.

    All clients are constructed lazily — the object is cheap to create and
    importable without the SDK installed (it raises only on first use).
    """

    def __init__(self, secrets: Secrets | None = None):
        self.secrets = secrets or Secrets.from_env()
        self._hist_client = None
        self._news_client = None
        self._trading_client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_creds(self) -> None:
        if not (self.secrets.alpaca_key and self.secrets.alpaca_secret):
            raise RuntimeError(
                "Alpaca credentials missing — set ALPACA_API_KEY and ALPACA_SECRET_KEY "
                "in .env and run: pip install -e '.[data]'"
            )

    def _require_hist_client(self):
        self._check_creds()
        if self._hist_client is None:
            try:
                from alpaca.data.historical import StockHistoricalDataClient
            except ImportError as exc:
                raise RuntimeError("Run: pip install -e '.[data]'") from exc
            self._hist_client = StockHistoricalDataClient(
                self.secrets.alpaca_key, self.secrets.alpaca_secret
            )
        return self._hist_client

    def _require_trading_client(self):
        self._check_creds()
        if self._trading_client is None:
            try:
                from alpaca.trading.client import TradingClient
            except ImportError as exc:
                raise RuntimeError("Run: pip install -e '.[data]'") from exc
            self._trading_client = TradingClient(
                self.secrets.alpaca_key,
                self.secrets.alpaca_secret,
                paper=self.secrets.alpaca_paper,
            )
        return self._trading_client

    def _feed_enum(self):
        try:
            from alpaca.data.enums import DataFeed
        except ImportError as exc:
            raise RuntimeError("Run: pip install -e '.[data]'") from exc
        return {"iex": DataFeed.IEX, "sip": DataFeed.SIP}.get(
            (self.secrets.alpaca_feed or "iex").lower(), DataFeed.IEX
        )

    def _fetch_bars(
        self, symbol: str, start: datetime, end: datetime, adjustment: str
    ) -> pd.DataFrame:
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            from alpaca.data.enums import Adjustment
        except ImportError as exc:
            raise RuntimeError("Run: pip install -e '.[data]'") from exc

        adj_map = {
            "split": Adjustment.SPLIT,
            "all": Adjustment.ALL,
            "raw": Adjustment.RAW,
            "dividend": Adjustment.DIVIDEND,
        }
        client = self._require_hist_client()
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment=adj_map[adjustment],
            feed=self._feed_enum(),
        )
        return _to_df(client.get_stock_bars(req), symbol)

    # ------------------------------------------------------------------
    # BarProvider protocol
    # ------------------------------------------------------------------

    def daily_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Split-adjusted OHLCV — breakout levels, pivots, ATR, MA stack."""
        return self._fetch_bars(symbol, start, end, "split")

    def total_return_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Split + dividend adjusted OHLCV — RS line and backtest P&L."""
        return self._fetch_bars(symbol, start, end, "all")

    def weekly_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            from alpaca.data.enums import Adjustment
        except ImportError as exc:
            raise RuntimeError("Run: pip install -e '.[data]'") from exc

        client = self._require_hist_client()
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Week,
            start=start,
            end=end,
            adjustment=Adjustment.SPLIT,
            feed=self._feed_enum(),
        )
        return _to_df(client.get_stock_bars(req), symbol)

    # ------------------------------------------------------------------
    # Universe
    # ------------------------------------------------------------------

    def active_us_equities(self) -> list[str]:
        """Sorted list of active, tradeable US equity tickers from Alpaca.

        Filters to alpha-only symbols (≤5 chars) to exclude warrants, units,
        rights, and other derivatives. The L0 gate further filters by liquidity.
        """
        try:
            from alpaca.trading.requests import GetAssetsRequest
            from alpaca.trading.enums import AssetClass, AssetStatus
        except ImportError as exc:
            raise RuntimeError("Run: pip install -e '.[data]'") from exc

        client = self._require_trading_client()
        req = GetAssetsRequest(
            asset_class=AssetClass.US_EQUITY,
            status=AssetStatus.ACTIVE,
        )
        assets = client.get_all_assets(req)
        return sorted(
            a.symbol
            for a in assets
            if a.tradable and a.symbol.isalpha() and len(a.symbol) <= 5
        )

    # ------------------------------------------------------------------
    # NewsProvider protocol
    # ------------------------------------------------------------------

    def news(self, symbol: str, start: datetime, end: datetime) -> list[NewsItem]:
        """News via Alpaca's Benzinga feed. Returned in ascending timestamp order."""
        self._check_creds()
        try:
            try:
                from alpaca.data.historical.news import NewsClient
            except ImportError:
                from alpaca.data.historical import NewsClient  # older alpaca-py layout
            from alpaca.data.requests import NewsRequest
        except ImportError as exc:
            raise RuntimeError("Run: pip install -e '.[data]'") from exc

        if self._news_client is None:
            self._news_client = NewsClient(
                self.secrets.alpaca_key, self.secrets.alpaca_secret
            )
        req = NewsRequest(symbols=[symbol], start=start, end=end, limit=50)
        response = self._news_client.get_news(req)
        return [
            NewsItem(
                symbol=symbol,
                timestamp=article.created_at,
                headline=article.headline,
                body=article.summary or "",
                source=article.author or "alpaca/benzinga",
                url=article.url,
            )
            for article in response.news
        ]
