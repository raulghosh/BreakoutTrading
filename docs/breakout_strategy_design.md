# Early-Stage Breakout Detection — Strategy Design Document (v1.0)

> **Version history.** v0.5 (Google Drive original) was a strong *philosophy memo*. This **v1.0**
> turns it into a buildable + validatable specification: it adds a scope section, splits the
> strategy into two explicit signal tracks, adds scoring calibration and a portfolio/risk layer,
> pins the trade lifecycle to a single unambiguous default per track, closes point-in-time
> leakage holes, hardens validation against overfitting, and adds a parameter register. The v0.5
> critique of the original four-rule idea (Section 1) and the original→fix table (Section 12) are
> kept largely intact because they were already good.

**Goal:** Identify stocks in the *early* stages of a large directional move, by combining classical
breakout/momentum structure with a relative-strength + group context and an unstructured
"catalyst" overlay (news, theme/supply-chain propagation).

**Data stack:** Schwab Trader API (thinkorswim) + Alpaca.

**Disclaimer:** This is a strategy-design document, not investment advice. A discovery/ranking
screen is not a trading system until it has defined entries, stops, sizing, exits, portfolio
limits, and a leak-free backtest establishing positive expectancy. Every threshold here is a
hypothesis to be validated, not a fact, and lives in the parameter register (Section 13).

---

## 0. Scope & operating constraints

The strategy is deliberately narrow so it can be specified and validated end-to-end.

- **Instruments:** US-listed **common stock** only. No options, futures, FX, or crypto. Exclude
  ETFs/ETNs (especially leveraged/inverse), ADRs with thin US liquidity, and non-common share
  classes unless explicitly added.
- **Direction:** **Long-only.** No shorting. Defense in adverse regimes comes from the regime gate
  scaling exposure toward cash, not from short or hedge positions.
- **Account:** **Cash account, no leverage, no margin.** Max gross exposure ≤ 100% of equity.
- **Horizon:** **Swing-to-position**, holding **weeks to a few months**. Not intraday, not HFT.
  Daily bars are the primary timeframe; weekly bars confirm; intraday is used only to confirm the
  trigger bar.
- **Capacity:** assume a modest account where realistic fills are possible if every position is
  capped at a small fraction of the symbol's average daily dollar volume (ADV) — see Section 7.
  Capacity degrades as AUM grows; the liquidity floor (L0) and ADV-participation cap (Section 7)
  are the two levers that keep fills realistic.
- **Out of scope (explicitly):** intraday scalping, options-premium strategies, short selling,
  pairs/market-neutral construction, and anything requiring leverage. These are noted so the
  validation in Section 10 is not silently expected to cover them.

---

## 1. Critique of the original strategy

The original triggers when **all four** are true:

1. Stock trades through its 52-week high
2. ATR over the last 20 days has gone up 2×
3. With 26-week range = R, price has traded ≥ 52wk-high + 0.25 R
4. Closely related stocks show similar price action

The instincts are good — new highs, volatility, breakout extension, peer confirmation. But each
rule has a flaw, and **two of them (2 and 3) systematically make the signal late**.

### Rule 1 — "trades through 52-week high"
- **Intraday vs close.** Intraday penetration invites bull traps. → Use a **closing** basis.
- **No volume.** → Require **volume ≥ ~1.5–2× the 50-day average** on the breakout bar.
- **Ignores the path to the high.** A grind out of a tight base ≠ a 40% earnings gap. → Add
  **base/setup quality** (L3).
- **52wk-high ≠ all-time-high.** Below ATH there is overhead supply. → Track distance to ATH and
  prefer "blue-sky" breakouts.

### Rule 2 — "ATR(20) doubled" — the most counterproductive rule
- 2× ATR means volatility **already** exploded → you buy *after* the move began.
- Strongest setups come from volatility **contraction** before the break (VCP, BB squeeze, NR7,
  low ATR percentile). Expansion should be the **one-bar trigger**, not a pre-condition.
- **Fix:** screen for ATR/BB-width **contraction** during the base; require single-bar
  volatility + volume **expansion** *on* the breakout bar.

