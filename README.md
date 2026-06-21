# Early-Stage Breakout Detection

Identify stocks in the **early** stages of a large directional move by combining classical
breakout/momentum structure with relative-strength + group context and a news/theme catalyst
overlay. Implementation of the **v1.0** spec in
[`breakout_strategy_design.md`](docs/breakout_strategy_design.md).

> **Disclaimer:** This is a research/discovery tool, not investment advice. A ranking screen is
> not a trading system until it has defined entries, stops, sizing, exits, portfolio limits, and a
> leak-free backtest establishing positive expectancy. Every threshold in `config/settings.yaml`
> is a hypothesis to validate, not a fact (see the design doc's parameter register).

**Scope (v1.0):** long-only US common stock, cash account, no leverage, swing/position horizon
(weeks–months). See [§0 Scope](docs/breakout_strategy_design.md#0-scope--operating-constraints).

## Two signal tracks

The v1.0 design runs **two tracks** on one engine (they share gates but differ in trigger and
trade lifecycle), resolving the v0.5 contradiction between "must close above pivot" and "buy
2nd-order names *before* they break out":

- **Track A — Confirmed breakout:** the L0–L7 funnel below; entry on the breakout.
- **Track B — Pre-breakout anticipation:** enter *inside* a tight base on theme + RS leadership +
  accumulation; the breakout becomes a confirmation/pyramid-add, not the entry. Validated
  separately, only after Track A clears its success criteria.

## Design in one screen

The core ideas are **gates vs. scores**, **contraction → expansion**, and **portfolio risk as
part of the strategy**:

| Layer | Role  | What it does |
|-------|-------|--------------|
| L0 Universe/liquidity | gate  | price & dollar-volume floor, drop ETFs/young IPOs |
| L1 Market regime      | gate* | multi-factor: trend + breadth + distribution; scales exposure |
| L2 Trend template     | gate  | Minervini Stage-2: 50>150>200 MA stack, near 52wk high |
| L3 Setup quality      | score | **volatility contraction** (squeeze), defined base/pivot, RS rank — *the "early" fix* |
| L4 Breakout trigger   | gate  | **close** above pivot + ATR/%-buffer, volume surge, range expansion *(Track A)* |
| L5 Group/theme        | score | RS leader in a strengthening, point-in-time cluster, broke early |
| L6 Catalyst/news      | score | LLM-scored durable catalyst + attention signals |
| Scoring + calibration | step  | features on a common scale; composite must be **monotone** vs forward return |
| Portfolio + risk      | output| heat caps (theme/sector/total), ADV cap, correlation-aware selection, stop/size per signal |

Why this differs from the naive "four ANDs": ATR-doubling and 26wk-range rules made the original
signal **late**; here volatility *contraction* builds the setup and *expansion* is only the
one-bar trigger. See the [original-rule → fix table](docs/breakout_strategy_design.md#12-original-rule--fix-summary).

## Project layout

```
BreakoutStrategy/
├── README.md
├── pyproject.toml                  # packaging + deps + `breakout` console script
├── config/
│   └── settings.yaml               # all tunable thresholds (the parameter register)
├── docs/
│   └── breakout_strategy_design.md # v1.0 design document
├── src/
│   └── breakout/
│       ├── __init__.py
│       ├── cli.py                  # `breakout demo` / `breakout screen ...`
│       ├── config.py               # load settings.yaml + .env
│       ├── synthetic.py            # synthetic OHLCV for tests + demo (no API keys)
│       ├── indicators/
│       │   ├── __init__.py
│       │   └── core.py             # ONE shared indicator lib (ATR, MAs, 52wk/ATH, BB width, RS)
│       ├── screen/                 # L0–L7 screening funnel
│       │   ├── __init__.py
│       │   ├── types.py            # Candidate / LayerResult / RiskPlan dataclasses
│       │   ├── funnel.py           # orchestration: run a symbol through the funnel
│       │   ├── l0_universe.py      # liquidity gate
│       │   ├── l1_regime.py        # market-regime gate
│       │   ├── l2_trend.py         # Stage-2 trend gate
│       │   ├── l3_setup.py         # setup-quality score
│       │   ├── l4_trigger.py       # breakout trigger gate (Track A)
│       │   ├── l5_group.py         # group/theme score
│       │   ├── l6_catalyst.py      # catalyst/news score
│       │   └── l7_compose.py       # composite + risk template
│       ├── data/                   # provider interfaces + bar store (Phase 1)
│       │   ├── __init__.py
│       │   ├── base.py             # BarProvider / NewsProvider protocols
│       │   ├── alpaca.py           # Alpaca adapter (stub pending keys)
│       │   ├── schwab.py           # Schwab adapter (stub pending keys)
│       │   ├── store.py            # Parquet bar cache
│       │   └── adjust.py           # split/dividend back-adjustment
│       ├── news/                   # news & theme overlay (stubs)
│       │   ├── __init__.py
│       │   ├── theme_graph.py
│       │   ├── catalyst_llm.py
│       │   └── attention.py
│       └── backtest/               # backtest harness
│           ├── __init__.py
│           ├── engine.py           # point-in-time loop (scaffold)
│           └── metrics.py          # R-multiple expectancy metrics
└── tests/                          # synthetic-data tests (run with no API keys)
    ├── test_indicators.py
    ├── test_funnel.py
    └── test_backtest_metrics.py
```

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # add ",data,news" for live providers
pytest                            # runs on synthetic data, no keys needed
```

Run the funnel on a single symbol's bars (synthetic demo, no keys):

```bash
breakout demo
```

With live data, copy `.env.example` → `.env`, fill keys, then `pip install -e ".[data]"`.

## Build status (phased plan, design §11)

> **Note:** the code scaffold currently implements **Track A only** and predates the v1.0 doc.
> Syncing it to v1.0 (split funnel into shared gates + Track A/B triggers, add a `portfolio/`
> module with heat caps + ADV cap + correlation-aware selection, add scoring calibration, fix the
> bar-adjustment policy to split-only for breakout levels, add the parameter register to
> `settings.yaml`) is the next change.

- [x] **Phase 1 — Data layer.** Shared indicator library; bar-store + provider interfaces
      (Alpaca/Schwab). *Indicators done; providers typed stubs; adjustment policy needs the
      split-only-for-levels fix (design §4).*
- [x] **Phase 2 — Track-A funnel (L0–L4 + risk).** Gated screen with attached stop/size. ✅
- [ ] **Phase 3 — Portfolio layer.** Heat caps, ADV cap, correlation-aware selection, regime scaling. *Not started.*
- [~] **Phase 4 — Backtest + calibration of Track A.** Metrics done; point-in-time engine + composite calibration are stubs.
- [~] **Phase 5 — Group/RS layer (L5).** RS leadership scoring scaffolded; point-in-time cluster construction stub.
- [ ] **Phase 6 — News & theme overlay (L6).** Alpaca news → LLM catalyst → theme graph, with backtestability controls. *Stubs.*
- [ ] **Phase 7 — Track B (pre-breakout anticipation).** Separate entry/stop/confirm-add; validated vs Track-A-only.
- [ ] **Phase 8 — Composite ranking + monitoring + paper-trade reconciliation.**

`[x]` runnable, `[~]` partial/scaffolded, `[ ]` stub. Each layer must **earn its keep** via the
per-track ablations in design §10 before it's trusted.
