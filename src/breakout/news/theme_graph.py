"""Theme / supply-chain knowledge graph (Section 5.1).

Maps catalyst -> theme -> 1st/2nd-order beneficiaries (e.g. AI demand -> GPUs -> HBM/memory ->
networking/optics -> power & cooling). A single news event flags the WHOLE cluster, which powers
L5 and surfaces 2nd-order names BEFORE they break out.

This is a minimal in-memory implementation: versioned, human-reviewable nodes + weighted edges.
Seeding from GICS / ETF-overlap / supplier graphs and LLM refinement is Phase 5 work (TODO).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Edge:
    theme: str
    symbol: str
    order: int  # 1 = direct beneficiary, 2 = second-order, ...
    exposure: float  # 0-1 strength of exposure
    mechanism: str = ""  # e.g. "supplies HBM to GPU makers"


@dataclass
class ThemeGraph:
    version: str = "0.0.1"
    edges: list[Edge] = field(default_factory=list)

    def add(self, theme: str, symbol: str, order: int, exposure: float, mechanism: str = "") -> None:
        self.edges.append(Edge(theme, symbol.upper(), order, exposure, mechanism))

    def cluster(self, theme: str) -> list[Edge]:
        """All tickers exposed to a theme, strongest/closest first."""
        members = [e for e in self.edges if e.theme == theme]
        return sorted(members, key=lambda e: (e.order, -e.exposure))

    def themes_for(self, symbol: str) -> list[str]:
        return sorted({e.theme for e in self.edges if e.symbol == symbol.upper()})

    # TODO(Phase 5): seed_from_gics(), seed_from_etf_overlap(), refine_with_llm(theme).