### Rule 3 — "52wk-high + 0.25 R, R = 26-week range"
- Right idea, wrong normalizer. R = (26wk high − 26wk low): for a trender R is huge → trigger
  late; for a quiet stock R is tiny → noise. The 26wk low is often an irrelevant crash print.
- **Fix:** normalize the buffer to **current volatility**: pivot + 0.5–1.0 × ATR(20), or a fixed
  2–3% above pivot (Minervini buy-point style).

### Rule 4 — "related stocks show similar price action"
- Undefined; worse, requiring peers to *already* break tends to buy the **laggard**. Leaders
  break first.
- **Fix:** require **top RS within the group**, a group whose **aggregate RS is rising**, and the
  stock to be **among the first** to break. Use the news/theme overlay to define the cluster.

### Cross-cutting problems (and where v1.0 fixes them)
- **Hard AND of four noisy conditions is brittle.** → few **hard gates** + a **calibrated
  weighted score** (Sections 4–6).
- **No trade lifecycle.** → one unambiguous lifecycle per track (Section 8).
- **No portfolio view.** → portfolio construction + risk aggregation (Section 7).
- **No regime awareness.** → multi-factor regime gate (Section 5, L1).
- **No validation.** → Section 10, with pre-registered criteria and an overfitting budget.

---

## 2. Design principles

1. **Gates vs scores.** Necessary conditions are hard gates; quality dimensions are scored and
   ranked. Avoids the brittleness of a 4-way AND while keeping discipline.
2. **Contraction → expansion.** The setup is built during volatility *contraction*; the trigger is
   the volatility/volume *expansion*. This is what makes signals early.
3. **Two tracks, one engine.** A *confirmed-breakout* track and a *pre-breakout anticipation*
   track share gates and infrastructure but have distinct entries, stops, and validation
   (Section 3). This resolves the v0.5 contradiction between "must close above pivot" and "buy
   2nd-order names before they break out."
4. **Lead, don't lag.** Prefer the strongest name in a strengthening group, breaking early.
5. **Catalyst as a weight, not a wall.** News raises/lowers rank and propagates a theme; it is
   never a hard requirement.
6. **Calibrate before you weight.** A composite score is worthless unless higher scores actually
   correspond to higher forward returns; this is checked, not assumed (Section 6).
7. **Portfolio risk is part of the strategy, not an afterthought** (Section 7) — especially because
   theme clustering deliberately concentrates correlated risk.
8. **Pre-register success and kill criteria.** Decide what "good" means *before* backtesting
   (Section 10) to avoid p-hacking across ~30 parameters.

---

## 3. Two signal tracks

Both tracks share the same **hard gates** and infrastructure; they differ only in the *trigger*
and the *trade lifecycle*. Validate and prove **Track A first**; only add Track B once Track A
clears the success criteria (Section 10/11).

| Aspect | Track A — Confirmed breakout | Track B — Pre-breakout anticipation |
|--------|------------------------------|--------------------------------------|
| Thesis | Buy the confirmed break with volume | Buy *inside* a tight base before the break, on theme + leadership + accumulation |
| Shared gates | L0 liquidity, L1 regime, L2 trend | same |
| Trigger | **Close above pivot** + ATR/%-buffer + volume surge + range expansion (L4) | (theme propagation from graph) ∧ (RS leadership in a rising group) ∧ (in-base accumulation / volume dry-up) — **no breakout required** |
| Role of the breakout | The entry | A **confirmation / pyramid-add** event, not the entry |
| Initial stop | Below pivot or entry − 1.5×ATR(20), tighter of the two | Below the base low (tighter, since entry is inside the base) |
| Starting size | Full per-trade risk (Section 7) | **Half** the per-trade risk; add the other half on confirmed breakout |
| Failure mode | Failed breakout (close back below pivot) → fast exit | Base breaks *down* / theme fades → exit at base-low stop |
| Validation | Its own base rate + expectancy (Section 10) | **Separately** validated; must earn its keep vs Track A alone |
| Expected profile | Higher win rate, later entry | Lower win rate, earlier/larger average win, more false starts |

