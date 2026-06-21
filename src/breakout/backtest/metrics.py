"""Expectancy metrics in R-multiples (design doc, Section 6).

R = (exit - entry) / (entry - stop). A system's edge is summarized by expectancy per trade and
profit factor; compare every variant to the naive 'buy any 52wk-high close' baseline.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Trade:
    symbol: str
    entry: float
    stop: float
    exit: float
    bars_held: int = 0

    @property
    def r_multiple(self) -> float:
        risk = self.entry - self.stop
        return (self.exit - self.entry) / risk if risk > 0 else 0.0

    @property
    def is_win(self) -> bool:
        return self.exit > self.entry


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
