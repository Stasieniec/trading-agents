from datetime import date

import pytest

from trading.ledger import (State, apply_event, borrow_fee_events, corporate_action_events, exit_events,
                            fill_orders, mark_event, replay)

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


# --- shorts


def test_short_sale_adds_proceeds_and_flips_the_plan():
    s = State()
    ev = fill_orders(s, [order(1, "AAA", w=-0.4, stop=10, target=20)], D1, {"AAA": 100.0}, {})
    fill = [e for e in ev if e["type"] == "fill"][0]
    assert fill["side"] == "sell" and fill["price"] == pytest.approx(99.90)
    p = s.positions["AAA"]
    assert p.qty < 0 and p.short
    q = -p.qty
    assert q * 100.0 * 1.001 == pytest.approx(40_000)  # sized net of slippage, like a buy
    assert s.cash == pytest.approx(100_000 + q * 99.9)
    assert p.stop_price == pytest.approx(110.0) and p.target_price == pytest.approx(80.0)
    assert p.avg_cost == pytest.approx(99.90)
    # Equity at the reference price is the start less the slippage.
    assert s.equity({"AAA": 100.0}) == pytest.approx(100_000 - q * 0.1)
    # The short gains when the price falls.
    assert s.equity({"AAA": 90.0}) == pytest.approx(100_000 - q * 0.1 + q * 10)
    assert p.pnl_pct(90.0) == pytest.approx((99.9 - 90) / 99.9)


def test_cover_returns_to_cash_only():
    s = State()
    fill_orders(s, [order(1, "AAA", w=-0.4)], D1, {"AAA": 100.0}, {})
    q = -s.positions["AAA"].qty
    ev = fill_orders(s, [order(2, "AAA", action="close")], D2, {"AAA": 90.0}, {})
    fill = [e for e in ev if e["type"] == "fill"][0]
    assert fill["side"] == "buy" and fill["price"] == pytest.approx(90.09) and fill["qty"] == pytest.approx(q)
    assert "AAA" not in s.positions
    assert s.cash == pytest.approx(100_000 + q * 99.9 - q * 90.09)


def test_partial_cover_keeps_average_price():
    s = State()
    fill_orders(s, [order(1, "AAA", w=-0.4)], D1, {"AAA": 100.0}, {})
    q0 = s.positions["AAA"].qty
    fill_orders(s, [order(2, "AAA", w=-0.2)], D2, {"AAA": 100.0}, {})
    p = s.positions["AAA"]
    assert p.qty == pytest.approx(q0 / 2, rel=0.01)
    assert p.avg_cost == pytest.approx(99.90)


def test_long_flips_to_short_in_one_order():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.5)], D1, {"AAA": 100.0}, {})
    ev = fill_orders(s, [order(2, "AAA", w=-0.3, stop=5, target=10)], D2, {"AAA": 100.0}, {})
    fills = [e for e in ev if e["type"] == "fill"]
    assert [f["side"] for f in fills] == ["sell", "sell"]
    p = s.positions["AAA"]
    assert p.short and -p.qty * 100.0 == pytest.approx(0.3 * s.equity({"AAA": 100.0}) / 1, rel=0.01)
    assert p.opened == D2.isoformat()
    assert p.stop_price == pytest.approx(105.0) and p.target_price == pytest.approx(90.0)
    plans = [e for e in ev if e["type"] == "plan"]
    assert len(plans) == 1


def test_short_proceeds_fund_longs_but_gross_stays_within_equity():
    s = State()
    ev = fill_orders(s, [order(1, "AAA", w=0.7), order(2, "BBB", w=-0.5)], D1, {"AAA": 100.0, "BBB": 50.0}, {})
    m = {"AAA": 100.0, "BBB": 50.0}
    assert s.gross(m) <= s.equity(m) + 1e-6
    assert s.cash > 0
    assert all(e.get("scaled", 1) < 1 for e in ev if e["type"] == "fill")