**Why two tracks rather than one.** Track A is honest momentum: high base rate, but by definition
late. Track B is the "early 2nd-order beneficiary" idea from Section 5 — but it can only be entered
*before* a breakout, so it cannot live behind the L4 breakout gate. Keeping them separate lets each
be measured on its own terms and prevents Track B's noise from contaminating Track A's statistics.

---

## 4. Data architecture (Schwab + Alpaca)

| Need | Primary source | Notes |
|------|----------------|-------|
| Daily/weekly OHLCV (universe-wide) | Alpaca Market Data | bulk pulls; build daily + resampled weekly |
| Per-symbol intraday candles | Schwab pricehistory | cross-check + trigger-bar confirmation |
| Options volume & IV (attention) | Schwab options chains | Alpaca options as backup |
| Fundamentals / earnings dates & surprises | Schwab instruments/fundamentals | supplement with an earnings-calendar source |
| Movers / most-active (discovery) | Schwab movers + Alpaca screener | seeds the *live* candidate pool — see leakage note below |
| News (unstructured overlay) | Alpaca News API (Benzinga) | real-time + historical headlines/bodies by symbol |
| Corporate actions (splits/divs/spinoffs) | Alpaca corporate actions | needed for correct adjustment |

### Adjustment policy (subtle but important)
- **Breakout levels (52wk high, ATH, pivots, base highs) use SPLIT-ADJUSTED but NOT
  dividend-adjusted prices.** Traders watch *actual price* highs; dividend back-adjustment shifts
  historical prices down and produces phantom new highs. Reverse-split and special-dividend events
  must be handled, and **spinoffs reset the price history** — flag and quarantine the pre-spinoff
  window for level computation.
- **Performance/return series (RS, backtest P&L) use TOTAL-RETURN (split + dividend adjusted).**
- Keep both series; never compute breakout levels off the total-return series.

### Point-in-time everything (or the backtest lies)
Every input that can be *restated* must be stored as-of its observation date:
- **Universe membership** (include delisted names; reconstruct as of each date) — survivorship.
- **GICS sector/sub-industry** — classifications change; using today's mapping historically leaks.
- **ETF holdings** (used for clustering) — holdings change; use historical holdings.
- **Fundamentals / earnings surprises** — frequently restated/backfilled; use first-reported
  values with their report timestamps.
- **News** — store the publish timestamp; bodies get edited, so snapshot the version available at
  signal time.
- **Movers/most-active seed** — this is a *live* feed and is **not reliably reconstructable
  point-in-time.** For the backtest, do **not** seed candidates from movers; instead derive the
  candidate pool from the cached bar universe (every symbol passing L0 is eligible). Movers may be
  used *live* as an attention feature, with a documented caveat that it cannot be backtested.

### Engineering notes
- **Cache raw bars** locally (Parquet/SQLite) keyed by symbol+date; recompute indicators from the
  cache so the backtest and live screen are byte-for-byte identical.
- **One indicator library** shared by backtest and live screen — the #1 source of "works in
  backtest, fails live."
- **Rate limits:** batch Alpaca, throttle Schwab, central token refresh.

---

## 5. The screening funnel (shared gates + Track-A trigger)

Each layer **gates** (drop) or **scores** (0–1). Gates L0/L1/L2 are shared by both tracks; L4 is
the Track-A trigger; L3/L5/L6 feed the score for both.

### L0 — Universe & liquidity *(gate)*
- Price ≥ `min_price`; 20-day average **dollar volume** ≥ `min_dollar_volume`.
- Exclude leveraged/inverse ETFs, recent IPOs (< `min_history_days`, 52wk high undefined),
  non-common classes.

### L1 — Market regime *(gate, scales exposure)* — now multi-factor
Breakouts need risk appetite, not just an index above a line. Combine:
- **Trend:** benchmark above its 200-day MA, 200-day slope ≥ 0.
- **Breadth:** % of universe above its 50-day MA above a floor; new-highs ≥ new-lows.
- **Distribution:** count of recent high-volume down days below a ceiling.
Output a **regime score in [0,1]** that scales position count / sizing (Section 7), plus a hard
"risk-off" cutoff that takes new exposure to zero. The benchmark for trend is the broad index; the
benchmark for **RS** is the **universe median return** (or a size/style-matched index), *not* SPY
for small caps.

