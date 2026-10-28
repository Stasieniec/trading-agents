"""The marking job: brings every portfolio up to date, one trading day at a time."""

import csv
import json
from datetime import date, timedelta

from .alpaca import Alpaca, bar_is_sane
from .config import (AGENTS, AGENTS_DIR, BENCHMARK_SLIPPAGE_BP, BENCHMARKS, DATA_DIR,
                     EXPERIMENT_FILE)
from .ledger import (State, append_jsonl, apply_event, corporate_action_events, exit_events,
                     fill_orders, mark_event, read_jsonl, replay)
from .timeutil import previous_trading_day, trading_days

BENCH_DIR = DATA_DIR / "benchmarks"
SPY_DAILY = BENCH_DIR / "spy-daily.csv"


def experiment() -> dict:
    if EXPERIMENT_FILE.exists():
        return json.loads(EXPERIMENT_FILE.read_text())
    return {}


def start_date() -> date | None:
    s = experiment().get("start_date")
    return date.fromisoformat(s) if s else None


def portfolio_dirs() -> dict[str, object]:
    out = {name: AGENTS_DIR / name / "ledger" for name in AGENTS}
    out.update({f"bench:{b}": BENCH_DIR / b / "ledger" for b in BENCHMARKS})
    return out


def ensure_benchmark_orders(start: date) -> None:
    for name, b in BENCHMARKS.items():
        p = BENCH_DIR / name / "ledger" / "orders.jsonl"
        if p.exists():
            continue
        rows = [{"id": f"{name}-{start.isoformat()}-{i:02d}", "session_date": start.isoformat(), "ticker": t,
                 "action": "set_weight", "target_weight": w, "slippage_bp": BENCHMARK_SLIPPAGE_BP}
                for i, (t, w) in enumerate(sorted(b["weights"].items()), 1)]
        append_jsonl(p, rows)


def last_known_closes(events: list[dict]) -> dict[str, float]:
    closes: dict[str, float] = {}
    for e in events:
        if e["type"] == "mark":
            closes.update(e.get("prices", {}))
    return closes


def days_to_mark(upto: date) -> list[date]:
    start = start_date()
    if not start or upto < start:
        return []
    marked = []
    for d in portfolio_dirs().values():
        st = replay(read_jsonl(d / "events.jsonl"))
        marked.append(st.last_marked)
    earliest_missing = start
    if all(marked):
        earliest_missing = date.fromisoformat(min(marked)) + timedelta(days=1)
    return trading_days(earliest_missing, upto)


def run(upto: date, alpaca: Alpaca | None = None, log=print) -> list[date]:
    days = days_to_mark(upto)
    if not days:
        log("marking: nothing to do")
        return []
    start = start_date()
    ensure_benchmark_orders(start)
    alpaca = alpaca or Alpaca()

    books = {}
    symbols, order_syms = {"SPY"}, set()
    for name, d in portfolio_dirs().items():
        events = read_jsonl(d / "events.jsonl")
        orders = read_jsonl(d / "orders.jsonl")
        st = replay(events)
        books[name] = (d, st, orders, last_known_closes(events))
        symbols |= set(st.positions)
        for o in orders:
            if days[0].isoformat() <= o["session_date"] <= days[-1].isoformat():
                order_syms.add(o["ticker"])
    symbols |= order_syms

    first, last = days[0], days[-1]
    bars = alpaca.daily_bars(sorted(symbols), previous_trading_day(first), last, adjustment="raw")
    auctions = alpaca.opening_auctions(sorted(order_syms), first, last) if order_syms else {}
    actions = alpaca.corporate_actions(sorted(symbols), first - timedelta(days=10), last + timedelta(days=1))
    by_day: dict[str, dict[str, dict]] = {}
    rejected = 0
    for sym, bl in bars.items():
        for b in bl:
            if bar_is_sane(b):
                by_day.setdefault(b["date"], {})[sym] = b
            else:
                rejected += 1
    if rejected:
        log(f"marking: rejected {rejected} bars with open or close outside the high-low range")

    for day in days:
        ds = day.isoformat()
        today = by_day.get(ds, {})
        if "SPY" not in today:
            log(f"marking: no SPY bar for {ds} yet, stopping before it")
            return [d for d in days if d < day]
        _append_spy(ds, today["SPY"])
        for name, (d, st, orders, closes) in books.items():
            if st.last_marked and st.last_marked >= ds:
                continue
            new = []
            new += corporate_action_events(st, actions, day)
            todays = [o for o in orders if o["session_date"] == ds]
            stale = [o for o in orders if o["session_date"] < ds and o["id"] not in st.done_orders]
            for o in stale:
                ev = {"type": "cancel", "order_id": o["id"], "date": ds, "ticker": o["ticker"],
                      "reason": "expired unfilled"}
                apply_event(st, ev)
                new.append(ev)
            opens = {}
            for o in todays:
                t = o["ticker"]
                px = (auctions.get(t) or {}).get(ds)
                if px is None and t in today:
                    px = float(today[t]["o"])
                if px is not None:
                    opens[t] = px
            for t in st.positions:
                if t in today:
                    opens.setdefault(t, float(today[t]["o"]))
            new += fill_orders(st, todays, day, opens, closes)
            new += exit_events(st, day, today)
            for t, b in today.items():
                closes[t] = float(b["c"])
            new.append(mark_event(st, day, closes))
            append_jsonl(d / "events.jsonl", new)
        log(f"marking: {ds} done")
    return days


def _append_spy(ds: str, bar: dict) -> None:
    SPY_DAILY.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    if SPY_DAILY.exists():
        with open(SPY_DAILY) as f:
            rows = {r["date"]: r for r in csv.DictReader(f)}
    rows[ds] = {"date": ds, "open": bar["o"], "close": bar["c"]}
    with open(SPY_DAILY, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "open", "close"])
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])


def spy_series() -> dict[str, tuple[float, float]]:
    if not SPY_DAILY.exists():
        return {}
    with open(SPY_DAILY) as f:
        return {r["date"]: (float(r["open"]), float(r["close"])) for r in csv.DictReader(f)}


def state_for(agent: str) -> tuple[State, dict[str, float]]:
    events = read_jsonl(AGENTS_DIR / agent / "ledger" / "events.jsonl")
    return replay(events), last_known_closes(events)
