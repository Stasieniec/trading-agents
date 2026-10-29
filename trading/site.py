"""Builds site-data/*.json for the dashboard and the code-owned ticker records. Needs no secrets."""

import json
from datetime import date

from .config import (AGENTS, AGENTS_DIR, BENCHMARKS, DATA_DIR, MONTHLY_CAP_USD, REPO, SITE_DIR, START_CASH,
                     TECH_TEN)
from .cost import month_spend
from .ledger import read_jsonl, replay
from .market import BENCH_DIR, last_known_closes, spy_series, start_date
from .stats import correlation, daily_returns, equity_series, overlap, round_trips, summarize
from .timeutil import NY, now_utc, session_times, trading_days


def _load(dirpath):
    return read_jsonl(dirpath / "events.jsonl"), read_jsonl(dirpath / "orders.jsonl")


def write_records() -> None:
    spy = spy_series()
    for name in AGENTS:
        events, orders = _load(AGENTS_DIR / name / "ledger")
        trips = round_trips(events, orders, spy)
        by_t: dict[str, list] = {}
        for tr in trips:
            by_t.setdefault(tr["ticker"], []).append(tr)
        rd = AGENTS_DIR / name / "records"
        rd.mkdir(parents=True, exist_ok=True)
        for t, trs in by_t.items():
            (rd / f"{t}.json").write_text(json.dumps({"ticker": t, "trades": trs}, indent=1, default=str))


def _sessions(name: str) -> list[dict]:
    out = []
    for p in sorted((AGENTS_DIR / name / "sessions").glob("*/decision.json")):
        d = json.loads(p.read_text())
        out.append({"date": d["date"], "status": d["status"], "reason": d.get("reason", ""),
                    "cost": d.get("total_cost", 0.0), "orders": len(d.get("orders", [])),
                    "rejected": d.get("rejected", []), "prompt_hash": d.get("prompt_hash"),
                    "url": f"https://github.com/{REPO}/tree/main/agents/{name}/sessions/{d['date']}"})
    return out


def _read(p) -> str:
    return p.read_text() if p.exists() else ""