### L2 — Trend template (Stage-2 uptrend) *(gate)*
Minervini-style: close > 50 > 150 > 200 MA (with tolerance); 200-day rising ≥ ~1 month; close
within `within_high_pct` of 52wk high and ≥ `above_low_pct` above 52wk low.

### L3 — Setup quality *(score)* — the "early" fix
- **Volatility contraction:** ATR(20)/price and Bollinger-band width in a **low percentile** vs
  their trailing year (squeeze). Tighter = higher.
- **Base structure (precise):** detect a **consolidation** — the most recent window of ≥
  `base_min_weeks` where the high-to-low range stays within `base_max_depth` and successive
  pullbacks contract (VCP-like). The **pivot** is the high of that consolidation (a single, well-
  defined level), not "max over 30 bars." If no qualifying base exists, base score = 0.
- **RS line** at/near new highs (often leads price).
- **RS rank (precise):** percentile of a **weighted multi-period total return** (e.g. blend of
  3/6/12-month, recent-weighted) vs the **liquid universe**; prefer top decile/quartile.

### L4 — Breakout trigger *(gate — Track A only)* — fixes Rules 1 & 3
- **Close** (not intraday) above the **pivot** (= consolidation high; flag if also an all-time
  high → "blue sky").
- Penetration buffer = pivot + max(`atr_buffer_mult`×ATR(20), `pct_buffer`×price) — ATR/%-
  normalized, **not** 0.25 R.
- **Volume ≥ `volume_mult`×** the 50-day average on the breakout bar.
- **Range expansion** on the breakout bar (true range > recent average TR).

### L5 — Group / theme confirmation *(score)* — fixes Rule 4
Define the cluster (Section 9: GICS sub-industry ∪ ETF co-membership ∪ supply-chain graph ∪
rolling-correlation cluster, all **point-in-time**). Reward: group RS rising; this name a **leader**
within the cluster; **broke early** (few peers already extended). Penalize buying the last laggard.

### L6 — Catalyst / news overlay *(score)* — Section 9.

### Earnings proximity *(flag + optional gate)*
Mark whether the trigger bar is within `earnings_window_days` of a scheduled report.
Earnings-gap breakouts are a **distinct, higher-failure species**; by default the lifecycle
(Section 8) reduces size and tightens the stop for earnings-adjacent entries, and offers an
ablation switch to exclude them entirely.

---

## 6. Scoring & calibration

The composite is only meaningful if it is built from comparable pieces and actually predicts
returns.

