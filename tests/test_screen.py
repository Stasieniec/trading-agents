import json
from datetime import date, timedelta

import pytest

from trading import screen as sc
from trading.screen import build, industry_moves, outcomes, render, scan, stats
from trading.universe import Universe

DAY = date(2026, 11, 5)  # a Thursday; the screen measures Wednesday 4 Nov


def bars(closes, vols=None, last=None, end=date(2026, 11, 4)):
    n = len(closes)
    out = []
    d = end
    dates = []
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d)
        d -= timedelta(days=1)
    dates.reverse()
    for i, c in enumerate(closes):
        out.append({"date": dates[i].isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c,
                    "v": (vols or [1e6] * n)[i]})
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
    assert stats(bars([100.0] * 30 + [99.0, 98.0, 97.0]))["streak"] == -3


def test_short_history_is_skipped():
    assert stats(bars([100.0] * 10)) is None


def test_industry_median_needs_five_names():
    rows = [{"symbol": f"S{i}", "eligible": True, "industry": "Chips", "sector": "Tech", "name": ""} for i in range(5)]
    rows.append({"symbol": "LONE", "eligible": True, "industry": "Rare", "sector": "Tech", "name": ""})
    uni = Universe(rows, "x")
    moves = {f"S{i}": {"r1": float(i)} for i in range(5)} | {"LONE": {"r1": 10.0}}
    ind = industry_moves(uni, moves)
    assert ind["S0"] == 2.0  # median of 0..4 in Chips
    assert ind["LONE"] == pytest.approx(2.5)  # its industry is too small: the Tech sector's median, itself included


class FakeAlpaca:
    """Calm stocks, one with a no-news spike, one with a heavy-volume drop, all on Wednesday 4 Nov."""
    def __init__(self):
        calm = [50 + (0.2 if i % 2 else -0.2) for i in range(70)]
        self.b = {f"C{i}": bars(calm + [50.1]) for i in range(8)}
        self.b["SPIKE"] = bars(calm + [60.0])
        self.b["DROP"] = bars(calm + [44.0], vols=[1e6] * 70 + [9e6])
        self.b["SPY"] = bars([500.0] * 71)
        self.calls = []

    def daily_bars(self, symbols, start, end, adjustment="raw"):
        self.calls.append(len(symbols))
        return {s: self.b[s] for s in symbols if s in self.b}

    def premarket(self, symbols, day):
        return {"SPIKE": {"price": 57.0, "time": "2026-11-05T13:00:00Z", "volume": 120000.0}}


def uni():
    rows = [{"symbol": s, "name": s, "eligible": True, "market_cap": 5e9, "sector": "Tech", "industry": "Software",
             "shortable": s != "DROP"} for s in [f"C{i}" for i in range(8)] + ["SPIKE", "DROP"]]
    return Universe(rows, "x")


def test_build_ranks_moves_by_their_own_volatility_and_adds_context(monkeypatch):
    monkeypatch.setattr(sc, "fetch_earnings", lambda day, log=print: {"DROP": ["2026-11-04 before open"]})
    a = FakeAlpaca()
    out = build(uni(), a, DAY, {"SPIKE": 0, "DROP": 4}, log=lambda m: None, per_side=1, by_volume=0, by_earnings=0)
    assert out["measured"] == 10
    tickers = [r["ticker"] for r in out["rows"]]
    assert tickers == ["SPIKE", "DROP"]
    spike = out["rows"][0]
    assert spike["pre"] == pytest.approx(57 / 60 * 100 - 100) and spike["pre_volume"] == 120000
    assert spike["vs_industry"] == pytest.approx(spike["r1"] - out["industry_moves"]["SPIKE"], abs=1e-3)
    drop = out["rows"][1]
    assert drop["stories"] == 4 and drop["earnings"] == ["2026-11-04 before open"] and not drop["shortable"]
    text = render(out["rows"])
    assert "SPIKE" in text and "DROP (not shortable)" in text and "2026-11-04 before open" in text
    # Scanning any ticker reuses the screen's industry, news and earnings context.
    (row,) = scan(uni(), a, DAY, ["drop"], out)
    assert row["earnings"] == ["2026-11-04 before open"] and row["stories"] == 4


def test_outcomes_follow_rows_from_the_open_of_the_screen_day():
    class A(FakeAlpaca):
        def daily_bars(self, symbols, start, end, adjustment="raw"):
            # Wed 4 Nov opens at 100 for everything; by the Wed close SPIKE fell to 95, DROP rose to 103.
            row = lambda o, c: [{"date": "2026-11-04", "o": o, "h": o, "l": o, "c": c, "v": 1}]  # noqa: E731
            return {"SPIKE": row(100, 95), "DROP": row(100, 103), "SPY": row(100, 101)}

    def load(d):
        if d == date(2026, 11, 4):
            return {"screen": {"rows": [{"ticker": "SPIKE", "r1": 9.0, "stories": 0, "earnings": []},
                                        {"ticker": "DROP", "r1": -8.0, "stories": 2, "earnings": []}]}}
        return None

    text = outcomes(DAY, A(), load, lookbacks=(1,))
    assert "2026-11-04 (1 session ago) | 1 | up | no | -6.00% | 0 of 1" in text
    assert "2026-11-04 (1 session ago) | 1 | down | yes | +2.00% | 0 of 1" in text