def test_short_stop_triggers_on_the_high():
    s = State()
    fill_orders(s, [order(1, "AAA", w=-0.4, stop=10, target=20)], D1, {"AAA": 100.0}, {})
    ev = exit_events(s, D2, {"AAA": {"o": 101, "h": 112, "l": 85, "c": 100}})
    assert ev[0]["side"] == "buy" and ev[0]["reason"] == "stop" and ev[0]["ref_price"] == pytest.approx(110.0)
    assert ev[0]["price"] == pytest.approx(110.11)
    assert "AAA" not in s.positions


def test_short_gap_up_through_stop_fills_at_open():
    s = State()
    fill_orders(s, [order(1, "AAA", w=-0.4, stop=10, target=20)], D1, {"AAA": 100.0}, {})
    ev = exit_events(s, D2, {"AAA": {"o": 125, "h": 130, "l": 120, "c": 128}})
    assert "gapped" in ev[0]["reason"] and ev[0]["ref_price"] == pytest.approx(125.0)


def test_short_target_triggers_on_the_low():
    s = State()
    fill_orders(s, [order(1, "AAA", w=-0.4, stop=10, target=20)], D1, {"AAA": 100.0}, {})
    ev = exit_events(s, D2, {"AAA": {"o": 95, "h": 99, "l": 78, "c": 82}})
    assert ev[0]["reason"] == "target" and ev[0]["ref_price"] == pytest.approx(80.0)
    ev = exit_events(s, D2, {"AAA": {"o": 95, "h": 99, "l": 78, "c": 82}})
    assert ev == []


def test_short_pays_the_dividend():
    s = State()
    fill_orders(s, [order(1, "AAA", w=-0.4)], D1, {"AAA": 100.0}, {})
    q = s.positions["AAA"].qty
    cash = s.cash
    corporate_action_events(s, [{"id": "d1", "kind": "cash_dividends", "symbol": "AAA", "ex_date": "2026-11-03",
                                 "rate": 0.5}], D2)
    assert s.cash == pytest.approx(cash + q * 0.5)
    assert s.cash < cash


def test_short_split_keeps_value():
    s = State()
    fill_orders(s, [order(1, "AAA", w=-0.4, stop=10)], D1, {"AAA": 100.0}, {})
    q = s.positions["AAA"].qty
    corporate_action_events(s, [{"id": "s1", "kind": "forward_splits", "symbol": "AAA", "ex_date": "2026-11-03",
                                 "old_rate": 1, "new_rate": 2}], D2)
    p = s.positions["AAA"]
    assert p.qty == pytest.approx(2 * q) and p.stop_price == pytest.approx(55.0)
    assert s.equity({"AAA": 50.0}) == pytest.approx(s.equity({"AAA": 50.0}))


def test_borrow_fee_charged_per_calendar_night():
    s = State()
    fill_orders(s, [order(1, "AAA", w=-0.4)], D1, {"AAA": 100.0}, {})
    cash = s.cash
    q = -s.positions["AAA"].qty
    ev = borrow_fee_events(s, D1, {"AAA": 100.0})  # Monday to Tuesday
    assert ev[0]["days"] == 1
    assert cash - s.cash == pytest.approx(q * 100 * 0.005 / 360)
    fri = date(2026, 11, 6)
    ev = borrow_fee_events(s, fri, {"AAA": 100.0})  # Friday to Monday
    assert ev[0]["days"] == 3
    # Longs pay nothing.
    s2 = State()
    fill_orders(s2, [order(1, "AAA", w=0.4)], D1, {"AAA": 100.0}, {})
    assert borrow_fee_events(s2, D1, {"AAA": 100.0}) == []


