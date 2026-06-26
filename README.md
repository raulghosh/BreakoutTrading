# Breakout Strategy

A stock screening tool that identifies US equities in the **early stages of a large directional
move** — before the move is obvious. It combines classical breakout/momentum structure with
relative strength, group/theme context, and a news catalyst overlay.

> **Disclaimer:** Research and discovery tool only, not investment advice. Every threshold in
> `config/settings.yaml` is a hypothesis to validate. Do not size up before the backtest in
> Phase 4 establishes positive expectancy.

**Scope:** Long-only · US common stock · Cash account, no leverage · Swing/position horizon
(weeks to months). See [`docs/breakout_strategy_design.md`](docs/breakout_strategy_design.md)
for the full v1.0 specification.

---

## The core idea

Most breakout systems buy **too late** — they wait for ATR to double or price to extend far above
a 52-week high, by which time the easy money is gone. This tool flips that:

- **Screen for contraction** — stocks building tight bases with drying volume (volatility squeeze)
- **Trigger on expansion** — one bar of price + volume expansion breaking above the pivot
- **Rank by context** — group RS, catalyst durability, market regime

The result is a ranked list of setups with pre-computed entry, stop, and first target for each.

---

## How the funnel works

Every stock runs through eight layers. **Gates** are binary — fail one and the stock is dropped
immediately. **Scores** are continuous [0–1] — they rank the survivors.

| Layer | Type  | What it checks |
|-------|-------|----------------|
| **L0** Universe / liquidity | Gate  | Price ≥ $7 · Avg daily dollar volume ≥ $15M · Enough history · Not a leveraged ETF |
| **L1** Market regime        | Gate  | SPY above its rising 200-day MA — if the market is in a downtrend, all signals are suppressed |
| **L2** Stage-2 trend        | Gate  | Minervini trend template: 50d MA > 150d MA > 200d MA · Close within 25% of 52-week high · ≥30% above 52-week low |
| **L3** Setup quality        | Score | Volatility squeeze (Bollinger width at a 1yr low) · Base tightness · RS line near its high |
| **L4** Breakout trigger     | Gate  | Close above pivot + ATR buffer · Volume ≥ 1.5× 50-day average · Range expansion on the bar |
| **L5** Group / theme        | Score | Stock is an RS leader in a strengthening group · Broke out early (not the last laggard) |
| **L6** Catalyst / news      | Score | LLM-scored catalyst: durability, novelty, attention signal |
| **L7** Composite + risk     | Output| Weighted score · Entry, stop (ATR-based), shares, first target at 2.5R |

Layers L0–L4 are **gates** that must pass before any scoring happens. L5–L6 are enrichment
scores for ranking. The funnel short-circuits at the first gate failure, so cheap checks run
before expensive ones.

---

## Real examples

### AAPL — rejected at L2 (trend template)

```
=== AAPL @ 2026-06-26 ===
  [PASS] L0_universe   # price and dollar-volume above the liquidity floor
  [PASS] L1_regime     # SPY is above its rising 200d MA — market is in an uptrend
  [FAIL] L2_trend      # AAPL failed the Stage-2 template: MA stack broken, or price
                        # too far below the 52-week high, or too close to the 52-week low
  -> REJECTED at L2_trend
```

AAPL is liquid and the market backdrop is fine, but AAPL itself is not in a Stage-2 uptrend.
Either its MA stack is out of order (e.g. 50d MA < 150d MA), it has fallen more than 25% from
its 52-week high, or it is less than 30% above its 52-week low. No further analysis is done.

---

### SNDK — rejected at L4 (breakout trigger)

```
=== SNDK @ 2026-06-26 ===
  [PASS] L0_universe   # liquid enough to trade
  [PASS] L1_regime     # market uptrend confirmed
  [PASS] L2_trend      # Stage-2 uptrend: MA stack intact, near 52-week highs
  [FAIL] L4_trigger    # price did not close above the pivot + ATR buffer,
                        # or volume was not ≥ 1.5× the 50-day average,
                        # or the bar showed no range expansion
  -> REJECTED at L4_trigger
```

SNDK is in a healthy uptrend and building a base (it passed L2), but it has not broken out yet.
It is a **watch-list candidate** — if it triggers in a future session it will pass all gates.
Note: L3 (setup quality score) is skipped here because L4 is a gate; setup score is only
computed for stocks that actually trigger.

---

## Setup

### 1. Install

```bash
pip install -e ".[dev,data]"
```

If you only want to run the synthetic demo and tests (no API keys needed):

```bash
pip install -e ".[dev]"
```

### 2. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` and fill in your Alpaca credentials:

```
ALPACA_API_KEY=PKxxxxxxxxxxxxxxxxxxxxxxx
ALPACA_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ALPACA_DATA_FEED=iex      # free tier; use "sip" if you have a paid subscription
ALPACA_PAPER=true         # true for paper account, false for live
```

