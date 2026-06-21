"""Command-line entry point.

    breakout demo                 # run the funnel on a synthetic breakout (no keys needed)
    breakout screen SYM [SYM..]   # run on cached bars in data/cache (Phase 1 providers fill it)
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import Settings
from .data.store import BarStore
from .screen.funnel import screen_symbol


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


def cmd_screen(args) -> int:
    settings = Settings.load(args.config)
    store = BarStore(args.cache)
    if not store.has(args.benchmark):
        print(f"benchmark bars for {args.benchmark} not in cache ({args.cache}). "
              "Populate the cache via a data provider first (Phase 1).", file=sys.stderr)
        return 2
    bench = store.load(args.benchmark)

    survivors = []
    for sym in args.symbols:
        if not store.has(sym):
            print(f"skip {sym}: not in cache", file=sys.stderr)
            continue
        cand = screen_symbol(sym, store.load(sym), settings, benchmark_df=bench,
                             account_equity=args.equity)
        _print_candidate(cand)
        if cand.passed_gates:
            survivors.append(cand)

    survivors.sort(key=lambda c: c.composite or 0, reverse=True)
    print(f"\n{len(survivors)} survivor(s), ranked by composite:")
    for c in survivors:
        print(f"  {c.composite:.3f}  {c.symbol}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="breakout", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=None, help="path to settings.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="run on a synthetic breakout series")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_demo)

    s = sub.add_parser("screen", help="run on cached bars")
    s.add_argument("symbols", nargs="+")
    s.add_argument("--benchmark", default="SPY")
    s.add_argument("--cache", default="data/cache")
    s.add_argument("--equity", type=float, default=100_000.0)
    s.set_defaults(func=cmd_screen)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
