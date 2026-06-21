"""Local bar cache (Parquet) keyed by symbol. Indicators are recomputed from the cache so the
backtest and live screen are byte-for-byte identical (design doc, Section 3)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..indicators import OHLCV_COLUMNS

DEFAULT_CACHE = Path("data/cache")


class BarStore:
    def __init__(self, root: str | Path = DEFAULT_CACHE):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str, freq: str = "daily") -> Path:
        return self.root / f"{symbol.upper()}_{freq}.parquet"

    def has(self, symbol: str, freq: str = "daily") -> bool:
        return self._path(symbol, freq).exists()

    def save(self, symbol: str, df: pd.DataFrame, freq: str = "daily") -> None:
        missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"refusing to cache {symbol}: missing {missing}")
        df.sort_index().to_parquet(self._path(symbol, freq))

    def load(self, symbol: str, freq: str = "daily") -> pd.DataFrame:
        df = pd.read_parquet(self._path(symbol, freq))
        return df.sort_index()

    def symbols(self, freq: str = "daily") -> list[str]:
        suffix = f"_{freq}.parquet"
        return sorted(p.name[: -len(suffix)] for p in self.root.glob(f"*{suffix}"))
