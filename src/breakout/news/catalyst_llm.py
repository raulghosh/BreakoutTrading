"""LLM catalyst-scoring pipeline.

For each ticker clearing the technical screen, pull recent news (Alpaca Benzinga feed)
and have the model emit a CatalystContext. DURABILITY (one-off vs multi-quarter structural shift)
dominates the score — it separates 'ChatGPT -> NVDA' from a transient headline.

Guardrails enforced here:
- only items timestamped <= as_of (no look-ahead)
- near-identical wire deduplication (Jaccard > 0.55 on headline words)
- fails open: any API/import error returns no-catalyst so the screen still runs
- never auto-trade on a headline alone
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from ..config import Secrets
from ..data.base import NewsItem
from ..screen.l6_catalyst import CatalystContext
from .attention import news_volume_zscore

_CATALYST_TYPES = (
    "product_launch", "supply_shortage", "demand_surge", "guidance_raise",
    "regulatory_approval", "major_contract", "tech_breakthrough", "macro_shift", "none",
)

_TOOL = {
    "name": "emit_catalyst",
    "description": (
        "Assess the catalyst quality from recent news for a stock that just broke out technically. "
        "DURABILITY is the most important field: does this news signal a multi-quarter structural "
        "shift (1.0) or a transient one-day headline (0.0)?"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "catalyst_present": {
                "type": "boolean",
                "description": "True if any meaningful fundamental catalyst exists in the headlines.",
            },
            "catalyst_type": {
                "type": "string",
                "enum": list(_CATALYST_TYPES),
                "description": "Best-fit category. 'none' if catalyst_present is false.",
            },
            "durability": {
                "type": "number",
                "description": "0 = one-off pop (earnings beat), 1 = multi-quarter structural shift (new product cycle).",
            },
            "novelty": {
                "type": "number",
                "description": "0 = already priced in / widely known, 1 = fresh surprise not yet in consensus.",
            },
            "confidence": {
                "type": "number",
                "description": "Model confidence 0-1. Low when headlines are ambiguous or sparse.",
            },
            "rationale": {
                "type": "string",
                "description": "One sentence explaining the assessment. Kept for audit trail.",
            },
        },
        "required": ["catalyst_present", "catalyst_type", "durability", "novelty", "confidence", "rationale"],
    },
}


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    """Drop near-identical wire re-runs (Jaccard > 0.55 on headline words)."""
    seen: list[set] = []
    out: list[NewsItem] = []
    for item in items:
        words = set(item.headline.lower().split())
        if not any(
            len(words & s) / len(words | s) > 0.55
            for s in seen
            if words | s
        ):
            seen.append(words)
            out.append(item)
    return out


def _attention_z(items: list[NewsItem]) -> float:
    if not items:
        return 0.0
    counts = pd.Series(1, index=[n.timestamp.date() for n in items])
    daily = counts.groupby(counts.index).sum()
    daily.index = pd.to_datetime(daily.index)
    return float(max(0.0, news_volume_zscore(daily)))


def score_catalyst(
    symbol: str,
    news_items: list[NewsItem],
    as_of: datetime,
    secrets: Secrets | None = None,
    lookback_days: int = 7,
) -> CatalystContext:
    """Return a CatalystContext for `symbol` using only news with timestamp <= as_of.

    Fails open: returns no-catalyst on any error so the funnel always completes.
    """
    # --- point-in-time filter ---
    visible = [n for n in news_items if n.timestamp <= as_of]
    attention_z = _attention_z(visible)

    cutoff = as_of - timedelta(days=lookback_days)
    recent = [n for n in visible if n.timestamp >= cutoff]
    if not recent:
        return CatalystContext(catalyst_present=False, attention_z=attention_z)

    recent = _dedupe(recent)[-12:]  # cap context; most-recent headlines last

    try:
        import anthropic
    except ImportError:
        return CatalystContext(catalyst_present=False, attention_z=attention_z)

    secrets = secrets or Secrets.from_env()
    if not secrets.anthropic_key:
        return CatalystContext(catalyst_present=False, attention_z=attention_z)

    headlines = "\n".join(
        f"[{n.timestamp.strftime('%Y-%m-%d')}] {n.headline}" for n in recent
    )
    prompt = (
        f"Stock: {symbol}\n\n"
        f"Recent news (oldest first):\n{headlines}\n\n"
        "Assess the fundamental catalyst quality for a trader who just saw a technical breakout."
    )

    try:
        client = anthropic.Anthropic(api_key=secrets.anthropic_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "emit_catalyst"},
            messages=[{"role": "user", "content": prompt}],
        )
        result = next(b.input for b in resp.content if b.type == "tool_use")
    except Exception:
        return CatalystContext(catalyst_present=False, attention_z=attention_z)

    return CatalystContext(
        catalyst_present=bool(result.get("catalyst_present", False)),
        catalyst_type=result.get("catalyst_type"),
        durability=float(result.get("durability", 0.0)),
        novelty=float(result.get("novelty", 0.0)),
        confidence=float(result.get("confidence", 0.0)),
        attention_z=attention_z,
        rationale=result.get("rationale"),
    )


if __name__ == "__main__":
    from datetime import timezone
    items = [
        NewsItem("DEMO", datetime(2024, 6, 1, 9, 0, tzinfo=timezone.utc),
                 "DEMO wins $500M multi-year government contract for cloud services",
                 "", "benzinga"),
        NewsItem("DEMO", datetime(2024, 6, 2, 8, 0, tzinfo=timezone.utc),
                 "DEMO shares rise after major contract announcement",
                 "", "benzinga"),
        NewsItem("DEMO", datetime(2024, 6, 3, 7, 0, tzinfo=timezone.utc),
                 "Analysts raise price targets on DEMO following contract win",
                 "", "benzinga"),
    ]
    ctx = score_catalyst("DEMO", items, as_of=datetime(2024, 6, 3, 23, 59, tzinfo=timezone.utc))
    print(f"catalyst_present : {ctx.catalyst_present}")
    print(f"catalyst_type    : {ctx.catalyst_type}")
    print(f"durability       : {ctx.durability:.2f}")
    print(f"novelty          : {ctx.novelty:.2f}")
    print(f"confidence       : {ctx.confidence:.2f}")
    print(f"attention_z      : {ctx.attention_z:.2f}")
    print(f"rationale        : {ctx.rationale}")
