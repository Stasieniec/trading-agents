#!/usr/bin/env python3
"""Mock site-data for developing the dashboard.

It does not imitate the JSON shapes by hand. It builds a fake repo (agents, sessions, ledgers,
memory) in a temporary folder, runs a made-up market through the real ledger code
(trading.ledger.fill_orders, exit_events, mark_event), and then calls the real trading.site.build()
with its paths pointed at that folder. So the output has exactly the shapes site.py writes.

Run from the repo root:  .venv/bin/python dashboard/dev/make-mock.py
Writes dashboard/dev/mock/<scenario>/ with meta.json, equity.json, stats.json, comparison.json and
agents/<name>.json, for these scenarios:

  full   25 trading days. Day one nobody trades. no-news never trades. One failed, one missing
         and two held sessions, a prompt change, stops, targets, extensions, a dividend, and the
         session job "dies" on the last day so the stale banner shows. Notes and theses carry
         hostile markup for the sanitiser test.
  day1   The first morning: sessions have run and orders are waiting, nothing is marked yet.
  empty  No experiment start date at all.
"""

import argparse
import hashlib
import json
import random
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

from trading import config, cost, ledger, market, site  # noqa: E402
from trading.config import AGENTS, START_CASH, TECH_TEN, slippage_for_market_cap  # noqa: E402
from trading.timeutil import previous_trading_day, trading_days  # noqa: E402

UTC = timezone.utc

# ticker: (start price, market cap, daily vol, beta, company)
TICKERS = {
    "SPY": (571.0, 600e9, 0.0, 1.0, "SPDR S&P 500 ETF"),
    "QQQ": (489.0, 300e9, 0.0, 1.25, "Invesco QQQ"),
    "NVDA": (182.0, 4.4e12, 0.026, 1.6, "NVIDIA"),
    "AAPL": (238.0, 3.5e12, 0.014, 1.0, "Apple"),
    "MSFT": (511.0, 3.8e12, 0.013, 1.0, "Microsoft"),
    "GOOGL": (247.0, 3.0e12, 0.017, 1.1, "Alphabet"),
    "AMZN": (226.0, 2.4e12, 0.018, 1.2, "Amazon"),
    "META": (742.0, 1.9e12, 0.02, 1.3, "Meta Platforms"),
    "TSLA": (433.0, 1.4e12, 0.035, 1.8, "Tesla"),
    "AVGO": (344.0, 1.6e12, 0.024, 1.5, "Broadcom"),
    "AMD": (161.0, 260e9, 0.03, 1.7, "Advanced Micro Devices"),
    "PLTR": (178.0, 420e9, 0.034, 1.8, "Palantir"),
    "LMT": (497.0, 116e9, 0.012, 0.4, "Lockheed Martin"),
    "CCJ": (79.0, 34e9, 0.03, 1.2, "Cameco"),
    "FCX": (44.0, 63e9, 0.025, 1.3, "Freeport-McMoRan"),
    "UNP": (229.0, 136e9, 0.013, 0.8, "Union Pacific"),
    "MOS": (33.0, 10.5e9, 0.024, 0.9, "Mosaic"),
    "ALB": (86.0, 9.9e9, 0.035, 1.4, "Albemarle"),
    "KNX": (44.0, 7.2e9, 0.022, 1.0, "Knight-Swift Transportation"),
    "LW": (55.0, 7.8e9, 0.025, 0.7, "Lamb Weston"),
    "SMR": (36.0, 4.9e9, 0.06, 2.0, "NuScale Power"),
    "MP": (62.0, 1.8e9, 0.05, 1.6, "MP Materials"),
    "TROX": (5.9, 940e6, 0.045, 1.4, "Tronox"),
    "IOSP": (88.0, 1.2e9, 0.02, 0.8, "Innospec"),
}

NEWS = [
    ("https://www.reuters.com/business/energy/uranium-supply-deal-2026-10-01/", "Reuters"),
    ("https://www.cnbc.com/2026/10/02/defense-budget-markup.html", "CNBC"),
    ("https://www.marketwatch.com/story/copper-prices-hit-record-on-chile-strike-2026", "MarketWatch"),
    ("https://www.bloomberg.com/news/articles/2026-10-06/rail-volumes-rise", "Bloomberg"),
    ("https://apnews.com/article/drought-idaho-potato-harvest-2026", "AP"),
    ("https://www.ft.com/content/rare-earth-export-controls-2026", "FT"),
    ("https://investor.nvidia.com/news/press-release-details/2026/q3-results", "NVIDIA IR"),
]


