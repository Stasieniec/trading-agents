"""The marking job: brings every portfolio up to date, one trading day at a time."""

import csv
import json
from datetime import date, datetime, timedelta

from .alpaca import Alpaca, DataError, bar_is_sane
from .config import (AGENTS, AGENTS_DIR, BENCHMARK_SLIPPAGE_BP, BENCHMARKS, DATA_DIR,
                     EXPERIMENT_FILE)
from .ledger import (State, append_jsonl, apply_event, borrow_fee_events, corporate_action_events,
                     exit_events, fill_orders, mark_event, read_jsonl, replay)
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
    fill_at = experiment().get("start_fill", "open")
    for name, b in BENCHMARKS.items():
        p = BENCH_DIR / name / "ledger" / "orders.jsonl"
        if p.exists():
            continue
        rows = [{"id": f"{name}-{start.isoformat()}-{i:02d}", "session_date": start.isoformat(), "ticker": t,
                 "action": "set_weight", "target_weight": w, "slippage_bp": BENCHMARK_SLIPPAGE_BP,
                 "fill_at": fill_at}
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
    try:
        auctions = alpaca.opening_auctions(sorted(order_syms), first, last) if order_syms else {}
    except DataError as e:
        log(f"marking: opening auctions unavailable, filling at the bar open: {e}")
        auctions = {}
    # Wide window: the endpoint may date entries by processing rather than ex-date. Only actions
    # with an ex-date on or before the day being marked are applied.
    actions = alpaca.corporate_actions(sorted(symbols), first - timedelta(days=10), last + timedelta(days=45))
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
            day_orders = [o for o in orders if o["session_date"] == ds]
            todays = [o for o in day_orders if o.get("fill_at", "open") == "open"]
            at_close = [o for o in day_orders if o.get("fill_at") == "close"]
            intraday = [o for o in day_orders if str(o.get("fill_at", "")).startswith("after:")]
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
            by_moment: dict[str, list] = {}
            for o in intraday:
                by_moment.setdefault(o["fill_at"][6:], []).append(o)
            for moment, group in sorted(by_moment.items()):
                # Filled at the first minute after the decision: a price nobody had seen. Stops start tomorrow.
                px = alpaca.first_minute_open(sorted({o["ticker"] for o in group} | set(st.positions)),
                                              datetime.fromisoformat(moment.replace("Z", "+00:00")))
                new += fill_orders(st, group, day, px, closes)
            for t, b in today.items():
                closes[t] = float(b["c"])
            if at_close:
                # Orders decided during the session fill at that day's close, which nobody had seen.
                close_px = {t: float(b["c"]) for t, b in today.items()}
                new += fill_orders(st, at_close, day, close_px, closes)
            new += borrow_fee_events(st, day, closes)
            new.append(mark_event(st, day, closes))
            append_jsonl(d / "events.jsonl", new)
        log(f"marking: {ds} done")
    return days


def fill_today(now: datetime, alpaca: Alpaca | None = None, log=print) -> bool:
    """Book today's fills during the session, as soon as the prices exist (the free plan hides the last
    15 minutes). The evening pass then only adds exits and the close. Safe to run any number of times."""
    from .timeutil import NY, UTC, is_trading_day, session_times

    day = now.astimezone(NY).date()
    start = start_date()
    if not start or day < start or not is_trading_day(day):
        log("fill pass: not a trading day of the experiment")
        return False
    open_at, _ = session_times(day)
    ready = now - timedelta(minutes=16)
    if ready < open_at:
        log("fill pass: the open is not in the data yet")
        return False
    ensure_benchmark_orders(start)
    ds = day.isoformat()
    alpaca = alpaca or Alpaca()
    books, symbols, wanted = {}, set(), {}
    for name, d in portfolio_dirs().items():
        events = read_jsonl(d / "events.jsonl")
        st = replay(events)
        if st.last_marked and st.last_marked >= ds:
            continue
        pending = []
        for o in read_jsonl(d / "orders.jsonl"):
            if o["session_date"] != ds or o["id"] in st.done_orders:
                continue
            at = o.get("fill_at", "open")
            if at == "open" or (at.startswith("after:") and
                                datetime.fromisoformat(at[6:].replace("Z", "+00:00")) <= ready):
                pending.append(o)
        if pending:
            books[name] = (d, st, pending, last_known_closes(events))
            symbols |= set(st.positions) | {o["ticker"] for o in pending}
    if not books:
        log("fill pass: nothing to fill")
        return False
    try:
        auctions = alpaca.opening_auctions(sorted(symbols), day, day)
    except DataError as e:
        log(f"fill pass: opening auctions unavailable: {e}")
        auctions = {}
    first_minute = alpaca.first_minute_open(sorted(symbols), open_at)
    opens = {t: (auctions.get(t) or {}).get(ds) or first_minute.get(t) for t in symbols}
    opens = {t: v for t, v in opens.items() if v}
    actions = alpaca.corporate_actions(sorted(symbols), day - timedelta(days=10), day + timedelta(days=45))
    for name, (d, st, pending, closes) in books.items():
        new = corporate_action_events(st, actions, day)
        at_open = [o for o in pending if o.get("fill_at", "open") == "open"]
        new += fill_orders(st, at_open, day, opens, closes)
        groups: dict[str, list] = {}
        for o in pending:
            if o.get("fill_at", "open").startswith("after:"):
                groups.setdefault(o["fill_at"][6:], []).append(o)
        for moment, group in sorted(groups.items()):
            px = alpaca.first_minute_open(sorted({o["ticker"] for o in group} | set(st.positions)),
                                          datetime.fromisoformat(moment.replace("Z", "+00:00")))
            new += fill_orders(st, group, day, px, closes)
        append_jsonl(d / "events.jsonl", new)
        log(f"fill pass: {name}, {sum(1 for e in new if e['type'] == 'fill')} fills")
    return True


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
