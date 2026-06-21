"""Dataclasses passed through the funnel."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LayerResult:
    """Result of one funnel layer for one symbol on one date.

    A *gate* layer sets `passed`; a *score* layer sets `score` in [0, 1]. `detail` carries the
    raw numbers behind the verdict (for auditability and ablations).
    """

    name: str
    kind: str  # "gate" | "score"
    passed: bool = True  # gates only; scores leave this True
    score: float | None = None  # scores only, 0-1
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskPlan:
    """Risk template attached to every surviving signal (L7). Makes expectancy measurable."""

    entry: float
    stop: float
    stop_distance: float
    shares: int
    risk_dollars: float
    first_target: float  # price at +first_target_r
    time_stop_days: int

    @property
    def r_multiple_to_target(self) -> float:
        return (self.first_target - self.entry) / self.stop_distance if self.stop_distance else 0.0


@dataclass
class Candidate:
    """A symbol evaluated by the funnel on a given date."""

    symbol: str
    date: Any  # pd.Timestamp
    layers: list[LayerResult] = field(default_factory=list)
    passed_gates: bool = True
    composite: float | None = None
    risk: RiskPlan | None = None
    is_ath_breakout: bool = False

    def layer(self, name: str) -> LayerResult | None:
        return next((lr for lr in self.layers if lr.name == name), None)

    @property
    def rejected_at(self) -> str | None:
        """Name of the first gate that failed, or None if all gates passed."""
        for lr in self.layers:
            if lr.kind == "gate" and not lr.passed:
                return lr.name
        return None

    def score_of(self, name: str, default: float = 0.0) -> float:
        lr = self.layer(name)
        return default if lr is None or lr.score is None else lr.score