class Market:
    def __init__(self, days, seed):
        rnd = random.Random(seed)
        self.bars = {}  # date -> ticker -> bar
        last = {t: v[0] for t, v in TICKERS.items()}
        for d in days:
            m = rnd.gauss(0.0005, 0.0085)
            day = {}
            for t, (_, _, vol, beta, _) in TICKERS.items():
                r = beta * m + (rnd.gauss(0, vol) if vol else 0.0)
                gap = r * rnd.uniform(0.2, 0.6) + rnd.gauss(0, max(vol, 0.004) * 0.25)
                o = last[t] * (1 + gap)
                c = last[t] * (1 + r)
                span = max(vol, 0.006)
                h = max(o, c) * (1 + abs(rnd.gauss(0, span * 0.5)))
                lo = min(o, c) * (1 - abs(rnd.gauss(0, span * 0.5)))
                day[t] = {"o": round(o, 4), "h": round(h, 4), "l": round(lo, 4), "c": round(c, 4)}
                last[t] = c
            self.bars[d.isoformat()] = day

    def opens(self, d):
        return {t: b["o"] for t, b in self.bars[d.isoformat()].items()}

    def closes(self, d):
        return {t: b["c"] for t, b in self.bars[d.isoformat()].items()}


def point_at(root: Path) -> None:
    """Redirect every path constant the builder and marking code use."""
    data = root / "data"
    bench = data / "benchmarks"
    paths = {"AGENTS_DIR": root / "agents", "DATA_DIR": data, "SITE_DIR": root / "site-data",
             "EXPERIMENT_FILE": data / "experiment.json", "BENCH_DIR": bench, "SPY_DAILY": bench / "spy-daily.csv"}
    for mod in (config, cost, market, site):
        for k, v in paths.items():
            if hasattr(mod, k):
                setattr(mod, k, v)


def bp_for(t):
    return 10 if t in TECH_TEN else slippage_for_market_cap(TICKERS[t][1])[1]


