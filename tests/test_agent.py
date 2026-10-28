from datetime import date
from pathlib import Path

import pytest

from trading.agent.memory import Memory, MemoryError_
from trading.agent.urls import norm
from trading.agent.validate import Context, validate
from trading.config import AGENTS
from trading.ledger import State, fill_orders
from trading.universe import Universe

ROWS = [
    {"symbol": "BIG", "name": "Big Corp Common Stock", "price": 100, "market_cap": 50e9, "sector": "Tech",
     "industry": "Software", "eligible": True, "reasons": [], "bucket": "large"},
    {"symbol": "SML", "name": "Small Potato Farms Inc.", "price": 20, "market_cap": 800e6, "sector": "Food",
     "industry": "Farming", "eligible": True, "reasons": [], "bucket": "small"},
    {"symbol": "PNY", "name": "Penny Co", "price": 2, "market_cap": 50e6, "sector": "X", "industry": "Y",
     "eligible": False, "reasons": ["price under $5"], "bucket": "small"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation Common Stock", "price": 180, "market_cap": 4e12, "sector": "Tech",
     "industry": "Chips", "eligible": True, "reasons": [], "bucket": "large"},
]
URL = "https://example.com/story"


def buy(t, w=0.2, **kw):
    o = {"action": "set_weight", "ticker": t, "target_weight": w, "thesis": "because", "horizon_days": 10,
         "stop_pct": 8, "target_pct": 15, "probability": 0.55, "sources": [URL], "causal_chain": []}
    o.update(kw)
    return o


def ctx(agent="open-quality", state=None, **kw):
    c = Context(agent=AGENTS[agent], universe=Universe(ROWS, "2026-11-02"), state=state or State(), closes={},
                session_date="2026-11-02", read_ok_urls={norm(URL)}, seen_urls=set())
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_valid_buy_gets_size_based_slippage():
    ok, err = validate([buy("BIG"), buy("SML")], ctx())
    assert not err
    assert {o["ticker"]: o["slippage_bp"] for o in ok} == {"BIG": 10, "SML": 50}


def test_ineligible_and_unknown_rejected():
    ok, err = validate([buy("PNY"), buy("ZZZZ")], ctx())
    assert not ok and len(err) == 2


def test_buy_needs_a_page_read_this_session():
    ok, err = validate([buy("BIG", sources=["https://other.com/x"])], ctx())
    assert not ok and "read_page" in err[0]


def test_url_normalisation():
    assert norm("https://www.Example.com/story/?utm_source=x") == norm(URL)


def test_no_news_agent_needs_no_sources():
    ok, err = validate([buy("BIG", sources=[])], ctx("no-news"))
    assert ok and not err


def test_tech_ten_only():
    ok, err = validate([buy("BIG"), buy("NVDA")], ctx("tech-ten"))
    assert [o["ticker"] for o in ok] == ["NVDA"] and len(err) == 1


def test_weights_over_one_rejected():
    ok, err = validate([buy("BIG", w=0.7), buy("SML", w=0.5)], ctx())
    assert not ok and any("invested" in e for e in err)


def test_weird_links_rejects_headline_names_and_short_chains():
    chain = [{"step": "storm hits farms", "source_url": URL}, {"step": "supply drops", "source_url": URL}]
    c = ctx("weird-links", headline_text="Small Potato Farms flooded after storm")
    ok, err = validate([buy("SML", causal_chain=chain)], c)
    assert not ok and "named in today's digest" in err[0]
    ok, err = validate([buy("BIG", causal_chain=chain[:1])], c)
    assert not ok and "causal chain" in err[0]
    ok, err = validate([buy("BIG", causal_chain=chain)], c)
    assert ok and not err


def test_expired_positions_need_an_answer():
    s = State()
    fill_orders(s, [{"id": "x", "ticker": "BIG", "action": "set_weight", "target_weight": 0.3, "stop_pct": 5,
                     "target_pct": 5, "horizon_days": 1, "thesis": "t", "slippage_bp": 10}],
                date(2026, 11, 2), {"BIG": 100.0}, {})
    c = ctx(state=s, closes={"BIG": 100.0}, expired={"BIG"})
    ok, err = validate([], c)
    assert any("passed their horizon" in e for e in err)
    ok, err = validate([{"action": "close", "ticker": "BIG"}], c)
    assert ok and not err


def test_memory_paths_are_confined(tmp_path: Path):
    m = Memory(tmp_path / "agent")
    for bad in ["../../trading/tools", "../x", "notes/../../y", "a b", ""]:
        with pytest.raises(MemoryError_):
            m._path(bad)
    m.update_ticker("brk.b", "cheap insurance float", "first look", "2026-11-02")
    assert (tmp_path / "agent" / "memory" / "tickers" / "BRK.B.md").exists()


def test_memory_caps_and_log_trim(tmp_path: Path):
    m = Memory(tmp_path / "agent")
    with pytest.raises(MemoryError_):
        m.write_notes("word " * 2100)
    for i in range(20):
        m.update_ticker("ABC", "view", f"entry {i}", f"2026-11-{i + 1:02d}")
    text = (tmp_path / "agent" / "memory" / "tickers" / "ABC.md").read_text()
    assert "entry 19" in text and "entry 4" not in text
    assert (tmp_path / "agent" / "memory" / "tickers" / "archive" / "ABC.md").exists()
