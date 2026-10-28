from datetime import date

import pytest

from trading.ledger import (State, apply_event, corporate_action_events, exit_events, fill_orders,
                            mark_event, replay)

D1 = date(2026, 11, 2)  # a Monday
D2 = date(2026, 11, 3)


def order(i, ticker, action="set_weight", w=0.5, stop=10, target=20, horizon=5, bp=10):
    return {"id": f"a-{i}", "ticker": ticker, "action": action, "target_weight": w, "stop_pct": stop,
            "target_pct": target, "horizon_days": horizon, "thesis": f"t{i}", "slippage_bp": bp}


def test_buy_sizes_from_equity_at_open_with_slippage():
    s = State()
    ev = fill_orders(s, [order(1, "AAA", w=0.5)], D1, {"AAA": 100.0}, {})
    fill = [e for e in ev if e["type"] == "fill"][0]
    assert fill["price"] == pytest.approx(100.10)
    assert fill["qty"] * fill["price"] == pytest.approx(50_000)
    p = s.positions["AAA"]
    assert p.stop_price == pytest.approx(90.0)
    assert p.target_price == pytest.approx(120.0)
    assert p.horizon_end == "2026-11-09"
    assert s.cash == pytest.approx(50_000)


def test_buys_scaled_when_cash_short_and_sells_first():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.9)], D1, {"AAA": 100.0}, {})
    # Next day: sell AAA down to 0.2, buy BBB at 0.8. Sells settle before buys.
    ev = fill_orders(s, [order(2, "AAA", w=0.2), order(3, "BBB", w=0.8)], D2, {"AAA": 100.0, "BBB": 50.0}, {})
    assert [e["side"] for e in ev if e["type"] == "fill"] == ["sell", "buy"]
    assert s.cash >= -1e-6
    total = s.cash + sum(p.qty * {"AAA": 100.0, "BBB": 50.0}[t] for t, p in s.positions.items())
    assert total == pytest.approx(100_000, rel=0.003)


def test_unnamed_holdings_keep_shares():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.3)], D1, {"AAA": 100.0}, {})
    q = s.positions["AAA"].qty
    fill_orders(s, [order(2, "BBB", w=0.3)], D2, {"AAA": 130.0, "BBB": 10.0}, {})
    assert s.positions["AAA"].qty == q


def test_no_open_price_cancels():
    s = State()
    ev = fill_orders(s, [order(1, "HALT")], D1, {}, {})
    assert ev[0]["type"] == "cancel"
    assert "HALT" not in s.positions


def test_orders_never_fill_twice():
    s = State()
    o = order(1, "AAA")
    fill_orders(s, [o], D1, {"AAA": 100.0}, {})
    assert fill_orders(s, [o], D1, {"AAA": 100.0}, {}) == []


def test_stop_beats_target_same_day_and_gap_fills_at_open():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.5), order(2, "BBB", w=0.4)], D1, {"AAA": 100.0, "BBB": 100.0}, {})
    ev = exit_events(s, D2, {"AAA": {"o": 101, "h": 125, "l": 85, "c": 100},   # both touched: stop
                             "BBB": {"o": 80, "h": 82, "l": 78, "c": 81}})     # gapped through the stop
    by = {e["ticker"]: e for e in ev}
    assert by["AAA"]["reason"] == "stop" and by["AAA"]["ref_price"] == pytest.approx(90.0)
    assert by["BBB"]["reason"].startswith("stop (gapped") and by["BBB"]["ref_price"] == 80
    assert not s.positions


def test_target_exit():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.5)], D1, {"AAA": 100.0}, {})
    ev = exit_events(s, D2, {"AAA": {"o": 105, "h": 121, "l": 104, "c": 120}})
    assert ev[0]["reason"] == "target" and ev[0]["ref_price"] == pytest.approx(120.0)


def test_split_adjusts_shares_and_levels_before_stops():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.5)], D1, {"AAA": 100.0}, {})
    q = s.positions["AAA"].qty
    acts = [{"kind": "forward_splits", "id": "x1", "symbol": "AAA", "old_rate": 1, "new_rate": 4, "ex_date": "2026-11-03"}]
    corporate_action_events(s, acts, D2)
    p = s.positions["AAA"]
    assert p.qty == pytest.approx(q * 4)
    assert p.stop_price == pytest.approx(22.5)
    # post-split bar must not trip a stop
    assert exit_events(s, D2, {"AAA": {"o": 25, "h": 26, "l": 24, "c": 25.5}}) == []
    # applied once only
    assert corporate_action_events(s, acts, D2) == []


def test_dividend_credited_on_ex_date():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.5)], D1, {"AAA": 100.0}, {})
    cash = s.cash
    q = s.positions["AAA"].qty
    corporate_action_events(s, [{"kind": "cash_dividends", "id": "d1", "symbol": "AAA", "rate": 0.5,
                                 "ex_date": "2026-11-03"}], D2)
    assert s.cash == pytest.approx(cash + 0.5 * q)


def test_close_and_extend():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.5), order(2, "BBB", w=0.3)], D1, {"AAA": 100.0, "BBB": 50.0}, {})
    fill_orders(s, [order(3, "AAA", action="close"),
                    {**order(4, "BBB", action="extend", stop=5, target=50, horizon=10), "thesis": "new"}],
                D2, {"AAA": 110.0, "BBB": 60.0}, {})
    assert "AAA" not in s.positions
    b = s.positions["BBB"]
    assert b.thesis == "new" and b.original_thesis == "t2" and b.extensions == 1
    assert b.stop_price == pytest.approx(57.0)


def test_replay_matches_live_state():
    s = State()
    events = []
    events += fill_orders(s, [order(1, "AAA", w=0.5)], D1, {"AAA": 100.0}, {})
    events.append(mark_event(s, D1, {"AAA": 101.0}))
    events += exit_events(s, D2, {"AAA": {"o": 100, "h": 101, "l": 89, "c": 95}})
    events.append(mark_event(s, D2, {}))
    r = replay(events)
    assert r.cash == pytest.approx(s.cash)
    assert r.positions.keys() == s.positions.keys()
    assert r.last_marked == "2026-11-03"


def test_benchmark_orders_without_plan():
    s = State()
    fill_orders(s, [{"id": "b-1", "ticker": "SPY", "action": "set_weight", "target_weight": 1.0,
                     "slippage_bp": 10}], D1, {"SPY": 500.0}, {})
    assert s.positions["SPY"].stop_price is None
    assert exit_events(s, D2, {"SPY": {"o": 1, "h": 1, "l": 1, "c": 1}}) == []


def test_actions_dated_before_or_on_the_buy_are_not_applied():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.5)], D2, {"AAA": 25.0}, {})  # bought on the split's ex-date
    q, stop = s.positions["AAA"].qty, s.positions["AAA"].stop_price
    cash = s.cash
    acts = [{"kind": "forward_splits", "id": "s1", "symbol": "AAA", "old_rate": 1, "new_rate": 4, "ex_date": "2026-11-03"},
            {"kind": "cash_dividends", "id": "d1", "symbol": "AAA", "rate": 1.0, "ex_date": "2026-11-02"}]
    ev = corporate_action_events(s, acts, date(2026, 11, 4))
    assert [e["type"] for e in ev] == ["noop_action", "noop_action"]
    assert s.positions["AAA"].qty == q and s.positions["AAA"].stop_price == stop and s.cash == cash
    assert corporate_action_events(s, acts, date(2026, 11, 5)) == []
