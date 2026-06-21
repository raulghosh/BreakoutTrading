"""Funnel orchestration: run one symbol through L0–L7 on the LAST bar of `df`.

For a point-in-time backtest, pass `df` truncated to the signal bar — every indicator uses only
data through `df.index[-1]`, so there is no look-ahead.
"""
from __future__ import annotations

import pandas as pd

from ..indicators import validate_ohlcv
from . import l0_universe, l1_regime, l2_trend, l3_setup, l4_trigger, l5_group, l6_catalyst, l7_compose
from .l5_group import GroupContext
from .l6_catalyst import CatalystContext
from .types import Candidate


def screen_symbol(
    symbol: str,
    df: pd.DataFrame,
    settings,
    *,
    benchmark_df: pd.DataFrame,
    account_equity: float = 100_000.0,
    is_leveraged_etf: bool = False,
    rs_rank_pct: float | None = None,
    group_ctx: GroupContext | None = None,
    catalyst_ctx: CatalystContext | None = None,
) -> Candidate:
    """Evaluate `symbol` at df.index[-1]. Gates short-circuit; scores always computed if reached.

    Returns a Candidate. `cand.passed_gates` is True only if L0/L1/L2/L4 all passed; in that case
    `cand.composite` and `cand.risk` are populated.
    """
    validate_ohlcv(df)
    cand = Candidate(symbol=symbol, date=df.index[-1])

    # --- gates (short-circuit on first failure, but record the result) ---
    r0 = l0_universe.evaluate(df, settings.universe, is_leveraged_etf=is_leveraged_etf)
    cand.layers.append(r0)
    if not r0.passed:
        cand.passed_gates = False
        return cand

    r1 = l1_regime.evaluate(benchmark_df, settings.regime)
    cand.layers.append(r1)
    if not r1.passed:
        cand.passed_gates = False
        return cand

    r2 = l2_trend.evaluate(df, settings.trend)
    cand.layers.append(r2)
    if not r2.passed:
        cand.passed_gates = False
        return cand

    r4 = l4_trigger.evaluate(df, settings.trigger)
    cand.layers.append(r4)
    if not r4.passed:
        cand.passed_gates = False
        return cand

    # --- scores (only for survivors) ---
    cand.layers.append(
        l3_setup.evaluate(df, settings.setup, benchmark_df=benchmark_df, rs_rank_pct=rs_rank_pct)
    )
    cand.layers.append(l5_group.evaluate(group_ctx, settings.group))
    cand.layers.append(l6_catalyst.evaluate(catalyst_ctx, settings.composite))

    return l7_compose.finalize(cand, df, settings, account_equity)
