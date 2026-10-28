"""Which cron firings run, the page reader's success detection, and the digest's filtering."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

import trading.__main__ as cli
from trading import digest
from trading.agent.tools import ToolBox
from trading.config import AGENTS
from trading.ledger import State


def gate(monkeypatch, tmp_path, when: str, done=False, start=date(2026, 10, 29)):
    out = tmp_path / "out"
    out.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(cli, "now_utc", lambda: datetime.fromisoformat(when).replace(tzinfo=timezone.utc))
    monkeypatch.setattr(cli, "experiment_start", lambda: start)
    monkeypatch.setattr(cli, "session_done", lambda n, d: done)
    cli.cmd_gate_session(None)
    return dict(line.split("=", 1) for line in out.read_text().split())


@pytest.mark.parametrize("when,expect", [
    # 29 Oct 2026: Amsterdam on winter time, New York still on summer time, open 13:30 UTC
    ("2026-10-29T11:37:00", "false"),   # 12:37 Amsterdam, too early
    ("2026-10-29T12:32:00", "true"),
    ("2026-10-29T12:37:00", "true"),
    ("2026-10-29T12:44:00", "true"),
    ("2026-10-29T12:52:00", "true"),
    ("2026-10-29T13:07:00", "false"),   # 23 minutes to the open
    # December: both on winter time, open 14:30 UTC
    ("2026-12-01T11:37:00", "false"),
    ("2026-12-01T12:37:00", "true"),
    ("2026-12-01T13:07:00", "true"),
    # June: both on summer time, open 13:30 UTC, 11:37 UTC is 13:37 Amsterdam
    ("2027-06-15T11:37:00", "true"),
    ("2027-06-15T13:07:00", "false"),
    # March mismatch week: New York on summer time, Amsterdam not yet
    ("2027-03-16T12:37:00", "true"),
    # no session on a weekend or a holiday
    ("2026-10-31T12:37:00", "false"),
    ("2026-11-26T12:37:00", "false"),   # Thanksgiving
])
def test_gate_timing(monkeypatch, tmp_path, when, expect):
    assert gate(monkeypatch, tmp_path, when)["run"] == expect


def test_gate_respects_start_date_and_completed_sessions(monkeypatch, tmp_path):
    assert gate(monkeypatch, tmp_path, "2026-10-28T12:37:00")["run"] == "false"  # before the start date
    assert gate(monkeypatch, tmp_path, "2026-10-29T12:37:00", done=True)["run"] == "false"
    assert gate(monkeypatch, tmp_path, "2026-10-29T12:37:00", start=None)["run"] == "false"
    assert gate(monkeypatch, tmp_path, "2026-10-29T12:37:00")["day"] == "2026-10-29"


class O(SimpleNamespace):
    pass


class HaikuFake:
    """Answers read_page calls: scripted blocks and usage."""

    def __init__(self, blocks, fetches=1, inp=8000):
        self.blocks, self.fetches, self.inp = blocks, fetches, inp
        self.calls = 0

    @property
    def messages(self):
        return self

    def with_options(self, **kw):
        return self

    def create(self, **kw):
        self.calls += 1
        return O(stop_reason="end_turn", content=self.blocks,
                 usage=O(input_tokens=self.inp, output_tokens=200, cache_read_input_tokens=0,
                         cache_creation_input_tokens=0,
                         server_tool_use=O(web_fetch_requests=self.fetches, web_search_requests=0)))


def toolbox(client):
    costs = []
    tb = ToolBox(AGENTS["open-quality"], date(2026, 11, 2), None, None, None, State(), {}, client,
                 lambda m, u, w: costs.append(w), print)
    return tb, costs


def test_read_page_success_is_recorded_for_citations():
    fetched = O(type="web_fetch_tool_result", content=O(type="web_fetch_result", error_code=None))
    tb, costs = toolbox(HaikuFake([fetched, O(type="text", text="PAGE DATE: 28 Oct 2026\nOrders doubled.")]))
    out, err = tb.run("read_page", {"url": "https://www.example.com/a?utm_source=x", "question": "what?"})
    assert not err and "Orders doubled" in out
    assert "https://example.com/a" in tb.read_ok_urls and costs == ["read_page"]


def test_read_page_failure_is_not_citable():
    failed = O(type="web_fetch_tool_result", content=O(type="web_fetch_tool_result_error", error_code="url_not_accessible"))
    tb, _ = toolbox(HaikuFake([failed, O(type="text", text="FETCH FAILED")], fetches=1, inp=900))
    out, err = tb.run("read_page", {"url": "https://example.com/b", "question": "q"})
    assert "Could not fetch" in out and not tb.read_ok_urls


def test_read_page_rejects_non_http_and_caps_calls():
    tb, _ = toolbox(HaikuFake([O(type="text", text="x")]))
    out, err = tb.run("read_page", {"url": "file:///etc/passwd", "question": "q"})
    assert err
    tb.read_calls = 10
    out, err = tb.run("read_page", {"url": "https://example.com", "question": "q"})
    assert err and "limit" in out


def test_unknown_tool_and_crashing_tool_return_errors_without_detail():
    tb, _ = toolbox(HaikuFake([]))
    assert tb.run("rm_rf", {}) == ("unknown tool rm_rf", True)
    out, err = tb.run("get_quotes", {"tickers": ["X"]})  # alpaca is None: AttributeError inside
    assert err and out == "tool failed: AttributeError"


def test_digest_drops_wire_noise_and_merges_duplicates():
    items = [
        {"title": "Barclays Maintains Overweight on Visa, Raises Price Target to $440", "source": "benzinga",
         "time": "2026-10-28T16:00:00Z", "url": "u1", "line": "", "symbols": ["V"]},
        {"title": "Vertiv orders more than double as AI spending surges", "source": "benzinga",
         "time": "2026-10-28T15:00:00Z", "url": "u2", "line": "", "symbols": ["VRT"]},
        {"title": "Vertiv orders more than double as AI data center spending surges", "source": "CNBC",
         "time": "2026-10-28T15:30:00Z", "url": "u3", "line": "", "symbols": []},
    ]
    kept = [i for i in items if not digest.NOISE.search(i["title"])]
    out = digest._cluster(kept, {"VRT": 5}, 15)
    assert len(out) == 1 and out[0]["sources"] == ["CNBC", "benzinga"]


def test_price_only_digest_has_no_headlines():
    d = {"date": "2026-11-02", "built_at": "2026-11-02T12:40:00+00:00", "previous_session": "2026-10-30",
         "sources": {}, "etfs": [{"symbol": "SPY", "name": "S&P 500", "close": 700.0, "day_pct": 0.5, "week_pct": 1.0}],
         "movers": {"gainers": [{"symbol": "AAA", "pct": 9.0}], "losers": []}, "most_actives": [],
         "headlines": [{"title": "SECRET HEADLINE", "sources": ["CNBC"], "time": "t", "url": "u", "line": "", "symbols": []}],
         "news_mentions": [{"symbol": "AAA", "stories": 3}], "summary": "summary text"}
    price_only = digest.render(d, news=False)
    assert "SECRET HEADLINE" not in price_only and "summary text" not in price_only and "news" not in price_only.lower()
    assert "AAA" in price_only and "SPY" in price_only
    assert "SECRET HEADLINE" in digest.render(d, news=True)
