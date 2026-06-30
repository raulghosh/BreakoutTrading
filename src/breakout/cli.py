"""Command-line entry point.

    breakout demo                     # synthetic demo (no keys needed)
    breakout screen SYM [SYM...]      # screen named symbols from the local bar cache
    breakout fetch  SYM [SYM...]      # download bars from Alpaca into the cache
    breakout scan   [--top N]         # screen every symbol in the cache
    breakout backtest SYM [SYM...]    # simulate the strategy on cached bars
    breakout universe [--save FILE]   # list tradeable US equities from Alpaca
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .config import Settings
from .data.store import BarStore
from .screen.funnel import screen_symbol
from .screen.l6_catalyst import CatalystContext


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_candidate(cand) -> None:
    print(f"\n=== {cand.symbol} @ {cand.date.date()} ===")
    for lr in cand.layers:
        if lr.kind == "gate":
            mark = "PASS" if lr.passed else "FAIL"
            print(f"  [{mark}] {lr.name}")
        else:
            print(f"  [score={lr.score:.3f}] {lr.name}")
    if cand.passed_gates:
        print(f"  -> COMPOSITE {cand.composite:.3f}"
              + ("  (ATH breakout)" if cand.is_ath_breakout else ""))
        r = cand.risk
        print(f"  -> RISK entry={r.entry} stop={r.stop} shares={r.shares} "
              f"risk=${r.risk_dollars} target={r.first_target} ({r.r_multiple_to_target:.1f}R)")
    else:
        print(f"  -> REJECTED at {cand.rejected_at}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_demo(args) -> int:
    from .synthetic import make_benchmark, make_breakout_series

    settings = Settings.load(args.config)
    bench = make_benchmark()
    df = make_breakout_series()
    cand = screen_symbol("DEMO", df, settings, benchmark_df=bench)
    _print_candidate(cand)
    if args.json:
        print(json.dumps({"symbol": cand.symbol, "passed_gates": cand.passed_gates,
                          "composite": cand.composite}, indent=2))
    return 0


def cmd_fetch(args) -> int:
    """Download split-adjusted daily bars from Alpaca and save to the local cache."""
    from datetime import datetime, timedelta
    from .data.alpaca import AlpacaProvider

    provider = AlpacaProvider()          # reads .env automatically
    store = BarStore(args.cache)

    end = datetime.today()
    start = end - timedelta(days=args.lookback)

    # Deduplicate; ensure benchmark is always fetched first
    seen: dict[str, None] = {}
    for sym in [args.benchmark] + list(args.symbols):
        seen[sym.upper()] = None
    symbols = list(seen)

    ok, failed = 0, []
    for sym in symbols:
        print(f"  {sym:<8} ...", end=" ", flush=True)
        try:
            df = provider.daily_bars(sym, start, end)
            if df.empty:
                print("no data")
                failed.append(sym)
                continue
            store.save(sym, df)
            print(f"{len(df)} bars  ({df.index[0].date()} → {df.index[-1].date()})")
            ok += 1
        except Exception as exc:
            print(f"FAIL  {exc}")
            failed.append(sym)

    print(f"\n{ok}/{len(symbols)} fetched"
          + (f"  |  failures: {', '.join(failed)}" if failed else ""))
    return 0 if not failed else 1


def _fetch_catalyst(sym: str, as_of, args) -> CatalystContext | None:
    """Fetch news and score catalyst for `sym`. Returns None if --news not set or fetch fails."""
    if not getattr(args, "news", False):
        return None
    try:
        from datetime import timedelta
        from .data.alpaca import AlpacaProvider
        from .news.catalyst_llm import score_catalyst
        provider = AlpacaProvider()
        start = as_of - timedelta(days=14)
        items = provider.news(sym, start, as_of)
        return score_catalyst(sym, items, as_of=as_of)
    except Exception as exc:
        print(f"  [news] {sym}: {exc}", file=sys.stderr)
        return None


def cmd_screen(args) -> int:
    settings = Settings.load(args.config)
    store = BarStore(args.cache)
    if not store.has(args.benchmark):
        print(f"benchmark bars for {args.benchmark} not in cache ({args.cache}). "
              f"Run: breakout fetch {args.benchmark}", file=sys.stderr)
        return 2
    bench = store.load(args.benchmark)

    survivors = []
    for sym in args.symbols:
        if not store.has(sym):
            print(f"skip {sym}: not in cache (run: breakout fetch {sym})", file=sys.stderr)
            continue
        df = store.load(sym)
        as_of = df.index[-1].to_pydatetime()
        catalyst_ctx = _fetch_catalyst(sym, as_of, args)
        cand = screen_symbol(sym, df, settings, benchmark_df=bench,
                             account_equity=args.equity, catalyst_ctx=catalyst_ctx)
        _print_candidate(cand)
        if cand.passed_gates:
            survivors.append(cand)

    survivors.sort(key=lambda c: c.composite or 0, reverse=True)
    print(f"\n{len(survivors)} survivor(s), ranked by composite:")
    for c in survivors:
        print(f"  {c.composite:.3f}  {c.symbol}")
    return 0


def cmd_scan(args) -> int:
    """Run the funnel on every symbol in the bar cache and print the ranked signal list."""
    settings = Settings.load(args.config)
    store = BarStore(args.cache)

    if not store.has(args.benchmark):
        print(f"No benchmark bars for {args.benchmark}. "
              f"Run: breakout fetch {args.benchmark}", file=sys.stderr)
        return 2

    bench = store.load(args.benchmark)
    symbols = [s for s in store.symbols() if s != args.benchmark.upper()]
    if not symbols:
        print("No cached symbols. Run: breakout fetch SYM [SYM...]", file=sys.stderr)
        return 2

    print(f"Scanning {len(symbols)} symbol(s) ...")
    survivors, rejected_counts = [], {}
    for sym in symbols:
        df = store.load(sym)
        as_of = df.index[-1].to_pydatetime()
        catalyst_ctx = _fetch_catalyst(sym, as_of, args)
        cand = screen_symbol(sym, df, settings, benchmark_df=bench,
                             account_equity=args.equity, catalyst_ctx=catalyst_ctx)
        if cand.passed_gates:
            survivors.append(cand)
        else:
            rejected_counts[cand.rejected_at] = rejected_counts.get(cand.rejected_at, 0) + 1

    survivors.sort(key=lambda c: c.composite or 0, reverse=True)
    top = survivors[: args.top]

    print(f"\n{len(survivors)} signal(s) from {len(symbols)} scanned:\n")
    if top:
        hdr = f"  {'#':<4} {'SYM':<8} {'COMP':>6}  {'ENTRY':>8}  {'STOP':>8}  {'TARGET':>8}  R"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for i, c in enumerate(top, 1):
            r = c.risk
            ath = "  [ATH]" if c.is_ath_breakout else ""
            print(f"  {i:<4} {c.symbol:<8} {c.composite:>6.3f}  "
                  f"{r.entry:>8.2f}  {r.stop:>8.2f}  {r.first_target:>8.2f}  "
                  f"{r.r_multiple_to_target:.1f}R{ath}")

    if rejected_counts:
        print("\n  Rejections by gate:")
        for gate, n in sorted(rejected_counts.items(), key=lambda x: -x[1]):
            print(f"    {gate}: {n}")

    return 0


def _print_backtest(res) -> None:
    start, end = res.window
    print(f"\n=== BACKTEST {res.symbol} ===")
    print(f"  window     : {start.date()} → {end.date()}  ({res.equity.get('n_bars', 0)} bars)")
    print(f"  signals    : {res.n_signals}")
    print(f"  trades     : {res.metrics.get('n', 0)}")

    m = res.metrics
    if m.get("n", 0):
        pf = m["profit_factor"]
        pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"\n  win_rate     : {m['win_rate'] * 100:.1f}%")
        print(f"  avg_win_r    : {m['avg_win_r']:+.2f}R")
        print(f"  avg_loss_r   : {m['avg_loss_r']:+.2f}R")
        print(f"  expectancy_r : {m['expectancy_r']:+.2f}R / trade")
        print(f"  profit_factor: {pf_str}")
        print(f"  total_r      : {m['total_r']:+.2f}R")
        print(f"  avg_hold     : {m['avg_bars_held']:.1f} bars")

    e = res.equity
    if e.get("n_bars", 0):
        print(f"\n  return       : {e['total_return_pct']:+.2f}%   "
              f"(${e['start_equity']:,.0f} → ${e['end_equity']:,.0f})")
        print(f"  max_drawdown : {e['max_drawdown_pct']:.2f}%")
        print(f"  buy & hold   : {res.buy_hold_pct:+.2f}%   "
              f"<- strategy {'BEAT' if e['total_return_pct'] > res.buy_hold_pct else 'TRAILED'} "
              f"buy-and-hold")


def _print_trades(res) -> None:
    if not res.trades:
        return
    print("\n  Trades:")
    hdr = (f"    {'ENTRY':<12} {'EXIT':<12} {'IN':>8} {'OUT':>8} "
           f"{'SH':>5} {'BARS':>4} {'R':>6}  REASON")
    print(hdr)
    print("    " + "-" * (len(hdr) - 4))
    for t in res.trades:
        ed = t.entry_date.date() if t.entry_date is not None else "?"
        xd = t.exit_date.date() if t.exit_date is not None else "?"
        print(f"    {str(ed):<12} {str(xd):<12} {t.entry:>8.2f} {t.exit:>8.2f} "
              f"{t.shares:>5} {t.bars_held:>4} {t.r_multiple:>+6.2f}  {t.exit_reason}")


def cmd_backtest(args) -> int:
    from .backtest.engine import BacktestConfig, backtest_symbol

    settings = Settings.load(args.config)
    store = BarStore(args.cache)

    if not store.has(args.benchmark):
        print(f"benchmark bars for {args.benchmark} not in cache. "
              f"Run: breakout fetch {args.benchmark}", file=sys.stderr)
        return 2
    bench = store.load(args.benchmark)
    config = BacktestConfig.from_settings(settings, account_equity=args.equity)
    config.min_composite = args.min_composite

    for sym in args.symbols:
        if not store.has(sym):
            print(f"skip {sym}: not in cache (run: breakout fetch {sym})", file=sys.stderr)
            continue
        df = store.load(sym)

        # Default test window = trailing --lookback-days; earlier bars are warmup.
        start = args.start
        if start is None and args.end is None:
            cutoff = df.index[-1] - pd.Timedelta(days=args.lookback_days)
            start = cutoff if cutoff > df.index[0] else None

        res = backtest_symbol(sym, df, bench, settings, config,
                              start=start, end=args.end)
        _print_backtest(res)
        if args.verbose:
            _print_trades(res)
    return 0


def cmd_universe(args) -> int:
    """Fetch the list of active, tradeable US equity symbols from Alpaca."""
    from .data.alpaca import AlpacaProvider

    provider = AlpacaProvider()
    print("Fetching tradeable US equity universe from Alpaca ...", flush=True)
    symbols = provider.active_us_equities()
    print(f"{len(symbols)} active tradeable US equities found.")

    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(symbols) + "\n")
        print(f"Saved → {out}")
    else:
        for sym in symbols:
            print(sym)
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="breakout",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--config", default=None, help="path to settings.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    # demo ---------------------------------------------------------------
    d = sub.add_parser("demo", help="run the funnel on a synthetic breakout series (no keys)")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_demo)

    # fetch --------------------------------------------------------------
    f = sub.add_parser("fetch", help="download daily bars from Alpaca into the local cache")
    f.add_argument("symbols", nargs="+", metavar="SYM", help="ticker(s) to fetch")
    f.add_argument("--benchmark", default="SPY", help="always fetch this symbol too (default: SPY)")
    f.add_argument("--lookback", type=int, default=504,
                   help="calendar days of history to download (default: 504 ≈ 2 yrs)")
    f.add_argument("--cache", default="data/cache")
    f.set_defaults(func=cmd_fetch)

    # screen -------------------------------------------------------------
    s = sub.add_parser("screen", help="screen named cached symbols")
    s.add_argument("symbols", nargs="+", metavar="SYM")
    s.add_argument("--benchmark", default="SPY")
    s.add_argument("--cache", default="data/cache")
    s.add_argument("--equity", type=float, default=100_000.0)
    s.add_argument("--news", action="store_true",
                   help="fetch Alpaca news and score catalyst with Claude (requires ANTHROPIC_API_KEY)")
    s.set_defaults(func=cmd_screen)

    # scan ---------------------------------------------------------------
    sc = sub.add_parser("scan", help="screen every symbol in the bar cache")
    sc.add_argument("--benchmark", default="SPY")
    sc.add_argument("--equity", type=float, default=100_000.0)
    sc.add_argument("--top", type=int, default=20, help="rows to show (default: 20)")
    sc.add_argument("--cache", default="data/cache")
    sc.add_argument("--news", action="store_true",
                    help="fetch Alpaca news and score catalyst with Claude (requires ANTHROPIC_API_KEY)")
    sc.set_defaults(func=cmd_scan)

    # backtest -----------------------------------------------------------
    b = sub.add_parser("backtest", help="simulate the strategy on cached bars")
    b.add_argument("symbols", nargs="+", metavar="SYM")
    b.add_argument("--benchmark", default="SPY")
    b.add_argument("--start", default=None, help="test-window start (YYYY-MM-DD)")
    b.add_argument("--end", default=None, help="test-window end (YYYY-MM-DD)")
    b.add_argument("--lookback-days", type=int, default=365,
                   help="if no --start/--end, test the trailing N days (default: 365)")
    b.add_argument("--equity", type=float, default=100_000.0)
    b.add_argument("--min-composite", type=float, default=0.0,
                   help="only take signals at/above this composite rank")
    b.add_argument("--verbose", action="store_true", help="print the per-trade log")
    b.add_argument("--cache", default="data/cache")
    b.set_defaults(func=cmd_backtest)

    # universe -----------------------------------------------------------
    u = sub.add_parser("universe", help="list active US equity symbols from Alpaca")
    u.add_argument("--save", metavar="FILE", default=None,
                   help="write one symbol per line to FILE instead of stdout")
    u.set_defaults(func=cmd_universe)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
