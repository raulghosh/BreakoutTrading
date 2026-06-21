"""L5 — Group / theme confirmation (score). Fixes original Rule 4.

Rewards 'strong group + this name leading + broke early'; penalizes buying the last laggard.
Cluster construction lives in news/theme_graph.py (Phase 4/5); this layer consumes a prepared
GroupContext so the scoring math is testable without that machinery.
"""
from __future__ import annotations

from dataclasses import dataclass

from .types import LayerResult


@dataclass
class GroupContext:
    """Pre-computed cluster facts for a symbol on a date."""

    group_rs_rising: bool = False        # cluster aggregate outperforming the market
    leader_rank_pct: float = 0.0         # this name's RS percentile WITHIN the cluster (1 = top)
    peers_already_extended_pct: float = 0.0  # fraction of peers already broken out (we want LOW)
    group_name: str | None = None

    @property
    def broke_early(self) -> float:
        return max(0.0, 1.0 - self.peers_already_extended_pct)


def evaluate(ctx: GroupContext | None, cfg: dict) -> LayerResult:
    if ctx is None:  # no group data available yet → neutral, doesn't help or hurt
        return LayerResult(name="L5_group", kind="score", score=0.0,
                           detail={"available": False})

    score = (
        0.35 * (1.0 if ctx.group_rs_rising else 0.0)
        + 0.40 * float(ctx.leader_rank_pct)
        + 0.25 * ctx.broke_early
    )
    return LayerResult(
        name="L5_group",
        kind="score",
        score=round(float(max(0.0, min(1.0, score))), 4),
        detail={"available": True, "group": ctx.group_name,
                "group_rs_rising": ctx.group_rs_rising,
                "leader_rank_pct": ctx.leader_rank_pct,
                "broke_early": round(ctx.broke_early, 4)},
    )
