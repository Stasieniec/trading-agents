"""The marking job end to end against a fake Alpaca, on a temporary copy of the repo layout."""

import json
from datetime import date

import pytest

import trading.market as market
import trading.site as site
from trading.ledger import read_jsonl, replay

D1, D2 = date(2026, 11, 2), date(2026, 11, 3)


class FakeAlpaca:
    def __init__(self):
        self.px = {"2026-10-30": 100.0, "2026-11-02": 101.0, "2026-11-03": 103.0}

    def daily_bars(self, symbols, start, end, adjustment="raw"):
        out = {}
        for s in symbols:
            bars = []
            for d, p in self.px.items():
                if start.isoformat() <= d <= end.isoformat():
                    k = 4.0 if (s == "SPLT" and d >= "2026-11-03") else 1.0  # 4:1 split on Nov 3
                    bars.append({"date": d, "t": d + "T04:00:00Z", "o": p / k, "h": p * 1.01 / k,
                                 "l": p * 0.99 / k, "c": p / k, "v": 1e6})
            out[s] = bars
        return out

    def opening_auctions(self, symbols, start, end):
        return {}

    def corporate_actions(self, symbols, start, end):
        return [{"kind": "forward_splits", "id": "s1", "symbol": "SPLT", "old_rate": 1, "new_rate": 4,
                 "ex_date": "2026-11-03"}] if "SPLT" in symbols else []


@pytest.fixture
def repo(tmp_path, monkeypatch):
    agents = tmp_path / "agents"
    for n in market.AGENTS:
        (agents / n / "ledger").mkdir(parents=True)
    exp = tmp_path / "data" / "experiment.json"
    exp.parent.mkdir(parents=True)
    exp.write_text(json.dumps({"start_date": D1.isoformat()}))
    bench = tmp_path / "data" / "benchmarks"
    for mod in (market, site):
        monkeypatch.setattr(mod, "AGENTS_DIR", agents, raising=False)
    monkeypatch.setattr(market, "EXPERIMENT_FILE", exp)
    monkeypatch.setattr(market, "BENCH_DIR", bench)
    monkeypatch.setattr(market, "SPY_DAILY", bench / "spy-daily.csv")
    monkeypatch.setattr(site, "BENCH_DIR", bench)
    monkeypatch.setattr(site, "SITE_DIR", tmp_path / "site-data")
    monkeypatch.setattr(site, "DATA_DIR", tmp_path / "data")
    return tmp_path


def test_two_days_with_a_split(repo):
    orders = repo / "agents" / "open-quality" / "ledger" / "orders.jsonl"
    orders.write_text(json.dumps({"id": "open-quality-2026-11-02-01", "session_date": "2026-11-02",
                                  "action": "set_weight", "ticker": "SPLT", "target_weight": 0.5,
                                  "stop_pct": 10, "target_pct": 50, "horizon_days": 5, "thesis": "t",
                                  "probability": 0.6, "slippage_bp": 25, "sources": []}) + "\n")
    assert market.run(D2, FakeAlpaca(), log=lambda m: None) == [D1, D2]
    ev = read_jsonl(repo / "agents" / "open-quality" / "ledger" / "events.jsonl")
    st = replay(ev)
    p = st.positions["SPLT"]
    assert p.stop_price == pytest.approx(101 * 0.9 / 4)  # stop rescaled by the split, not triggered
    marks = [e for e in ev if e["type"] == "mark"]
    assert [m["date"] for m in marks] == ["2026-11-02", "2026-11-03"]
    assert marks[-1]["equity"] == pytest.approx(50_000 / 1.0025 * 103 / 101 + 50_000, rel=1e-3)
    spy = replay(read_jsonl(repo / "data" / "benchmarks" / "spy" / "ledger" / "events.jsonl"))
    assert "SPY" in spy.positions
    # Idempotent: a second run changes nothing.
    assert market.run(D2, FakeAlpaca(), log=lambda m: None) == []
    site.build()
    stats = json.loads((repo / "site-data" / "stats.json").read_text())
    assert stats["open-quality"]["days"] == 2
    assert stats["open-quality"]["trades_open"] == 1


class OpenBelowClose(FakeAlpaca):
    def daily_bars(self, symbols, start, end, adjustment="raw"):
        out = super().daily_bars(symbols, start, end, adjustment)
        for bars in out.values():
            for b in bars:
                b["o"] = b["c"] * 0.95
                b["l"] = b["c"] * 0.94
        return out


def test_late_day_one_fills_everything_at_the_close(repo):
    (repo / "data" / "experiment.json").write_text(json.dumps({"start_date": D1.isoformat(), "start_fill": "close"}))
    orders = repo / "agents" / "tech-ten" / "ledger" / "orders.jsonl"
    orders.write_text(json.dumps({"id": "tech-ten-2026-11-02-01", "session_date": "2026-11-02", "fill_at": "close",
                                  "action": "set_weight", "ticker": "NVDA", "target_weight": 0.5, "stop_pct": 3,
                                  "target_pct": 50, "horizon_days": 5, "thesis": "t", "probability": 0.6,
                                  "slippage_bp": 10, "sources": []}) + "\n")
    market.run(D1, OpenBelowClose(), log=lambda m: None)
    fill = [e for e in read_jsonl(repo / "agents" / "tech-ten" / "ledger" / "events.jsonl") if e["type"] == "fill"][0]
    assert fill["ref_price"] == pytest.approx(101.0) and fill["at"] == "close"  # the close, not the 95.95 open
    st = replay(read_jsonl(repo / "agents" / "tech-ten" / "ledger" / "events.jsonl"))
    assert "NVDA" in st.positions  # the day's low under the 3% stop did not trigger: the fill came after it
    spy = [e for e in read_jsonl(repo / "data" / "benchmarks" / "spy" / "ledger" / "events.jsonl") if e["type"] == "fill"][0]
    assert spy["ref_price"] == pytest.approx(101.0)


class WithMinutes(OpenBelowClose):
    def first_minute_open(self, symbols, after):
        assert after.isoformat().startswith("2026-11-02T14:1")
        return {s: 98.0 for s in symbols}


def test_orders_fill_at_the_first_minute_after_the_decision(repo):
    (repo / "data" / "experiment.json").write_text(json.dumps({"start_date": D1.isoformat(),
                                                               "start_fill": "after:2026-11-02T14:16:27Z"}))
    orders = repo / "agents" / "no-news" / "ledger" / "orders.jsonl"
    orders.write_text(json.dumps({"id": "no-news-2026-11-02-01", "session_date": "2026-11-02",
                                  "fill_at": "after:2026-11-02T14:13:48Z", "action": "set_weight", "ticker": "CROX",
                                  "target_weight": 0.07, "stop_pct": 1, "target_pct": 18, "horizon_days": 15,
                                  "thesis": "t", "probability": 0.53, "slippage_bp": 25, "sources": []}) + "\n")
    market.run(D1, WithMinutes(), log=lambda m: None)
    ev = read_jsonl(repo / "agents" / "no-news" / "ledger" / "events.jsonl")
    fill = [e for e in ev if e["type"] == "fill"][0]
    assert fill["ref_price"] == 98.0 and fill["at"].startswith("after:")
    assert "CROX" in replay(ev).positions  # the day's low under the 1% stop did not trigger on the fill day
    spy = [e for e in read_jsonl(repo / "data" / "benchmarks" / "spy" / "ledger" / "events.jsonl") if e["type"] == "fill"][0]
    assert spy["ref_price"] == 98.0
