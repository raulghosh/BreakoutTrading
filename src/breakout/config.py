"""Configuration loading: settings.yaml (thresholds) + .env (secrets)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Repo root = three levels up from this file (src/breakout/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS = REPO_ROOT / "config" / "settings.yaml"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency on python-dotenv)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def load_settings(path: str | Path | None = None) -> dict[str, Any]:
    """Load the threshold/parameter dictionary from YAML."""
    p = Path(path) if path else DEFAULT_SETTINGS
    with open(p) as fh:
        return yaml.safe_load(fh)


@dataclass
class Secrets:
    """API credentials, read from the environment (load .env first)."""

    alpaca_key: str | None = None
    alpaca_secret: str | None = None
    alpaca_feed: str = "iex"
    alpaca_paper: bool = True     # True = paper endpoint, False = live trading endpoint
    schwab_app_key: str | None = None
    schwab_app_secret: str | None = None
    anthropic_key: str | None = None

    @classmethod
    def from_env(cls, dotenv: str | Path | None = None) -> "Secrets":
        _load_dotenv(Path(dotenv) if dotenv else REPO_ROOT / ".env")
        return cls(
            alpaca_key=os.getenv("ALPACA_API_KEY"),
            alpaca_secret=os.getenv("ALPACA_SECRET_KEY"),
            alpaca_feed=os.getenv("ALPACA_DATA_FEED", "iex"),
            alpaca_paper=os.getenv("ALPACA_PAPER", "true").lower() == "true",
            schwab_app_key=os.getenv("SCHWAB_APP_KEY"),
            schwab_app_secret=os.getenv("SCHWAB_APP_SECRET"),
            anthropic_key=os.getenv("ANTHROPIC_API_KEY"),
        )


@dataclass
class Settings:
    """Parsed settings with convenient attribute access per layer."""

    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Settings":
        return cls(raw=load_settings(path))

    def __getattr__(self, name: str) -> Any:  # settings.trigger, settings.risk, ...
        try:
            return self.__dict__["raw"][name]
        except KeyError as exc:
            raise AttributeError(name) from exc
