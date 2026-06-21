"""Point-in-time, leak-free backtest loop (Phase 3 scaffold).

Non-negotiables enforced by this design (design doc, Section 6):
- point-in-time universe (include delisted names) — pass a membership function
- indicators use data through the signal bar only (screen_symbol already truncates)
- entry on the NEXT bar's open, not the signal close
- costs: commission + slippage (larger for breakout fills; gap-ups fill worse)

The trade-management loop (stop / time-stop / partial / fast-exit-below-pivot) is TODO; the
interface and cost model are defined so Phase 2 signals can be wired in immediately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from ..screen.funnel import screen_symbol
from .metrics import Trade, summarize


@dataclass
class CostModel:
    commission_per_share: float = 0.0
    slippage_bps: float = 15.0  # breakout fills slip; model gap-ups worse separately

    def apply_buy(self, price: float) -> float:
        return price * (1 + self.slippage_bps / 1e4) + self.commission_per_share


@dataclass
class BacktestConfig:
    account_equity: float = 100_000.0
    cost: CostModel = field(default_factory=CostModel)
    min_composite: float = 0.0  # only act on signals above this rank


def run_backtest(
    symbols: list[str],
    load_bars: Callable[[str], pd.DataFrame],
    benchmark_df: pd.DataFrame,
    settings,
    dates: pd.DatetimeIndex,
    config: BacktestConfig | None = None,
) -> dict:
    """Walk `dates`, screen each symbol on data through that date, manage resulting trades.

    Currently produces signals and the trade list scaffold; the position-management loop is the
    remaining Phase 3 work (marked TODO below).
    """
    config = config or BacktestConfig()
    trades: list[Trade] = []
    signals: list[dict] = []

    for ts in dates:
        bench = benchmark_df.loc[:ts]
        if len(bench) < settings.regime["ma_period"]:
            continue
        for sym in symbols:
            full = load_bars(sym)
            df = full.loc[:ts]  # point-in-time truncation — no look-ahead
            if len(df) < settings.universe["min_history_days"]:
                continue
            cand = screen_symbol(sym, df, settings, benchmark_df=bench,
                                 account_equity=config.account_equity)
            if cand.passed_gates and (cand.composite or 0) >= config.min_composite:
                signals.append({"date": ts, "symbol": sym, "composite": cand.composite,
                                "risk": cand.risk})
                # TODO(Phase 3): enter on next bar's open via config.cost; manage stop/target/
                # time-stop/fast-exit-below-pivot; append closed positions to `trades`.

    return {"signals": signals, "trades": trades, "metrics": summarize(trades)}
