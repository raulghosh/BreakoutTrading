"""L7 — Composite rank + risk template (output).

composite = weighted sum of the SCORE layers (regime, setup, group, catalyst); the GATE layers
(L0/L2/L4) already filtered survivors. Every survivor gets a RiskPlan so expectancy is measurable.
"""
from __future__ import annotations

import math

import pandas as pd

from ..indicators import atr
from .types import Candidate, LayerResult, RiskPlan


def composite_score(cand: Candidate, weights: dict) -> float:
    """Weighted blend of scored layers. Weights are renormalized over available scores."""
    mapping = {
        "regime": "L1_regime",
        "setup": "L3_setup",
        "group": "L5_group",
        "catalyst": "L6_catalyst",
    }
    total_w = 0.0
    acc = 0.0
    for key, layer_name in mapping.items():
        w = weights.get(key, 0.0)
        if w <= 0:
            continue
        acc += w * cand.score_of(layer_name, 0.0)
        total_w += w
    return round(acc / total_w, 4) if total_w else 0.0


def build_risk_plan(df: pd.DataFrame, cfg: dict, account_equity: float,
                    pivot: float | None = None) -> RiskPlan:
    """Stop below pivot or entry - atr_stop_mult*ATR (whichever is tighter); fixed-fractional size."""
    entry = float(df["close"].iloc[-1])
    atr_now = float(atr(df, 20).iloc[-1])
    atr_stop = entry - cfg["atr_stop_mult"] * atr_now
    stop = max(atr_stop, pivot) if pivot is not None else atr_stop  # tighter of the two
    stop = min(stop, entry - 1e-6)  # stop must be below entry

    stop_distance = entry - stop
    risk_dollars = account_equity * cfg["account_risk_pct"]
    shares = int(math.floor(risk_dollars / stop_distance)) if stop_distance > 0 else 0
    first_target = entry + cfg["first_target_r"] * stop_distance

    return RiskPlan(
        entry=round(entry, 4),
        stop=round(stop, 4),
        stop_distance=round(stop_distance, 4),
        shares=shares,
        risk_dollars=round(risk_dollars, 2),
        first_target=round(first_target, 4),
        time_stop_days=cfg["time_stop_days"],
    )


def finalize(cand: Candidate, df: pd.DataFrame, settings, account_equity: float) -> Candidate:
    """Attach composite score + risk plan to a candidate that cleared all gates."""
    cand.composite = composite_score(cand, settings.composite["weights"])
    l4 = cand.layer("L4_trigger")
    pivot = l4.detail.get("pivot") if l4 else None
    cand.is_ath_breakout = bool(l4 and l4.detail.get("is_ath_breakout"))
    cand.risk = build_risk_plan(df, settings.risk, account_equity, pivot=pivot)
    cand.layers.append(LayerResult(name="L7_compose", kind="score", score=cand.composite,
                                   detail={"composite": cand.composite}))
    return cand
