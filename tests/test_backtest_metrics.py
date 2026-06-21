from breakout.backtest.metrics import Trade, summarize


def test_r_multiple():
    t = Trade(symbol="X", entry=100, stop=95, exit=110)
    assert t.r_multiple == 2.0
    assert t.is_win


def test_summarize_expectancy():
    trades = [
        Trade("A", 100, 95, 110),   # +2R
        Trade("B", 100, 95, 105),   # +1R
        Trade("C", 100, 95, 95),    # -1R
        Trade("D", 100, 95, 95),    # -1R
    ]
    m = summarize(trades)
    assert m["n"] == 4
    assert m["win_rate"] == 0.5
    assert m["expectancy_r"] == 0.25
    assert m["profit_factor"] == 1.5


def test_summarize_empty():
    assert summarize([]) == {"n": 0}
