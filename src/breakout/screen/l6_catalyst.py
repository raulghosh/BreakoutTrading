"""L6 — Catalyst / news overlay (score). A WEIGHT, not a gate (design doc, Section 5.4).

Consumes a CatalystContext produced by news/catalyst_llm.py + news/attention.py. Durability of
the catalyst (structural vs one-off) dominates the score — that is what separates
'ChatGPT -> NVDA' from a transient headline.
"""
from __future__ import annotations

from dataclasses import dataclass

from .types import LayerResult


@dataclass
class CatalystContext:
    catalyst_present: bool = False
    durability: float = 0.0       # 0 = one-off pop, 1 = multi-quarter structural shift
    novelty: float = 0.0          # 0 = already priced in, 1 = fresh surprise
    confidence: float = 0.0       # model confidence in its assessment
    attention_z: float = 0.0      # news-volume / options-activity z-score (clipped to ~[0,3])
    catalyst_type: str | None = None
    rationale: str | None = None


def evaluate(ctx: CatalystContext | None, cfg: dict) -> LayerResult:
    if ctx is None or not ctx.catalyst_present:
        return LayerResult(name="L6_catalyst", kind="score", score=0.0,
                           detail={"catalyst_present": False})

    attention = min(max(ctx.attention_z, 0.0), 3.0) / 3.0
    raw = 0.50 * ctx.durability + 0.20 * ctx.novelty + 0.30 * attention
    score = raw * max(0.0, min(1.0, ctx.confidence)) if ctx.confidence else raw

    return LayerResult(
        name="L6_catalyst",
        kind="score",
        score=round(float(max(0.0, min(1.0, score))), 4),
        detail={"catalyst_present": True, "catalyst_type": ctx.catalyst_type,
                "durability": ctx.durability, "novelty": ctx.novelty,
                "attention_norm": round(attention, 4), "confidence": ctx.confidence,
                "rationale": ctx.rationale},
    )
