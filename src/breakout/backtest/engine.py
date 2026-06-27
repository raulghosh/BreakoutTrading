"""Point-in-time, leak-free backtest engine (Track A).

Non-negotiables (design doc, Section 6):
- indicators use data through the signal bar only — `screen_symbol` truncates to df.index[-1]
- entry on the NEXT bar's open, never the signal close
- management of any bar uses only that bar's own OHLC (conservative: low before high)
- costs: commission + slippage, applied against the trader on both buy and sell

Trade lifecycle (the single Track-A default):
    entry      next bar open (+ slippage), shares sized so (entry-stop)*shares = risk_dollars
    stop       RiskPlan stop (max of pivot, entry-1.5*ATR), a hard level
    scale-out  sell `scale_out_fraction` at first_target, raise stop to breakeven
    trail      after scale-out, stop = max(stop, highest_close - trail_atr_mult*ATR)
    time stop  if first target not reached within time_stop_days bars, exit at close
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from ..indicators import atr
from ..screen.funnel import screen_symbol
from .metrics import Trade, buy_hold_return, equity_stats, summarize


@dataclass
class CostModel:
    commission_per_share: float = 0.0
    slippage_bps: float = 15.0  # fills slip against the trader

    def apply_buy(self, price: float) -> float:
        return price * (1 + self.slippage_bps / 1e4) + self.commission_per_share

    def apply_sell(self, price: float) -> float:
        return price * (1 - self.slippage_bps / 1e4) - self.commission_per_share


@dataclass
class BacktestConfig:
    account_equity: float = 100_000.0
    cost: CostModel = field(default_factory=CostModel)
    min_composite: float = 0.0           # only act on signals at/above this rank
    scale_out_fraction: float = 0.5      # fraction sold at the first target

    @classmethod
    def from_settings(cls, settings, account_equity: float | None = None) -> "BacktestConfig":
        bt = getattr(settings, "backtest", {}) or {}
        return cls(
            account_equity=account_equity if account_equity is not None
            else bt.get("account_equity", 100_000.0),
            cost=CostModel(
                commission_per_share=bt.get("commission_per_share", 0.0),
                slippage_bps=bt.get("slippage_bps", 15.0),
            ),
            min_composite=bt.get("min_composite", 0.0),
            scale_out_fraction=bt.get("scale_out_fraction", 0.5),
        )


@dataclass
class Position:
    """An open position being managed bar-by-bar."""

    symbol: str
    entry: float
    entry_date: pd.Timestamp
    stop: float
    pivot: float
    shares: int
    first_target: float
    initial_stop: float
    highest_close: float
    bars_held: int = 0
    scaled: bool = False
    # accumulated exits, for the share-weighted average exit price
    exit_value: float = 0.0   # sum(price * shares) across legs
    exit_shares: int = 0


@dataclass
class BacktestResult:
    symbol: str
    trades: list[Trade]
    equity_curve: pd.Series
    metrics: dict
    equity: dict
    buy_hold_pct: float
    window: tuple
    n_signals: int


def _resolve_window(df: pd.DataFrame, start, end, min_history: int):
    """Pick the [start, end] test window, defaulting to all bars after the warmup."""
    end = pd.Timestamp(end) if end is not None else df.index[-1]
    if start is not None:
        start = pd.Timestamp(start)
    else:
        # first bar that has enough history behind it to screen
        if len(df) > min_history:
            start = df.index[min_history]
        else:
            start = df.index[0]
    return start, end


def backtest_symbol(
    symbol: str,
    df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    settings,
    config: BacktestConfig | None = None,
    start=None,
    end=None,
) -> BacktestResult:
    """Simulate Track A on one symbol over [start, end]. Bars before `start` are warmup."""
    config = config or BacktestConfig.from_settings(settings)
    risk_cfg = settings.risk
    trail_mult = risk_cfg["atr_stop_mult"]
    time_stop_days = risk_cfg["time_stop_days"]
    min_history = settings.universe["min_history_days"]

    start, end = _resolve_window(df, start, end, min_history)
    test_dates = df.loc[start:end].index

    # ATR at bar b uses only data <= b, so precomputing on the full frame is leak-free.
    atr_series = atr(df, 20)

    trades: list[Trade] = []
    equity_points: list[tuple] = []
    n_signals = 0

    cash = config.account_equity
    pos: Position | None = None
    pending: Position | None = None  # entry planned on a signal, activates next bar

    for ts in test_dates:
        bar = df.loc[ts]
        o, hi, lo, c = (float(bar["open"]), float(bar["high"]),
                        float(bar["low"]), float(bar["close"]))

        # ---- 0) activate a pending entry: this IS the next bar after the signal ----
        if pending is not None and ts == pending.entry_date:
            pos = pending
            pending = None
            cash -= pos.entry * pos.shares  # entry price already includes slippage

        # ---- 1) manage an open position using THIS bar's OHLC ----
        if pos is not None:
            pos.bars_held += 1
            exited = False

            # (a) stop / trailing stop — low-before-high conservative assumption
            if lo <= pos.stop:
                fill = min(o, pos.stop)                      # gap-through fills at the open
                fill = config.cost.apply_sell(fill)
                cash += fill * pos.shares
                pos.exit_value += fill * pos.shares
                pos.exit_shares += pos.shares
                reason = "trail" if pos.scaled else "stop"
                trades.append(_close(pos, ts, reason))
                pos = None
                exited = True

            # (b) first target → scale out + move stop to breakeven
            if not exited and not pos.scaled and hi >= pos.first_target:
                sell = int(pos.shares * config.scale_out_fraction)
                if sell > 0:
                    fill = config.cost.apply_sell(pos.first_target)
                    cash += fill * sell
                    pos.exit_value += fill * sell
                    pos.exit_shares += sell
                    pos.shares -= sell
                pos.scaled = True
                pos.stop = max(pos.stop, pos.entry)          # breakeven

            # (c) trail the remainder (only after scale-out)
            if not exited and pos is not None and pos.scaled:
                pos.highest_close = max(pos.highest_close, c)
                atr_now = float(atr_series.loc[ts])
                pos.stop = max(pos.stop, pos.highest_close - trail_mult * atr_now)

            # (d) time decay — no first-target progress within the window
            if (not exited and pos is not None and not pos.scaled
                    and pos.bars_held >= time_stop_days):
                fill = config.cost.apply_sell(c)
                cash += fill * pos.shares
                pos.exit_value += fill * pos.shares
                pos.exit_shares += pos.shares
                trades.append(_close(pos, ts, "time_stop"))
                pos = None

        # ---- 2) when flat (and nothing pending), screen THIS bar's close for a signal ----
        if pos is None and pending is None:
            bench = benchmark_df.loc[:ts]
            sym_df = df.loc[:ts]
            if (len(bench) >= settings.regime["ma_period"]
                    and len(sym_df) >= min_history):
                cand = screen_symbol(symbol, sym_df, settings, benchmark_df=bench,
                                     account_equity=config.account_equity)
                if cand.passed_gates and (cand.composite or 0) >= config.min_composite:
                    n_signals += 1
                    pending = _plan_entry(symbol, df, ts, cand,
                                          config, risk_cfg["first_target_r"])

        # ---- 3) mark to market (open position valued at this close) ----
        held_value = pos.shares * c if pos is not None else 0.0
        equity_points.append((ts, cash + held_value))

    # close any still-open position at the last bar's close (marked, reason "open")
    if pos is not None:
        last_ts = test_dates[-1]
        last_c = float(df.loc[last_ts]["close"])
        fill = config.cost.apply_sell(last_c)
        cash += fill * pos.shares
        pos.exit_value += fill * pos.shares
        pos.exit_shares += pos.shares
        trades.append(_close(pos, last_ts, "open"))
        # rewrite the final equity point now that the position is booked to cash
        equity_points[-1] = (last_ts, cash)

    equity_curve = pd.Series(
        dict(equity_points)) if equity_points else pd.Series(dtype=float)
    equity_curve.index.name = "date"

    return BacktestResult(
        symbol=symbol,
        trades=trades,
        equity_curve=equity_curve,
        metrics=summarize(trades),
        equity=equity_stats(equity_curve),
        buy_hold_pct=buy_hold_return(df, start, end),
        window=(start, end),
        n_signals=n_signals,
    )


def _plan_entry(symbol, df, signal_ts, cand, config, first_target_r) -> Position | None:
    """Plan an entry at the bar AFTER `signal_ts` open (+ slippage).

    Returns an un-activated Position (cash is debited when the loop reaches entry_date).
    None if there is no next bar, the open gapped through the stop, or size rounds to 0.
    """
    loc = df.index.get_loc(signal_ts)
    if loc + 1 >= len(df):
        return None  # signal on the last bar — nothing to fill against
    entry_ts = df.index[loc + 1]
    entry = config.cost.apply_buy(float(df.iloc[loc + 1]["open"]))

    stop = cand.risk.stop
    if stop >= entry:           # gapped to/through the stop — skip
        return None
    stop_distance = entry - stop
    shares = int(cand.risk.risk_dollars // stop_distance)
    if shares <= 0:
        return None
    # Targets are re-anchored to the actual fill so R is measured from the real entry.
    first_target = entry + first_target_r * stop_distance

    return Position(
        symbol=symbol,
        entry=round(entry, 4),
        entry_date=entry_ts,
        stop=round(stop, 4),
        pivot=cand.risk.stop,
        shares=shares,
        first_target=round(first_target, 4),
        initial_stop=round(stop, 4),
        highest_close=entry,
    )


def _close(pos: Position, exit_date, reason: str) -> Trade:
    avg_exit = pos.exit_value / pos.exit_shares if pos.exit_shares else pos.entry
    return Trade(
        symbol=pos.symbol,
        entry=pos.entry,
        stop=pos.initial_stop,
        exit=round(avg_exit, 4),
        shares=pos.exit_shares,
        bars_held=pos.bars_held,
        entry_date=pos.entry_date,
        exit_date=exit_date,
        exit_reason=reason,
    )


def run_backtest(
    symbols: list[str],
    load_bars: Callable[[str], pd.DataFrame],
    benchmark_df: pd.DataFrame,
    settings,
    dates: pd.DatetimeIndex | None = None,
    config: BacktestConfig | None = None,
    start=None,
    end=None,
) -> dict:
    """Multi-symbol wrapper: each symbol simulated independently (no shared portfolio heat yet).

    `dates` is accepted for backward-compat; when given, its first/last bound the window.
    """
    config = config or BacktestConfig.from_settings(settings)
    if dates is not None and len(dates):
        start = start or dates[0]
        end = end or dates[-1]

    results = {}
    for sym in symbols:
        df = load_bars(sym)
        results[sym] = backtest_symbol(sym, df, benchmark_df, settings, config,
                                       start=start, end=end)
    return results
