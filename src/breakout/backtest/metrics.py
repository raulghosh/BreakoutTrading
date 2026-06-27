"""Expectancy metrics in R-multiples (design doc, Section 6).

R = (exit - entry) / (entry - stop). A system's edge is summarized by expectancy per trade and
profit factor; compare every variant to the naive 'buy any 52wk-high close' baseline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class Trade:
    """One closed (or marked-to-market) position from the backtest."""

    symbol: str
    entry: float
    stop: float
    exit: float
    shares: int = 0
    bars_held: int = 0
    entry_date: Any = None      # pd.Timestamp
    exit_date: Any = None       # pd.Timestamp
    exit_reason: str = ""        # stop | trail | time_stop | open

    @property
    def r_multiple(self) -> float:
        risk = self.entry - self.stop
        return (self.exit - self.entry) / risk if risk > 0 else 0.0

    @property
    def is_win(self) -> bool:
        return self.exit > self.entry

    @property
    def pnl(self) -> float:
        return (self.exit - self.entry) * self.shares


def summarize(trades: list[Trade]) -> dict:
    """Compute base rate, avg win/loss (R), expectancy (R), profit factor, etc."""
    if not trades:
        return {"n": 0}

    rs = [t.r_multiple for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)

    n = len(trades)
    return {
        "n": n,
        "win_rate": round(len(wins) / n, 4),
        "avg_win_r": round(gross_win / len(wins), 4) if wins else 0.0,
        "avg_loss_r": round(sum(losses) / len(losses), 4) if losses else 0.0,
        "expectancy_r": round(sum(rs) / n, 4),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else float("inf"),
        "total_r": round(sum(rs), 4),
        "avg_bars_held": round(sum(t.bars_held for t in trades) / n, 2),
    }


def equity_stats(equity_curve: pd.Series) -> dict:
    """Return %, max drawdown %, and start/end equity from a mark-to-market equity curve."""
    if equity_curve is None or equity_curve.empty:
        return {"n_bars": 0}

    start = float(equity_curve.iloc[0])
    end = float(equity_curve.iloc[-1])
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    max_dd = float(drawdown.min())  # most-negative point; 0 if monotonic

    return {
        "n_bars": int(len(equity_curve)),
        "start_equity": round(start, 2),
        "end_equity": round(end, 2),
        "total_return_pct": round((end / start - 1) * 100, 2) if start else 0.0,
        "max_drawdown_pct": round(max_dd * 100, 2),
    }


def buy_hold_return(df: pd.DataFrame, start, end) -> float:
    """Buy-&-hold return (%) of the symbol over [start, end], the success benchmark."""
    window = df.loc[start:end]
    if len(window) < 2:
        return 0.0
    first = float(window["close"].iloc[0])
    last = float(window["close"].iloc[-1])
    return round((last / first - 1) * 100, 2) if first else 0.0