HOSTILE_NOTES = """# General notes

Working rules I keep coming back to:

- Rail and trucking names react a day late to harvest and weather stories.
- **Do not** chase anything that already gapped more than 6% at the open.
- Rare earth export rules: check the effective date, not the announcement date.

## Sanitiser test (mock data only)

<script>window.__pwned = 'notes-script'; alert('notes-script')</script>

<img src=x onerror="window.__pwned='notes-img'; alert('notes-img')">

A [javascript link](javascript:alert('notes-js')) and an [http link](http://example.com/plain-http)
and a [normal https link](https://www.reuters.com/markets/).

<a href="javascript:alert('raw-anchor')" onclick="alert('onclick')">raw anchor</a>

<iframe src="https://example.com/frame"></iframe>

<form action="https://example.com/steal"><input name="x"><button>Send</button></form>

<style>body { display: none !important; }</style>

<div style="position:fixed;inset:0;background:red">overlay div</div>

![tracking pixel](https://example.com/pixel.png)

| Chain | Status |
|---|---|
| Idaho drought to frozen fries | open |
| Chile copper strike to rail volumes | closed |

```
code block stays code: <b>not bold</b>
```
"""


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class Sim:
    def __init__(self, root: Path, days, seed=7):
        self.root, self.days = root, days
        self.rnd = random.Random(seed)
        self.mk = Market(days, seed)
        self.states = {n: ledger.State() for n in AGENTS}
        self.states.update({f"bench:{b}": ledger.State() for b in config.BENCHMARKS})
        self.hash = {n: hashlib.sha256(n.encode()).hexdigest()[:12] for n in AGENTS}
        self.touched = {n: set() for n in AGENTS}

    def ledger_dir(self, name):
        if name.startswith("bench:"):
            return self.root / "data" / "benchmarks" / name[6:] / "ledger"
        return self.root / "agents" / name / "ledger"

    # -- agent decisions ---------------------------------------------------------------
    def order(self, name, d, i, action, t, w=0.0, thesis="", h=10, stop=8.0, target=15.0, p=0.55,
              sources=(), chain=()):
        self.touched[name].add(t)
        srcs = [{"url": u, "read": k == 0 and u.startswith("https"),
                 "answer": ("The page, dated %s, reports the event and quotes two analysts. "
                            "It does not mention the company by name." % d.isoformat()) if k == 0 else ""}
                for k, u in enumerate(sources)]
        return {"action": action, "ticker": t, "target_weight": w, "thesis": thesis, "horizon_days": h,
                "stop_pct": stop, "target_pct": target, "probability": p, "sources": srcs,
                "causal_chain": list(chain), "slippage_bp": bp_for(t),
                "id": f"{name}-{d.isoformat()}-{i:02d}", "session_date": d.isoformat(),
                "decided_at": datetime.combine(d, datetime.min.time(), UTC).replace(hour=11, minute=52).isoformat(),
                "prompt_hash": self.hash[name]}

    def weights(self, name, d):
        st = self.states[name]
        prev = self.mk.closes(previous_trading_day(d)) if d != self.days[0] else {}
        px = {t: prev.get(t, p.avg_cost) for t, p in st.positions.items()}
        eq = st.equity(px)
        return {t: p.qty * px[t] / eq for t, p in st.positions.items()}

    def decide(self, name, k, d):
        """Returns (status, reason, orders, rejected, summary) or None for a missing session."""
        st = self.states[name]
        r = self.rnd
        orders, rejected = [], []
        expired = sorted(t for t, p in st.positions.items() if p.horizon_end and p.horizon_end <= d.isoformat())
        w = self.weights(name, d)
        held = set(st.positions)
        closed = set()
        if k == 0:
            return "decided", "", [], [], ("First session. Read the digest, built a watch list, bought nothing: "
                                           "nothing had a clear catalyst left after the overnight move.")
        if name == "no-news":
            if k == 14:
                return None
            if k == 19:
                return "hold", "deadline before the open reached", [], [], ""
            return "decided", "", [], [], (f"Day {k + 1}. Scanned movers and most-actives. Nothing in prices alone "
                                           "justified a position; holding cash.")
        if name == "tech-ten" and k == 6:
            return "hold", "hard cost cap $2.00 reached", [], [], ""
        if name == "weird-links" and k == 8:
            return "failed", "API error APIStatusError 529", [], [], ""

        n = 1
        for t in expired:
            if r.random() < 0.5:
                orders.append(self.order(name, d, n, "extend", t, thesis=(
                    f"Extended. The original catalyst for {t} has not resolved yet; the filing is now expected "
                    "next week. Tightened the stop."), h=8, stop=5.0, target=12.0, p=0.52,
                    sources=[NEWS[r.randrange(len(NEWS))][0]]))
            else:
                orders.append(self.order(name, d, n, "close", t, p=0.5))
                closed.add(t)  # stays in held, so this session cannot buy it back
            n += 1

        invested = sum(v for t, v in w.items() if t in held and t not in closed)
        if name == "tech-ten":
            if k in (1, 9, 16, 21):
                picks = r.sample([t for t in TECH_TEN if t not in held], 2)
                for t in picks:
                    wt = round(r.uniform(0.12, 0.2), 3)
                    if invested + wt > 0.95:
                        break
                    invested += wt
                    orders.append(self.order(name, d, n, "set_weight", t, wt, thesis=(
                        f"{TICKERS[t][4]} guided above consensus and the move at the open looks small next to the "
                        "revision. Expect the gap to close over two weeks."), h=r.choice([6, 8, 10]),
                        stop=7.0, target=12.0, p=round(r.uniform(0.5, 0.68), 2),
                        sources=[NEWS[6][0], "https://www.cnbc.com/2026/10/09/megacap-earnings-preview.html"]))
                    n += 1
            if k == 12:
                rejected.append("order 3 (TSM): you may only trade " + ", ".join(TECH_TEN))
        elif name == "open-quality":
            if k % 3 == 1 and invested < 0.6:
                t = r.choice([x for x in ("LMT", "CCJ", "FCX", "UNP", "MP", "SMR", "NVDA", "AVGO") if x not in held])
                wt = round(r.uniform(0.12, 0.22), 3)
                orders.append(self.order(name, d, n, "set_weight", t, wt, thesis=(
                    f"{TICKERS[t][4]}: a specific, verifiable catalyst reported overnight, and the stock moved less "
                    "than peers on the same news. Sized small because the second leg depends on a regulator."),
                    h=r.choice([5, 8, 12]), stop=8.0, target=r.choice([12.0, 15.0, 20.0]),
                    p=round(r.uniform(0.52, 0.7), 2), sources=[NEWS[r.randrange(6)][0]]))
                n += 1
        elif name == "weird-links":
            if k % 4 == 1 and invested < 0.7:
                t = r.choice([x for x in ("LW", "KNX", "MOS", "ALB", "TROX", "IOSP") if x not in held])
                wt = round(r.uniform(0.06, 0.12), 3)
                chain = [
                    {"step": "Drought cuts the Idaho potato harvest by a fifth, per the state agriculture office.",
                     "source_url": NEWS[4][0]},
                    {"step": "Processors buy more from the Pacific Northwest and ship it further, by truck.",
                     "source_url": "https://www.agweb.com/news/crops/potatoes-freight-2026"},
                    {"step": f"{TICKERS[t][4]} has the largest refrigerated fleet on those lanes. "
                             "Weakest link: whether contracts reprice inside the horizon.", "source_url": ""},
                ]
                thesis = (f"Second-order trade on {t}. The headline is about crops; the money moves through freight. "
                          "<img src=x onerror=\"window.__pwned='thesis'\"> should show as text.")
                orders.append(self.order(name, d, n, "set_weight", t, wt, thesis=thesis, h=r.choice([6, 10, 15]),
                                         stop=10.0, target=18.0, p=round(r.uniform(0.45, 0.62), 2),
                                         sources=[NEWS[4][0], "javascript:alert('source')",
                                                  "http://insecure.example.com/article"], chain=chain))
                n += 1
        if name == "open-quality" and k >= 11:
            self.hash[name] = "b7e1c0d94a21"  # prompt edited on day 12
        summary = (f"Session {d.isoformat()}. Placed {len(orders)} orders. "
                   + ("Kept the rest in cash; nothing else cleared the bar. " if len(orders) < 2 else "")
                   + "Watching the **Thursday** CPI print and the rail volume report.")
        return "decided", ("some orders rejected after the resubmission" if rejected else ""), orders, rejected, summary

    # -- one full day --------------------------------------------------------------------
    def run_sessions(self, k, d):
        todays = {}
        for name in AGENTS:
            res = self.decide(name, k, d)
            if res is None:
                continue
            status, reason, orders, rejected, summary = res
            folder = self.root / "agents" / name / "sessions" / d.isoformat()
            c = round(self.rnd.uniform(0.35, 0.95), 4) if status != "failed" else round(self.rnd.uniform(0.0, 0.1), 4)
            if reason.startswith("hard cost cap"):
                c = 2.03
            dec = {"agent": name, "date": d.isoformat(), "dry_run": False, "status": status, "reason": reason,
                   "orders": orders, "rejected": rejected, "prompt_hash": self.hash[name], "total_cost": c,
                   "seconds": self.rnd.randint(140, 900), "summary": summary}
            write(folder / "decision.json", json.dumps(dec, indent=1))
            write(folder / "usage.json", json.dumps({"total_cost": c, "calls": [], "prompt_hash": self.hash[name]}))
            if status != "decided":
                summary = (f"The harness wrote this summary: the session on {d.isoformat()} ended without a decision "
                           f"({reason or status}). Nothing traded; all positions held.\n\n")
            write(self.root / "agents" / name / "memory" / "summary.md", f"Session {d.isoformat()}.\n\n{summary}\n")
            ledger.append_jsonl(self.ledger_dir(name) / "orders.jsonl", orders)
            todays[name] = orders
        return todays

    def mark(self, k, d, todays):
        opens, closes = self.mk.opens(d), self.mk.closes(d)
        prev = self.mk.closes(previous_trading_day(d)) if k else {t: v[0] for t, v in TICKERS.items()}
        bars = self.mk.bars[d.isoformat()]
        actions = []
        if k == 10:
            actions.append({"id": "mock-div-msft", "kind": "cash_dividends", "symbol": "MSFT", "rate": 0.91,
                            "ex_date": d.isoformat()})
            actions.append({"id": "mock-div-aapl", "kind": "cash_dividends", "symbol": "AAPL", "rate": 0.26,
                            "ex_date": d.isoformat()})
        for name, st in self.states.items():
            ev = ledger.corporate_action_events(st, actions, d)
            if name.startswith("bench:"):
                orders = ledger.read_jsonl(self.ledger_dir(name) / "orders.jsonl") if k == 0 else []
            else:
                orders = todays.get(name, [])
            ev += ledger.fill_orders(st, orders, d, opens, prev)
            ev += ledger.exit_events(st, d, bars)
            ev.append(ledger.mark_event(st, d, closes))
            ledger.append_jsonl(self.ledger_dir(name) / "events.jsonl", ev)
        spy = bars["SPY"]
        market._append_spy(d.isoformat(), spy)
        digest = self.root / "data" / "digest" / f"{d.isoformat()}.json"
        write(digest, json.dumps({"date": d.isoformat(), "usage": {"cost": 0.0021}}))

    def notes(self):
        for name in AGENTS:
            mem = self.root / "agents" / name / "memory"
            if name == "weird-links":
                write(mem / "notes.md", HOSTILE_NOTES)
            elif name == "no-news":
                pass  # never wrote notes: tests the empty state
            else:
                write(mem / "notes.md", "# Notes\n\n- Earnings gaps in megacaps fade within three sessions about "
                      "half the time.\n- Check the opening auction size before trusting a gap.\n")
            for t in sorted(self.touched[name])[:5]:
                body = (f"# {t}\n\n## Current view\n\n{TICKERS[t][4]}. Thesis intact; the next check is the "
                        "monthly volume report.\n\n## Log\n\n- 2026-10-02: opened after the [overnight report]"
                        f"({NEWS[0][0]}).\n- 2026-10-09: still holding, *nothing new*.\n")
                if name == "weird-links" and t == sorted(self.touched[name])[0]:
                    body += "\n<script>alert('ticker-note')</script> [bad](javascript:alert(1))\n"
                write(mem / "tickers" / f"{t}.md", body)


