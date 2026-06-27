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

## Backtesting

`scan` and `screen` tell you what looks good *today*. **Backtesting** answers the real question:
*if I had taken these signals over the past year, would I have made money?*

The engine replays history one day at a time — using only the data that existed on each day (no
look-ahead) — and simulates the full trade lifecycle:

- **Entry** on the next bar's open after a signal (with slippage)
- **Initial stop** at the technical level (below the pivot / 1.5×ATR)
- **Scale-out** — sell half at the first target (2.5R), move the stop to breakeven
- **Trailing stop** — trail the remaining half by an ATR chandelier stop
- **Time decay** — if the trade hasn't reached its target within 15 bars, cut it

### Run it on one stock, one year back

The backtest needs warmup history for the moving averages, so fetch ~2 years (1yr warmup +
1yr test):

```bash
breakout fetch SNDK --lookback 730
breakout backtest SNDK --verbose
```

Sample output (numbers are illustrative — run it for the real figures):

```
=== BACKTEST SNDK ===
  window     : 2024-06-26 → 2025-06-26  (250 bars)
  signals    : 3          # times a breakout fired
  trades     : 3          # positions actually taken

  win_rate     : 66.7%
  avg_win_r    : +3.10R    # winners average +3.1× the risk unit
  avg_loss_r   : -0.98R    # losers cut at ~ -1R, as designed
  expectancy_r : +1.74R / trade   # positive edge per trade
  profit_factor: 4.20
  total_r      : +5.22R
  avg_hold     : 18.3 bars

  return       : +3.91%   ($100,000 → $103,914)
  max_drawdown : -1.20%
  buy & hold   : +12.40%   <- strategy TRAILED buy-and-hold

  Trades:
    ENTRY        EXIT               IN      OUT    SH BARS      R  REASON
    ---------------------------------------------------------------------
    2024-08-12   2024-09-20      42.10    51.30   178   28  +3.10  trail
    2024-11-04   2024-11-06      48.50    47.55   195    2  -0.98  stop
    2025-02-18   2025-04-01      55.20    66.90   150   31  +3.10  trail
```

### Reading the result

- **`expectancy_r`** is the headline number — positive means the system made money per trade in
  risk-adjusted terms. This is the "did it succeed?" verdict.
- **`R` (R-multiple)** is profit measured in risk units: +3.10R means the trade made 3.1× what it
  risked. Losers should cluster near −1R.
- **`REASON`** shows how each trade closed: `trail` (trailing stop after a scale-out — a managed
  winner), `stop` (initial stop hit — a clean loss), `time_stop` (time decay), `open` (still
  open at the end of the window).
- **return % vs R** — return looks small next to total R because each trade only risks 0.75% of
  equity (`risk.account_risk_pct`). Raise that to take bigger swings.
- **buy & hold** is the honesty check. On a stock that ran straight up, buy-and-hold wins because
  the strategy sits in cash between signals. The strategy earns its keep on **choppy** names by
  sidestepping drawdowns — compare `max_drawdown` to what holding through the dips would cost.

### Useful flags

```bash
breakout backtest SNDK --start 2024-01-01 --end 2024-12-31   # explicit window
breakout backtest SNDK NVDA AAPL                              # several symbols at once
breakout backtest SNDK --min-composite 0.4                   # only take stronger signals
breakout backtest SNDK --equity 250000                       # different account size
```

---

## Interactive notebooks

For a visual, click-to-explore version of the backtest, use the notebooks in
[`notebooks/`](notebooks/):

```bash
pip install -e ".[notebooks]"
jupyter lab notebooks/
```

| Notebook | What it does |
|----------|-------------|
| [`01_backtest_explorer.ipynb`](notebooks/01_backtest_explorer.ipynb) | Enter a ticker and a window, run the full backtest, and see a price chart with entries/exits, a trade log, and an equity curve vs buy-and-hold. |
| [`02_point_in_time_check.ipynb`](notebooks/02_point_in_time_check.ipynb) | Enter a ticker and a **past date**. See exactly what the funnel said on that day (gate by gate, no look-ahead), then reveal what the stock actually did next — did it hit the target or the stop first? |

Each notebook has a **Parameters** cell at the top — edit `TICKER` / `START` / `END` (or `AS_OF`),
then *Run All*. Bars load from the local cache, fetching from Alpaca automatically if missing.

> **Tip:** prefer long-history tickers (AAPL, MSFT, NVDA) for clean results. Recent spin-offs
> (e.g. SNDK) have limited history and can show distorted buy-and-hold figures from their
> when-issued opening prints.

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
│           ├── engine.py           # point-in-time loop + position management
│           └── metrics.py          # R-multiple expectancy + equity/drawdown stats
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
- [x] **Phase 4 — Backtest engine.** Point-in-time loop, position management (scale-out + trail),
      time decay, equity curve + drawdown, buy-&-hold comparison. Composite calibration still TODO.
- [~] **Phase 5 — Group / RS layer (L5).** Scoring logic done; cluster construction is a stub.
- [ ] **Phase 6 — News & theme overlay (L6).** Stubs in place; needs Alpaca news + LLM wiring.
- [ ] **Phase 7 — Track B (pre-breakout anticipation).** Separate entry inside the base.
- [ ] **Phase 8 — Composite ranking + paper-trade reconciliation.**

`[x]` complete · `[~]` partial · `[ ]` not started