You need an [Alpaca](https://alpaca.markets) account. A free paper trading account gives you
both the Trading API and the IEX market data feed under the same key pair.

### 3. Verify

```bash
pytest                # 16 tests, all on synthetic data — no keys needed
breakout demo         # runs the full funnel on a synthetic breakout series
```

---

## Usage

### Download bars

```bash
# Always fetch the benchmark first
breakout fetch SPY

# Then fetch the stocks you want to screen
breakout fetch AAPL MSFT NVDA META AMZN GOOGL SNDK
```

Bars are saved as Parquet files in `data/cache/`. You only need to re-fetch to get new data.

### Screen specific stocks

```bash
breakout screen NVDA AAPL SNDK
```

Prints the layer-by-layer funnel result for each symbol and a ranked list of survivors.

### Scan everything in the cache

```bash
breakout scan --top 10
```

Runs the full funnel on every cached symbol and prints the top signals ranked by composite score:

```
Scanning 7 symbol(s) ...

1 signal(s) from 7 scanned:

  #    SYM      COMP     ENTRY      STOP    TARGET  R
  -------------------------------------------------------
  1    NVDA     0.612    120.50    116.20    130.80  2.5R
```

### Get the full tradeable universe

```bash
breakout universe --save data/universe.txt
breakout fetch $(cat data/universe.txt | head -200)   # fetch the first 200
breakout scan --top 20
```

---

## Tuning

All thresholds live in [`config/settings.yaml`](config/settings.yaml). Every number there is
a hypothesis — do not tune them without a clean out-of-sample test. Key knobs:

| Parameter | Default | What it controls |
|-----------|---------|-----------------|
| `universe.min_dollar_volume` | $15M | Liquidity floor — raise for larger accounts |
| `trigger.volume_mult` | 1.5× | Volume surge required on the breakout bar |
| `trigger.atr_buffer_mult` | 0.75 | How far above the pivot the close must be |
| `risk.account_risk_pct` | 0.75% | Fraction of equity risked per trade |
| `risk.first_target_r` | 2.5 | First profit target in R-multiples |

---

## Project layout

```
BreakoutStrategy/
├── README.md
├── pyproject.toml                  # packaging + deps + `breakout` console script
├── config/
│   └── settings.yaml               # all tunable thresholds
├── docs/
│   └── breakout_strategy_design.md # full v1.0 strategy specification
├── src/
│   └── breakout/
│       ├── cli.py                  # all CLI commands
│       ├── config.py               # settings.yaml + .env loader
│       ├── synthetic.py            # synthetic OHLCV for tests and demo
│       ├── indicators/
│       │   └── core.py             # shared indicator library (ATR, MAs, BB width, RS)
│       ├── screen/                 # L0–L7 screening funnel
│       │   ├── types.py            # Candidate / LayerResult / RiskPlan dataclasses
│       │   ├── funnel.py           # orchestration
│       │   ├── l0_universe.py      # liquidity gate
│       │   ├── l1_regime.py        # market-regime gate
│       │   ├── l2_trend.py         # Stage-2 trend gate
│       │   ├── l3_setup.py         # setup-quality score
│       │   ├── l4_trigger.py       # breakout trigger gate
│       │   ├── l5_group.py         # group/theme score
│       │   ├── l6_catalyst.py      # catalyst/news score
│       │   └── l7_compose.py       # composite + risk plan
│       ├── data/
│       │   ├── alpaca.py           # Alpaca bar + news adapter
│       │   ├── schwab.py           # Schwab adapter (stub)
│       │   ├── store.py            # local Parquet bar cache
│       │   └── adjust.py           # split/dividend adjustment
│       ├── news/
│       │   ├── theme_graph.py      # supply-chain / theme graph (Phase 6)
│       │   ├── catalyst_llm.py     # LLM catalyst scorer (Phase 6)
│       │   └── attention.py        # news volume z-score
│       └── backtest/
│           ├── engine.py           # point-in-time backtest loop (Phase 4)
│           └── metrics.py          # R-multiple expectancy metrics
└── tests/
    ├── test_indicators.py
    ├── test_funnel.py
    └── test_backtest_metrics.py
```

---

## Build status

- [x] **Phase 1 — Data layer.** Alpaca adapter, local Parquet cache, shared indicator library.
- [x] **Phase 2 — Track-A funnel (L0–L4 + risk).** Full gated screen with stop/size output.
- [ ] **Phase 3 — Portfolio layer.** Heat caps, ADV-participation cap, correlation-aware selection.
- [~] **Phase 4 — Backtest + calibration.** Metrics done; point-in-time engine is a stub.
- [~] **Phase 5 — Group / RS layer (L5).** Scoring logic done; cluster construction is a stub.
- [ ] **Phase 6 — News & theme overlay (L6).** Stubs in place; needs Alpaca news + LLM wiring.
- [ ] **Phase 7 — Track B (pre-breakout anticipation).** Separate entry inside the base.
- [ ] **Phase 8 — Composite ranking + paper-trade reconciliation.**

`[x]` complete · `[~]` partial · `[ ]` not started
