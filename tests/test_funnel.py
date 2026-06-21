
from breakout.config import Settings
from breakout.screen.funnel import screen_symbol
from breakout.screen.l5_group import GroupContext
from breakout.screen.l6_catalyst import CatalystContext
from breakout.synthetic import make_benchmark, make_breakout_series


def _settings():
    return Settings.load()


def test_clean_breakout_passes_all_gates():
    s = _settings()
    cand = screen_symbol("DEMO", make_breakout_series(), s, benchmark_df=make_benchmark())
    assert cand.passed_gates, f"rejected at {cand.rejected_at}"
    assert cand.composite is not None
    assert cand.risk is not None
    assert cand.risk.shares > 0
    assert cand.risk.stop < cand.risk.entry


def test_bear_regime_blocks_signal():
    s = _settings()
    bench = make_benchmark()
    bench["close"] = bench["close"].iloc[0]  # flat/declining -> not above rising 200d MA
    bench["high"] = bench["close"] * 1.001
    bench["low"] = bench["close"] * 0.999
    cand = screen_symbol("DEMO", make_breakout_series(), s, benchmark_df=bench)
    assert not cand.passed_gates
    assert cand.rejected_at == "L1_regime"


def test_no_breakout_rejected_at_trigger():
    s = _settings()
    df = make_breakout_series()
    # Nudge the last close just above the prior high but inside the volatility buffer: still at
    # the highs (L2 passes) but no meaningful penetration -> L4 trigger must fail.
    prior_high = df["close"].iloc[:-1].max()
    df.iloc[-1, df.columns.get_loc("close")] = prior_high * 1.001
    df.iloc[-1, df.columns.get_loc("high")] = prior_high * 1.002
    cand = screen_symbol("DEMO", df, s, benchmark_df=make_benchmark())
    assert not cand.passed_gates
    assert cand.rejected_at == "L4_trigger"


def test_liquidity_gate_blocks_penny_stock():
    s = _settings()
    df = make_breakout_series()
    df[["open", "high", "low", "close"]] *= 0.05  # push price below min_price
    cand = screen_symbol("PENNY", df, s, benchmark_df=make_benchmark())
    assert not cand.passed_gates
    assert cand.rejected_at == "L0_universe"


def test_catalyst_and_group_raise_composite():
    s = _settings()
    bench, df = make_benchmark(), make_breakout_series()
    base = screen_symbol("DEMO", df, s, benchmark_df=bench)

    boosted = screen_symbol(
        "DEMO", df, s, benchmark_df=bench,
        group_ctx=GroupContext(group_rs_rising=True, leader_rank_pct=0.95,
                               peers_already_extended_pct=0.1, group_name="AI"),
        catalyst_ctx=CatalystContext(catalyst_present=True, durability=0.9, novelty=0.8,
                                     confidence=0.9, attention_z=2.5, catalyst_type="demand_surge"),
    )
    assert boosted.composite > base.composite


def test_score_layers_bounded():
    s = _settings()
    cand = screen_symbol("DEMO", make_breakout_series(), s, benchmark_df=make_benchmark())
    for lr in cand.layers:
        if lr.kind == "score" and lr.score is not None:
            assert 0.0 <= lr.score <= 1.0