def build() -> None:
    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / "agents").mkdir(exist_ok=True)
    write_records()
    start = start_date()
    now = now_utc()
    spy = spy_series()

    books = {}
    for name in AGENTS:
        books[name] = _load(AGENTS_DIR / name / "ledger")
    for b in BENCHMARKS:
        books[f"bench:{b}"] = _load(BENCH_DIR / b / "ledger")
    series = {k: equity_series(ev) for k, (ev, _) in books.items()}
    spy_eq = series.get("bench:spy", [])
    dates = sorted({s["date"] for ser in series.values() for s in ser})

    def aligned(ser):
        m = {s["date"]: s["equity"] for s in ser}
        return [m.get(d) for d in dates]

    stats, matched, invested, gross, agents_meta = {}, {}, {}, {}, []
    for name, cfg in AGENTS.items():
        ev, orders = books[name]
        st = replay(ev)
        trips = round_trips(ev, orders, spy)
        sm = summarize(series[name], spy_eq, START_CASH, trips, st.traded_value, st.slippage_paid)
        sess = _sessions(name)
        sm["days_run"] = sum(1 for s in sess if s["status"] == "decided")
        sm["api_spend"] = sum(s["cost"] for s in sess)
        m = {s["date"]: v for s, v in zip(series[name], sm.pop("matched_curve", []))}
        matched[name] = [m.get(d) for d in dates]
        f = {s["date"]: v for s, v in zip(series[name], sm.pop("invested_fraction", []))}
        invested[name] = [f.get(d) for d in dates]
        g = {s["date"]: v for s, v in zip(series[name], sm.pop("gross_fraction", []))}
        gross[name] = [g.get(d) for d in dates]
        stats[name] = sm
        agents_meta.append({"name": name, "label": cfg.label, "description": cfg.description})

        closes = last_known_closes(ev)
        prices = {t: closes.get(t, p.avg_cost) for t, p in st.positions.items()}
        eq = st.equity(prices)
        positions = [{"ticker": t, "side": "short" if p.short else "long", "qty": p.qty, "avg_cost": p.avg_cost,
                      "last_close": prices[t], "value": p.qty * prices[t],
                      "weight": p.qty * prices[t] / eq if eq else 0, "pnl_pct": p.pnl_pct(prices[t]),
                      "stop_price": p.stop_price, "target_price": p.target_price, "horizon_end": p.horizon_end,
                      "opened": p.original_date, "thesis": p.thesis, "original_thesis": p.original_thesis,
                      "extensions": p.extensions} for t, p in sorted(st.positions.items())]
        tickers = {}
        for tp in sorted((AGENTS_DIR / name / "memory" / "tickers").glob("*.md")):
            tickers[tp.stem] = tp.read_text()
        recent_orders = sorted(orders, key=lambda o: o["id"], reverse=True)[:60]
        (SITE_DIR / "agents" / f"{name}.json").write_text(json.dumps({
            "name": name, "label": cfg.label, "description": cfg.description,
            "cash": st.cash, "equity": eq, "positions": positions,
            "trades": sorted(trips, key=lambda t: t["opened"], reverse=True),
            "orders": recent_orders, "sessions": sorted(sess, key=lambda s: s["date"], reverse=True),
            "summary": _read(AGENTS_DIR / name / "memory" / "summary.md"),
            "notes": _read(AGENTS_DIR / name / "memory" / "notes.md"),
            "tickers": tickers,
            "prompt": _read(AGENTS_DIR / name / "prompt.md"),
        }, default=str))

    for b, cfg in BENCHMARKS.items():
        ev, _ = books[f"bench:{b}"]
        st = replay(ev)
        stats[f"bench:{b}"] = summarize(series[f"bench:{b}"], spy_eq, START_CASH, [], st.traded_value,
                                        st.slippage_paid)
        stats[f"bench:{b}"].pop("matched_curve", None)
        stats[f"bench:{b}"].pop("invested_fraction", None)
        stats[f"bench:{b}"].pop("gross_fraction", None)

    # Agents side by side: holdings overlap today and correlation of daily returns.
    weights = {}
    for name in AGENTS:
        ev, _ = books[name]
        st = replay(ev)
        closes = last_known_closes(ev)
        px = {t: closes.get(t, p.avg_cost) for t, p in st.positions.items()}
        eq = st.equity(px)
        weights[name] = {t: p.qty * px[t] / eq for t, p in st.positions.items()} if eq else {}
    rets = {name: daily_returns(series[name]) for name in AGENTS}
    names = list(AGENTS)
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pairs.append({"a": a, "b": b, "overlap": overlap(weights[a], weights[b]),
                          "correlation": correlation(rets[a], rets[b])})

    # Health: sessions that should have happened.
    health = {"missing": [], "failed": [], "stale": False}
    last_expected = None
    if start:
        today_ny = now.astimezone(NY).date()
        for d in trading_days(start, today_ny):
            o, _ = session_times(d)
            if o < now:
                last_expected = d
        for name in AGENTS:
            have = {s["date"]: s for s in _sessions(name)}
            for d in trading_days(start, last_expected) if last_expected else []:
                s = have.get(d.isoformat())
                if not s:
                    health["missing"].append({"agent": name, "date": d.isoformat()})
                elif s["status"] == "failed":
                    health["failed"].append({"agent": name, "date": d.isoformat(), "reason": s["reason"]})
        newest = max((s["date"] for n in AGENTS for s in _sessions(n)), default=None)
        health["stale"] = bool(last_expected and (newest is None or newest < last_expected.isoformat()))
        health["last_expected_session"] = last_expected.isoformat() if last_expected else None
        health["newest_session"] = newest

    today = now.date()
    spent = month_spend(today)
    month_days = [d for d in trading_days(today.replace(day=1), _month_end(today))]
    elapsed = [d for d in month_days if d <= today]
    projection = spent / len(elapsed) * len(month_days) if elapsed else spent
    prompt_changes = {}
    for name in AGENTS:
        last, ch = None, []
        for s in sorted(_sessions(name), key=lambda s: s["date"]):
            if last and s["prompt_hash"] and s["prompt_hash"] != last:
                ch.append(s["date"])
            last = s["prompt_hash"] or last
        prompt_changes[name] = ch

    write_holdings(books, now)
    (SITE_DIR / "equity.json").write_text(json.dumps({
        "dates": dates, "start_cash": START_CASH,
        "series": {k: aligned(v) for k, v in series.items()},
        "exposure_matched": matched, "invested_fraction": invested, "gross_fraction": gross,
        "prompt_changes": prompt_changes}))
    (SITE_DIR / "stats.json").write_text(json.dumps(stats, default=str))
    (SITE_DIR / "comparison.json").write_text(json.dumps({"pairs": pairs}))
    (SITE_DIR / "meta.json").write_text(json.dumps({
        "generated_at": now.isoformat(), "start_date": start.isoformat() if start else None,
        "last_marked": dates[-1] if dates else None, "agents": agents_meta,
        "benchmarks": [{"name": f"bench:{b}", "label": c["label"]} for b, c in BENCHMARKS.items()],
        "tech_ten": TECH_TEN, "repo": REPO,
        "budget": {"month": today.strftime("%Y-%m"), "spent": spent, "cap": MONTHLY_CAP_USD,
                   "projection": projection},
        "health": health,
        "digest_dates": sorted(p.stem for p in (DATA_DIR / "digest").glob("*.json"))[-30:],
    }, default=str))


def write_holdings(books: dict, now) -> None:
    """What each portfolio holds right now, for the dashboard's live values during the session."""
    day = now.astimezone(NY).date().isoformat()
    out, symbols = {}, set()
    for name, (events, _) in books.items():
        st = replay(events)
        marks = [e for e in events if e["type"] == "mark"]
        last = marks[-1] if marks else None
        since = None
        for e in events:
            if e["type"] == "fill" and e["date"] == day and str(e.get("at", "")).startswith("after:"):
                t = e["at"][6:]
                since = max(since or t, t)
        out[name] = {"cash": round(st.cash, 6), "positions": {t: p.qty for t, p in sorted(st.positions.items())},
                     "basis": last["equity"] if last and last["date"] < day else (marks[-2]["equity"] if len(marks) > 1
                              and last["date"] == day else START_CASH),
                     "basis_label": (f"close {last['date']}" if last and last["date"] < day else
                                     f"close {marks[-2]['date']}" if len(marks) > 1 else "start"),
                     "since": since}
        symbols |= set(st.positions)
    (SITE_DIR / "holdings.json").write_text(json.dumps({
        "generated_at": now.isoformat(), "trading_day": day, "portfolios": out, "symbols": sorted(symbols)}))


def _month_end(d: date) -> date:
    nxt = d.replace(day=28)
    while nxt.month == d.month:
        nxt = date.fromordinal(nxt.toordinal() + 1)
    return date.fromordinal(nxt.toordinal() - 1)