- **Common scale.** Every scored feature is mapped to either a **cross-sectional percentile**
  (rank within today's eligible universe) or a **z-score**, so a percentile, a binary, and a ratio
  are never summed raw. Binaries become {0,1}; ratios are ranked.
- **Composite.** `composite = Σ wᵢ · featureᵢ` over the scored layers (regime, setup, group,
  catalyst). Start with **transparent default weights** (Section 13). Optionally fit weights with a
  **simple, monotonic** model (e.g. isotonic / logistic on a *single* engineered score), never a
  high-parameter learner on raw features — see overfitting budget (Section 10).
- **Calibration check (gating result).** Bucket historical signals by composite decile and plot
  **forward return / hit-rate per decile**. The composite is only accepted if it is **monotone**:
  higher deciles → better outcomes, out-of-sample. A non-monotone composite is rejected regardless
  of headline backtest P&L.

---

## 7. Portfolio construction & risk aggregation

The funnel emits a *ranked list*; this section turns the list into positions. It is essential
because the theme/group logic deliberately produces **correlated** candidates.

- **Per-trade risk:** `account_risk_pct` of equity (Section 13). Shares = risk$ / stop-distance.
- **Position count:** at most `max_positions`, scaled down by the regime score (risk-off → fewer
  or zero new positions).
- **ADV-participation cap:** position notional ≤ `max_adv_participation` × 20-day ADV, so fills are
  realistic and capacity-aware. The binding constraint is min(risk-based size, ADV cap).
- **Theme / sector heat caps:** sum of **open risk** within any one theme ≤ `max_theme_heat`, and
  within any GICS sector ≤ `max_sector_heat`. This is the direct antidote to "all my AI names broke
  the same day."
- **Total portfolio heat:** sum of open risk across all positions ≤ `max_portfolio_heat`.
- **Correlation-aware selection:** when picking from the ranked list, skip a candidate whose
  trailing return correlation to an existing holding exceeds `max_pair_corr` (prefer the
  higher-composite name). Prevents stacking the same bet under different tickers.
- **Pyramiding (Track B → A):** Track B enters at half risk inside the base; on a confirmed L4
  breakout, add the remaining half, subject to all heat caps.
- **Regime → exposure mechanism (concrete):** target number of new positions =
  round(`max_positions` × regime_score); below the risk-off cutoff, zero new entries (existing
  positions still managed by their stops).

---

## 8. Trade lifecycle (one unambiguous default per track)

Backtestable means singular: each rule below is a **default**, and listed alternatives are explicit
**ablation switches**, never "and/or."

### Common to both tracks
- **Entry fill:** next bar's **open** after the signal (never the signal close).
- **Costs:** commission + participation-based slippage; model gap-up entries as filling worse than
  the trigger (Section 10).
- **Time stop:** exit if the position has not reached +1R within `time_stop_days`.
- **Earnings handling (default):** if entry is within `earnings_window_days` of a report, halve the
  starting size and tighten the initial stop to the lesser of the default stop and 1.0×ATR.

### Track A — confirmed breakout
- **Initial stop (default):** the **tighter** of (pivot − small buffer) and (entry − 1.5×ATR(20)).
- **Profit management (default):** **trail under the rising 20-day MA**, exit on a *close* below
  it. *Ablation switches:* (S1) take a partial at +2.5R then trail the remainder; (S2) fixed
  target at +3R. Exactly one is active per backtest run.
- **Fast-exit rule (where most edge lives):** exit immediately on a **close back below the pivot**
  within the first `failed_breakout_days` bars.

### Track B — pre-breakout anticipation
- **Initial stop (default):** below the **base low**.
- **Confirmation add:** on a confirmed L4 breakout, add to bring the position to full risk; from
  then on the position is managed by the **Track A** rules.
- **Abort:** if the base resolves *downward* (close below base low) or the theme score decays below
  `theme_decay_floor` before a breakout, exit at the stop.

---

## 9. Unstructured / news & theme overlay

The event-driven, thematic-momentum overlay answering *why* a cluster is moving (e.g. ChatGPT →
NVDA; agentic compute → CPU names; memory shortage → memory makers). It powers L5/L6 and is the
engine behind Track B's early discovery.

### 9.1 Theme / supply-chain knowledge graph
Map **catalyst → theme → 1st/2nd-order beneficiaries** (AI demand → GPUs → HBM/memory →
networking/optics → power & cooling). Seed from point-in-time GICS, ETF-holdings overlap, and
customer/supplier relations; refine with an LLM (propose tickers by exposure order, tag the
mechanism). A single event flags the **whole cluster**, powering L5 and surfacing 2nd-order names
early (Track B). Store as versioned, human-reviewable nodes + weighted edges.

### 9.2 LLM catalyst-scoring pipeline (per candidate)
For each ticker clearing the technical screen, pull recent items (Alpaca news + 8-Ks / PRs /
transcripts) → structured features: `catalyst_present`, `catalyst_type`, **durability** (one-off
vs multi-quarter structural — dominates the score), `novelty`, `theme_tags`, `confidence`,
`rationale`. Guardrails: dedupe wire stories; **only use items time-stamped ≤ signal time**; keep
raw text + output for audit; never auto-trade on a headline.

### 9.3 Attention / abnormality signals (often lead price)
News-volume spike (z-score of daily article count); options call-volume & IV jumps (Schwab
chains); optional social/search velocity.

### 9.4 LLM backtestability (new — the hard part)
Using an *evolving* model as a *historical* feature is non-stationary and must be controlled:
- **Freeze model + prompt version per backtest run**; record both in the run manifest. Changing the
  model is a new experiment, not a re-run.
- **Cache scored artifacts** keyed by `(news_item_id, model_id, prompt_version)`; the backtest
  reads the cache so it is deterministic and cheap to re-run.
- **Point-in-time scoring:** score each item using only itself and context available at its
  timestamp.
- **Evaluate the scorer itself:** does the `durability` label actually predict forward return?
  Treat the overlay as a feature to be ablated (Section 10), not assumed-good. If it doesn't add
  expectancy, drop it.
- **Cost/latency:** scoring is bounded to candidates that already passed the technical screen, not
  the whole universe.

---

## 10. Validation & backtesting (non-negotiable before risking capital)

**Pre-registered success criteria (decide before backtesting):**
- Beat **buy-and-hold QQQ** on a risk-adjusted basis (Sharpe and MAR/Calmar) by a stated margin,
  net of costs, out-of-sample.
- **Positive expectancy per trade in R** with a profit factor above a stated floor.
- A **minimum trade count** for statistical significance; results below it are "inconclusive,"
  not "good."

**Kill criteria:** if OOS expectancy ≤ 0, or the composite calibration (Section 6) is non-monotone
OOS, or drawdown exceeds the buy-and-hold benchmark without commensurate return — the variant is
shelved, not re-tuned.

**Leak-free mechanics:** point-in-time universe (incl. delisted); indicators through the signal bar
only; news ≤ signal time; entry on next bar's open; candidate seed from cached bars, not the live
movers feed (Section 4).

**Costs:** commissions, spread/participation slippage (larger for breakout fills; gap-ups fill
worse than the trigger).

**Metrics:** base rate (win %), avg win/loss in **R**, expectancy/trade, profit factor, max
drawdown, exposure, follow-through distribution — reported **per track** and vs the naive
"buy any 52wk-high close" baseline.

**Robustness & anti-overfitting:**
- **Overfitting budget.** Most parameters are **frozen** at literature-standard defaults
  (Section 13). Only a small, **named** subset is tunable; tuning happens on in-sample data and is
  confirmed OOS via **walk-forward**.
- **Multiple-testing control.** Because many variants/ablations are tried, report a **deflated
  Sharpe** / White's reality-check-style adjustment; be suspicious of any single magic threshold.
- **Drawdown distribution** via bootstrap / Monte-Carlo on the trade sequence, not just the single
  realized path.
- **Regime-conditional expectancy** (bull / chop / bear) reported as a **gating result**, not a
  footnote.
- **Per-layer and per-track ablations:** measure the marginal expectancy of each layer and of
  Track B over Track A; drop anything that doesn't earn its keep.

**Reality check:** even a good version is a *ranking/discovery* tool; most realized edge comes from
the regime gate, the portfolio heat caps, and disciplined exits — not a cleverer entry trigger.

---

## 11. Phased build plan

1. **Data layer.** Unified bar store (Alpaca bulk + Schwab cross-check); split-only vs total-return
   series (Section 4); shared indicator library; point-in-time universe/GICS/ETF/news stores.
2. **Track-A funnel (L0–L4) + scoring (L3/L5/L6 features on a common scale).**
3. **Portfolio layer (Section 7)** — heat caps, ADV cap, correlation-aware selection, regime
   scaling.
4. **Backtest + calibration of Track A.** Point-in-time, leak-free, costed. **Must pass the
   Section 10 success criteria and Section 6 calibration before proceeding.**
5. **Group/RS layer (L5)** — point-in-time clusters; group RS + leadership scoring.
6. **News & theme overlay (L6 + graph)** with the LLM backtestability controls (Section 9.4);
   re-run ablations to confirm it adds expectancy.
7. **Track B (pre-breakout anticipation)** — entry/stop/confirm-add per Section 8; **separately**
   validated against Track-A-only.
8. **Composite ranking + monitoring** — final weights, daily candidate report, signal logging.
9. **Paper-trade reconciliation** — compare realized vs modeled slippage and live vs backtest
   signals; only size up after they match.

---

## 12. Original-rule → fix summary

| # | Original rule | Core problem | Fix in v1.0 |
|---|---------------|--------------|-------------|
| 1 | Trade through 52wk high | intraday traps; no volume; ignores base; 52wk ≠ ATH | close-basis breakout (L4) + volume surge + base quality (L3) + ATH flag |
| 2 | ATR(20) doubled | volatility already exploded → late | pre-breakout **contraction** (L3); expansion only as the one-bar trigger (L4) |
| 3 | 52wk-high + 0.25 R | range normalizer → late on trenders, noisy on quiet names | ATR/%-normalized buffer off a precisely defined pivot (L4) |
| 4 | Related stocks similar | undefined; buys the laggard | RS leader in a rising, point-in-time cluster, broke early (L5 + §9) |
| — | (none) | no scope, regime depth, portfolio, calibration, lifecycle, validation rigor | §0 scope; multi-factor regime (L1); portfolio heat caps (§7); calibration (§6); single-default lifecycle (§8); pre-registered validation + overfitting budget (§10) |
| — | (contradiction) | breakout gate vs. "buy before the break" | **two tracks** (§3): Track A confirmed-breakout, Track B pre-breakout anticipation |

---

## 13. Parameter register

Every threshold, its default, its source, and whether it is **frozen** (held at a defensible
default) or **in the tuning budget** (the small set we may optimize, in-sample then OOS). This
table *is* the overfitting budget from Section 10.

| Param | Default | Layer | Source | Status |
|-------|---------|-------|--------|--------|
| `min_price` | $7 | L0 | convention | frozen |
| `min_dollar_volume` | $15M | L0 | capacity | frozen |
| `min_history_days` | 130 (~6mo) | L0 | 52wk defined | frozen |
| benchmark / 200d MA + slope | SPY, 200, ≥0 | L1 | standard | frozen |
| breadth floor (% > 50d) | 0.40 | L1 | literature | **tunable** |
| distribution-day ceiling | 5 / 25d | L1 | O'Neil | frozen |
| MA stack | 50/150/200 | L2 | Minervini | frozen |
| `within_high_pct` / `above_low_pct` | 0.25 / 0.30 | L2 | Minervini | frozen |
| squeeze percentile window | 252 | L3 | 1yr | frozen |
| `base_min_weeks` / `base_max_depth` | 3 / 0.15 | L3 | VCP | **tunable** |
| RS rank blend / window | 3-6-12mo recent-wt | L3 | IBD-style | **tunable** |
| `atr_buffer_mult` / `pct_buffer` | 0.75×ATR / 2.5% | L4 | Minervini | **tunable** |
| `volume_mult` / avg period | 1.5× / 50 | L4 | convention | frozen |
| `earnings_window_days` | 5 | lifecycle | convention | frozen |
| `account_risk_pct` | 0.75% | §7 | risk-of-ruin | frozen |
| `atr_stop_mult` | 1.5 | §8 | convention | **tunable** |
| `max_positions` | 8 | §7 | concentration | **tunable** |
| `max_adv_participation` | 1% | §7 | capacity | frozen |
| `max_theme_heat` / `max_sector_heat` | 2% / 3% equity | §7 | concentration | frozen |
| `max_portfolio_heat` | 6% equity | §7 | risk | frozen |
| `max_pair_corr` | 0.8 | §7 | de-dup | frozen |
| `time_stop_days` | 15 | §8 | convention | **tunable** |
| `failed_breakout_days` | 5 | §8 | convention | frozen |
| `theme_decay_floor` | 0.3 | §8 (Track B) | prior | **tunable** |
| `first_target_r` (ablation S1) | 2.5R | §8 | convention | **tunable** |
| composite weights | setup .35 / group .20 / catalyst .25 / regime .20 | §6 | prior | **tunable (or fit)** |
| LLM model + prompt version | pinned per run | §9.4 | reproducibility | frozen-per-run |

*Discipline:* the "tunable" rows are the only knobs touched during optimization; everything else is
held fixed. This keeps researcher degrees-of-freedom small enough that the Section 10 significance
tests are meaningful.

*End of design document (v1.0).*