def scaffold(root: Path, start: date | None):
    point_at(root)
    for name in AGENTS:
        src = REPO / "agents" / name / "prompt.md"
        write(root / "agents" / name / "prompt.md", src.read_text() if src.exists() else f"Prompt for {name}.\n")
    (root / "data" / "digest").mkdir(parents=True, exist_ok=True)
    if start:
        write(root / "data" / "experiment.json", json.dumps({"start_date": start.isoformat()}))
        market.ensure_benchmark_orders(start)


def build(root: Path, now: datetime, out: Path):
    site.now_utc = lambda: now
    site.build()
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(root / "site-data", out)


def scenario_full(out: Path):
    end = date(2026, 10, 27)
    days = trading_days(end - timedelta(days=45), end)[-25:]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scaffold(root, days[0])
        sim = Sim(root, days)
        for k, d in enumerate(days):
            todays = sim.run_sessions(k, d)
            sim.mark(k, d, todays)
        sim.notes()
        # The session job never ran on 2026-10-28; the dashboard is built that evening.
        build(root, datetime(2026, 10, 28, 21, 50, tzinfo=UTC), out)


def scenario_day1(out: Path):
    d = date(2026, 10, 28)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scaffold(root, d)
        sim = Sim(root, [d])
        sim.run_sessions(1, d)  # orders placed, nothing filled yet
        build(root, datetime(2026, 10, 28, 13, 5, tzinfo=UTC), out)


def scenario_empty(out: Path):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scaffold(root, None)
        build(root, datetime(2026, 10, 28, 9, 0, tzinfo=UTC), out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE / "mock")
    a = ap.parse_args()
    for name, fn in (("full", scenario_full), ("day1", scenario_day1), ("empty", scenario_empty)):
        fn(a.out / name)
        print(f"wrote {a.out / name}")


if __name__ == "__main__":
    main()