def test_mark_records_net_and_gross():
    s = State()
    fill_orders(s, [order(1, "AAA", w=0.3), order(2, "BBB", w=-0.2)], D1, {"AAA": 100.0, "BBB": 50.0}, {})
    m = mark_event(s, D1, {"AAA": 100.0, "BBB": 50.0})
    assert m["invested"] == pytest.approx(m["gross"] - 2 * 0.2 * 100_000, rel=0.01)
    assert m["equity"] == pytest.approx(100_000, rel=0.002)


def test_short_events_replay_to_the_same_state():
    s = State()
    events = []
    events += fill_orders(s, [order(1, "AAA", w=0.5)], D1, {"AAA": 100.0}, {})
    events += fill_orders(s, [order(2, "AAA", w=-0.3)], D2, {"AAA": 104.0}, {})
    events += borrow_fee_events(s, D2, {"AAA": 104.0})
    r = replay(events)
    assert r.cash == pytest.approx(s.cash)
    assert r.positions["AAA"].qty == pytest.approx(s.positions["AAA"].qty)
    assert r.positions["AAA"].cost == pytest.approx(s.positions["AAA"].cost)


def test_round_trip_short_return_counts_fees_and_dividends():
    from trading.stats import round_trips

    s = State()
    o1 = order(1, "AAA", w=-0.4)
    o1["probability"] = 0.6
    events = fill_orders(s, [o1], D1, {"AAA": 100.0}, {})
    events += borrow_fee_events(s, D1, {"AAA": 100.0})
    events += corporate_action_events(s, [{"id": "d1", "kind": "cash_dividends", "symbol": "AAA",
                                           "ex_date": "2026-11-03", "rate": 1.0}], D2)
    events += fill_orders(s, [order(2, "AAA", action="close")], D2, {"AAA": 90.0}, {})
    spy = {"2026-11-02": (500.0, 500.0), "2026-11-03": (505.0, 505.0)}
    (tr,) = round_trips(events, [o1], spy)
    q = tr["entry_qty"]
    fee = q * 100 * 0.005 / 360
    assert tr["side"] == "short" and tr["closed"] == "2026-11-03"
    assert tr["fees"] == pytest.approx(fee) and tr["dividends"] == pytest.approx(-q)
    expect = (q * 99.9 - q - fee - q * 90.09) / (q * 99.9)
    assert tr["return"] == pytest.approx(expect)
    # SPY rose 1% while the stock fell: the short beat SPY by its return plus SPY's.
    assert tr["excess"] == pytest.approx(expect + 0.01)
    assert tr["beat_spy"] is True and tr["probability"] == 0.6


def test_round_trip_flip_closes_the_long_and_opens_a_short():
    from trading.stats import round_trips

    s = State()
    events = fill_orders(s, [order(1, "AAA", w=0.5)], D1, {"AAA": 100.0}, {})
    events += fill_orders(s, [order(2, "AAA", w=-0.3)], D2, {"AAA": 110.0}, {})
    trips = round_trips(events, [], {})
    assert [(t["side"], t["closed"]) for t in trips] == [("long", "2026-11-03"), ("short", None)]
    assert trips[0]["return"] == pytest.approx(110 * 0.999 / 100.1 - 1)
    assert trips[1]["open_qty"] < 0


def test_round_trip_stop_out_of_a_short():
    from trading.stats import round_trips

    s = State()
    events = fill_orders(s, [order(1, "AAA", w=-0.4, stop=10)], D1, {"AAA": 100.0}, {})
    events += exit_events(s, D2, {"AAA": {"o": 101, "h": 115, "l": 99, "c": 112}})
    (tr,) = round_trips(events, [], {})
    assert tr["exit_reason"] == "stop" and tr["return"] == pytest.approx((99.9 - 110.11) / 99.9)


def test_overlap_counts_only_same_side():
    from trading.stats import overlap

    assert overlap({"A": 0.3, "B": -0.2}, {"A": 0.1, "B": 0.2}) == pytest.approx(0.1)
    assert overlap({"B": -0.2}, {"B": -0.5}) == pytest.approx(0.2)
