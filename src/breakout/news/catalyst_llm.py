"""LLM catalyst-scoring pipeline (Section 5.2). Phase 5 stub.

For each ticker clearing the technical screen, pull recent news (Alpaca + 8-Ks/PRs/transcripts)
and have the model emit a CatalystContext. DURABILITY (one-off vs multi-quarter structural shift)
dominates the score — it separates 'ChatGPT -> NVDA' from a transient headline.

Guardrails (must be enforced when implemented):
- dedupe near-identical wire stories
- only use items time-stamped <= signal time (no look-ahead)
- keep raw text + model output for audit
- never auto-trade on a headline alone
"""
from __future__ import annotations

from datetime import datetime

from ..config import Secrets
from ..data.base import NewsItem
from ..screen.l6_catalyst import CatalystContext

# Structured output schema the model must return (wire into anthropic tool-use in Phase 5).
CATALYST_SCHEMA = {
    "catalyst_present": "bool",
    "catalyst_type": "product_launch|supply_shortage|demand_surge|guidance_raise|"
                     "regulatory_approval|major_contract|tech_breakthrough|macro_shift|none",
    "durability": "float 0-1 (one-off pop -> multi-quarter structural shift)",
    "novelty": "float 0-1 (already priced in -> fresh surprise)",
    "theme_tags": "list[str] (clusters to propagate to)",
    "confidence": "float 0-1",
    "rationale": "str (short, for auditability)",
}


def score_catalyst(
    symbol: str,
    news_items: list[NewsItem],
    as_of: datetime,
    secrets: Secrets | None = None,
) -> CatalystContext:
    """Return a CatalystContext for `symbol` using only news with timestamp <= as_of.

    Phase 5: filter+dedupe items, build the prompt, call Claude with CATALYST_SCHEMA tool-use,
    map the response onto CatalystContext, and merge attention signals. Until then, returns an
    empty (no-catalyst) context so the funnel runs end-to-end.
    """
    visible = [n for n in news_items if n.timestamp <= as_of]  # leak-free filter
    if not visible:
        return CatalystContext(catalyst_present=False)

    # TODO(Phase 5): anthropic tool-use call here (model=claude-opus-4-8 or sonnet for cost).
    raise NotImplementedError(
        "LLM catalyst scoring not yet implemented (Phase 5). Install '.[news]', set "
        "ANTHROPIC_API_KEY, then wire CATALYST_SCHEMA into a tool-use call."
    )
