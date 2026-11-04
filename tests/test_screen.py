from datetime import date, timedelta

import pytest

from trading.screen import candidates, render, scan, stats
from trading.universe import Universe


def bars(closes, vols=None, last=None):
    d0 = date(2026, 1, 1)
    out = []
    for i, c in enumerate(closes):
        out.append({"date": (d0 + timedelta(days=i)).isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c,
                    "v": (vols or [1e6] * len(closes))[i]})
    if last:
        out[-1].update(last)
    return out


def test_a_spike_on_heavy_volume_stands_out():
    closes = [100 + (1 if i % 2 else -1) * 0.5 for i in range(80)] + [120.0]
    vols = [1e6] * 80 + [5e6]
    s = stats(bars(closes, vols, last={"o": 115.0, "h": 121.0, "l": 114.0}))
    assert s["r1"] == pytest.approx(120 / closes[-2] * 100 - 100)
    assert s["z"] > 10  # ~19% against roughly 1% daily moves
    assert s["vol_x"] == pytest.approx(5.0)
    assert s["gap"] == pytest.approx(115 / closes[-2] * 100 - 100)
    assert s["range_pos"] == pytest.approx((120 - 114) / 7)
    assert s["from_high"] == pytest.approx(120 / 121 * 100 - 100)
    assert s["streak"] == 2  # 99.5 -> 100.5 -> 120


def test_streak_counts_consecutive_down_closes():
    closes = [100.0] * 30 + [99.0, 98.0, 97.0]
    assert stats(bars(closes))["streak"] == -3


def test_short_history_is_skipped():
    assert stats(bars([100.0] * 10)) is None


def test_candidates_are_the_biggest_eligible_moves():
    rows = [{"symbol": s, "eligible": e, "pct_change": p, "name": s, "sector": "", "industry": ""}
            for s, e, p in [("UP", True, 30.0), ("DN", True, -25.0), ("PNY", False, 90.0), ("FLAT", True, 0.0)]]
    assert candidates(Universe(rows, "x"), top=1) == ["UP", "DN"]


class FakeAlpaca:
    def daily_bars(self, symbols, start, end, adjustment="raw"):
        today = end.isoformat()
        b = bars([50.0] * 40 + [55.0])
        b.append({"date": today, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1})  # today's pre-market bar: ignored
        return {s: b for s in symbols}

    def latest_trades(self, symbols):
        return {"ABC": {"p": 57.75, "t": "2026-11-05T12:00:00Z"}}


def test_scan_uses_finished_sessions_and_the_pre_market_trade():
    uni = Universe([{"symbol": "ABC", "name": "Abc", "eligible": True, "pct_change": 10.0, "market_cap": 5e9,
                     "sector": "", "industry": "", "shortable": True}], "x")
    (r,) = scan(uni, FakeAlpaca(), date(2026, 11, 5), ["abc"], [{"symbol": "ABC", "stories": 3}])
    assert r["close"] == 55.0 and r["pre"] == pytest.approx(5.0) and r["headlines"] == 3
    text = render([r])
    assert "ABC" in text and "$5.0B" in text and "(not shortable)" not in text
