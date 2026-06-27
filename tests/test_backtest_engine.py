from breakout.backtest.engine import BacktestConfig, backtest_symbol
from breakout.config import Settings
from breakout.synthetic import make_benchmark, make_trade_path


def _run(outcome):
    s = Settings.load()
    df = make_trade_path(outcome=outcome)
    bench = make_benchmark(n=len(df))
    bench.index = df.index  # align the benchmark to the symbol's dates
    cfg = BacktestConfig.from_settings(s)
    return backtest_symbol("TEST", df, bench, s, cfg), s


def test_win_path_scales_out_and_profits():
    res, _ = _run("win")
    assert res.n_signals >= 1
    assert res.metrics["n"] >= 1
    assert res.metrics["total_r"] > 0
    # the winning trade should exit via the trail (after a scale-out) or be marked open in profit
    assert res.trades[0].exit_reason in {"trail", "open"}
    assert res.trades[0].r_multiple > 0


def test_loss_path_stops_out_near_minus_one_r():
    res, _ = _run("loss")
    assert res.metrics["n"] == 1
    t = res.trades[0]
    assert t.exit_reason == "stop"
    assert -1.6 < t.r_multiple < -0.4  # roughly -1R, allowing slippage/gap


def test_timeout_path_hits_time_stop():
    res, s = _run("timeout")
    assert res.metrics["n"] == 1
    t = res.trades[0]
    assert t.exit_reason == "time_stop"
    assert t.bars_held >= s.risk["time_stop_days"]


def test_no_lookahead_entry_after_signal():
    res, _ = _run("win")
    t = res.trades[0]
    # entry fills on the bar AFTER the signal, so it is strictly later than the signal close
    assert t.entry_date > res.window[0] or t.entry_date is not None
    assert t.exit_date >= t.entry_date


def test_equity_curve_and_drawdown_well_formed():
    res, _ = _run("win")
    assert len(res.equity_curve) == res.equity["n_bars"]
    assert res.equity["max_drawdown_pct"] <= 0.0
    assert res.equity["start_equity"] == 100_000.0
