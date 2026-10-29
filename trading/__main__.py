"""Entry points for the workflows.

python -m trading gate-session      decide whether this cron firing should run today's sessions (no secrets)
python -m trading session-day       mark, universe, digest, four agents, site data, commits (needs keys)
python -m trading gate-mark         decide whether the marking job has work (no secrets)
python -m trading mark              mark closed days, records, site data, commit (Alpaca keys)
python -m trading site              rebuild site-data from the repo (no secrets)
python -m trading check-sources     test every data source from this machine (Alpaca keys)
python -m trading start DATE        set the experiment's first trading day
python -m trading scan-outgoing     pattern scan of everything about to be pushed
"""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import (AGENTS, AGENTS_DIR, DATA_DIR, DEADLINE_BEFORE_OPEN_MIN, EXPERIMENT_FILE, LOCAL_START, LOCAL_TZ,
                     MIN_LEAD_BEFORE_OPEN_MIN, MONTHLY_CAP_USD, ROOT)
from .secrets import scan_paths, scan_text
from .timeutil import NY, UTC, is_trading_day, last_closed_day, next_open, now_utc, session_times


def log(msg: str) -> None:
    print(f"{datetime.now(UTC):%H:%M:%S} {msg}", flush=True)


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def commit(paths: list[str], message: str, allowed: list[str]) -> bool:
    """Stage paths, refuse anything outside allowed prefixes or containing key material, commit."""
    existing = [p for p in paths if (ROOT / p).exists()]
    if not existing:
        return False
    git("add", "--", *existing)
    staged = [s for s in git("diff", "--cached", "--name-only").splitlines() if s]
    if not staged:
        return False
    outside = [s for s in staged if not any(s.startswith(a) for a in allowed)]
    if outside:
        git("reset", "-q")
        raise RuntimeError(f"refusing to commit files outside {allowed}: {outside[:5]}")
    hits = scan_paths([ROOT / s for s in staged if (ROOT / s).exists()])
    if hits:
        git("reset", "-q")
        raise RuntimeError(f"refusing to commit, key material found: {hits[:3]}")
    git("commit", "-q", "-m", message)
    return True


def set_output(**kw) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in kw.items()]
    if out:
        with open(out, "a") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def experiment_start() -> date | None:
    if EXPERIMENT_FILE.exists():
        s = json.loads(EXPERIMENT_FILE.read_text()).get("start_date")
        return date.fromisoformat(s) if s else None
    return None


def session_done(name: str, day: date) -> bool:
    """A session counts as done unless it failed, so a later firing retries a failed one."""
    p = AGENTS_DIR / name / "sessions" / day.isoformat() / "decision.json"
    if not p.exists():
        return False
    try:
        return json.loads(p.read_text()).get("status") != "failed"
    except ValueError:
        return False


# ---------------------------------------------------------------------------


def cmd_gate_session(_args) -> None:
    now = now_utc()
    local = now.astimezone(ZoneInfo(LOCAL_TZ))
    day, open_at = next_open(now)
    reasons = []
    start = experiment_start()
    if not start:
        reasons.append("experiment has no start date yet")
    elif day < start:
        reasons.append(f"experiment starts {start}")
    if day != now.astimezone(ZoneInfo("America/New_York")).date():
        reasons.append(f"next open is {day}, not today")
    if (local.hour, local.minute) < LOCAL_START:
        reasons.append(f"Amsterdam time {local:%H:%M} is before {LOCAL_START[0]}:{LOCAL_START[1]:02d}")
    lead = (open_at - now).total_seconds() / 60
    if lead < MIN_LEAD_BEFORE_OPEN_MIN:
        reasons.append(f"only {lead:.0f} minutes to the open")
    if all(session_done(n, day) for n in AGENTS):
        reasons.append("today's sessions already ran")
    for r in reasons:
        log(f"gate: {r}")
    set_output(run="false" if reasons else "true", day=day.isoformat())


def cmd_session_day(args) -> None:
    import anthropic

    from . import digest as digest_mod
    from . import market, site, universe
    from .agent.harness import Session
    from .alpaca import Alpaca, DataError
    from .cost import month_spend

    if os.environ.get("CLAUDE_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = os.environ["CLAUDE_API_KEY"]
    now = now_utc()
    day, open_at = next_open(now)
    dry = args.dry_run
    fill_at = "open"
    if args.intraday:
        # A late session while the market is open: orders fill at today's close, which nobody has seen.
        today = now.astimezone(NY).date()
        if not is_trading_day(today):
            log(f"{today} is not a trading day")
            return
        o, c = session_times(today)
        if not (o < now < c - timedelta(minutes=45)):
            log("an intraday session needs the market open and at least 45 minutes to the close")
            return
        day, fill_at = today, "close"
        deadline = min(now + timedelta(minutes=25), c - timedelta(minutes=20))
    elif dry:
        deadline = now + timedelta(minutes=25)
    else:
        deadline = open_at - timedelta(minutes=DEADLINE_BEFORE_OPEN_MIN)
        if (open_at - now).total_seconds() / 60 < MIN_LEAD_BEFORE_OPEN_MIN:
            log("too close to the open, not starting")
            return
    names = [n for n in (args.agents.split(",") if args.agents else AGENTS) if n in AGENTS]
    alpaca = Alpaca()
    client = anthropic.Anthropic(max_retries=3, timeout=300.0)

    # 1. Bring the books up to date.
    upto = last_closed_day(now)
    if upto and not dry:
        try:
            if market.run(upto, alpaca, log=log):
                site.write_records()
                commit(["data/benchmarks", "agents"], f"mark: catch up to {upto}", ["data/benchmarks/", "agents/"])
        except Exception as e:  # a marking bug must not stop the sessions
            log(f"catch-up marking failed: {type(e).__name__}: {e}")

    # 2. Universe and digest, frozen before any agent runs.
    try:
        rows = universe.fetch_nasdaq()
        try:
            assets = alpaca.assets()
        except DataError as e:
            log(f"Alpaca asset list failed, eligibility uses Nasdaq only: {e}")
            assets = None
        universe.save(day, universe.build(rows, assets))
    except Exception as e:
        log(f"universe refresh failed ({type(e).__name__}), using the last snapshot")
    uni = universe.Universe.load()
    log(f"universe as of {uni.as_of}: {sum(1 for r in uni.rows.values() if r['eligible'])} eligible")

    stamp = now.strftime("%Y-%m-%dT%H%M")
    dig = digest_mod.load(day)
    if dig is None:
        dig = digest_mod.build(day, alpaca, uni, anthropic_client=client, log=log)
        if dry:
            # A dry run's digest stays with the dry run, so the real session builds a fresh one.
            (DATA_DIR / "dryruns" / stamp).mkdir(parents=True, exist_ok=True)
            (DATA_DIR / "dryruns" / stamp / "digest.json").write_text(json.dumps(dig, indent=1))
        else:
            digest_mod.save(dig)
    log("digest sources: " + ", ".join(f"{k} {v}" for k, v in dig["sources"].items()))
    if not dry:
        commit(["data/universe", "data/digest"], f"digest: {day}", ["data/universe/", "data/digest/"])

    # 3. Budget.
    spent = month_spend(day)
    if spent >= MONTHLY_CAP_USD and not dry:
        log(f"monthly cap reached (${spent:.2f} of ${MONTHLY_CAP_USD:.0f}), skipping sessions")
        for n in names:
            out = AGENTS_DIR / n / "sessions" / day.isoformat()
            out.mkdir(parents=True, exist_ok=True)
            (out / "decision.json").write_text(json.dumps({"agent": n, "date": day.isoformat(), "status": "skipped",
                                                           "reason": "monthly budget reached", "orders": [],
                                                           "total_cost": 0.0}))
            commit([f"agents/{n}/sessions/{day}"], f"session: {n} {day} skipped, monthly budget",
                   [f"agents/{n}/"])
        return

    # 4. The agents, in parallel. Each one's files are committed as soon as it finishes.
    jobs = {}
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        for n in names:
            if not dry and session_done(n, day):
                log(f"{n}: already ran today")
                continue
            cfg = AGENTS[n]
            if dry:
                out = DATA_DIR / "dryruns" / stamp / n
                mem = out / "memory-copy"
                mem.mkdir(parents=True, exist_ok=True)
                src = AGENTS_DIR / n / "memory"
                if src.exists():
                    subprocess.run(["cp", "-r", str(src), str(mem / "memory")], check=False)
                memory_dir = mem
            else:
                out = AGENTS_DIR / n / "sessions" / day.isoformat()
                memory_dir = None
            try:
                s = Session(cfg, day, deadline, dig, uni, out, client=client, alpaca=Alpaca(), dry_run=dry,
                            hard_cap=args.hard_cap, memory_dir=memory_dir, log=log, fill_at=fill_at)
            except Exception as e:
                log(f"{n}: could not start ({type(e).__name__}: {e})")
                continue
            jobs[pool.submit(s.run)] = (n, out)
        for fut in as_completed(jobs):
            n, out = jobs[fut]
            try:
                res = fut.result()
            except Exception as e:
                log(f"{n}: crashed ({type(e).__name__})")
                continue
            hits = scan_paths([out] + ([AGENTS_DIR / n / "memory"] if not dry else []))
            if hits:
                log(f"{n}: key material found in output, not committing: {hits[:2]}")
                continue
            rel = out.relative_to(ROOT).as_posix()
            if dry:
                commit([rel, f"data/dryruns/{stamp}/digest.json"], f"dry run: {n} {stamp}", ["data/dryruns/"])
            else:
                commit([f"agents/{n}"], f"session: {n} {day}, {res['status']}, {len(res['orders'])} orders, "
                       f"${res['total_cost']:.2f}", [f"agents/{n}/"])

    site.build()
    commit(["site-data"], f"site: after sessions {day}", ["site-data/"])


def cmd_gate_mark(_args) -> None:
    from .market import days_to_mark
    upto = last_closed_day(now_utc())
    days = days_to_mark(upto) if upto else []
    log(f"gate: {len(days)} day(s) to mark up to {upto}")
    set_output(run="true" if days else "false")


def cmd_mark(_args) -> None:
    from . import market, site
    upto = last_closed_day(now_utc())
    if upto and market.run(upto, log=log):
        site.write_records()
        commit(["data/benchmarks", "agents"], f"mark: {upto}", ["data/benchmarks/", "agents/"])
    try:
        site.build()
        commit(["site-data"], f"site: after marking {upto}", ["site-data/"])
    except Exception as e:  # the books are committed; a site bug must not strand them
        log(f"site build failed: {type(e).__name__}: {e}")
        raise


def cmd_site(_args) -> None:
    from . import site
    site.build()


def cmd_start(args) -> None:
    d = date.fromisoformat(args.date)
    if not is_trading_day(d):
        sys.exit(f"{d} is not an NYSE trading day")
    EXPERIMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXPERIMENT_FILE.write_text(json.dumps({"start_date": d.isoformat()}, indent=1) + "\n")
    print(f"start date set to {d}")


def cmd_check_sources(_args) -> None:
    from . import digest as digest_mod
    from . import universe
    from .alpaca import Alpaca, DataError
    a = Alpaca()
    today = now_utc().date()
    checks = {
        "bars SPY": lambda: len(a.daily_bars(["SPY", "NVDA"], today - timedelta(days=10), today).get("SPY", [])),
        "auctions": lambda: sum(len(v) for v in a.opening_auctions(["SPY", "NVDA"], today - timedelta(days=7), today).values()),
        "corporate actions": lambda: len(a.corporate_actions(["AAPL", "NVDA", "MSFT"], today - timedelta(days=200), today)),
        "news": lambda: len(a.news(now_utc() - timedelta(days=1), now_utc())),
        "most actives": lambda: len(a.most_actives()),
        "movers": lambda: len(a.movers().get("gainers", [])),
        "latest trades": lambda: len(a.latest_trades(["SPY", "AAPL"])),
        "assets": lambda: len(a.assets()),
        "nasdaq screener": lambda: len(universe.fetch_nasdaq()),
    }
    for name, url in digest_mod.RSS:
        checks[f"rss {name}"] = (lambda u=url, n=name: len(digest_mod._fetch_rss(n, u, now_utc() - timedelta(days=3))))
    for name, fn in checks.items():
        try:
            log(f"{name}: ok, {fn()} items")
        except Exception as e:
            log(f"{name}: FAILED {type(e).__name__}: {str(e)[:200] if isinstance(e, DataError) else ''}")
    # The shape of the auction data, with no prices, to confirm the parser.
    try:
        end = (now_utc() - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        j = a._get("https://data.alpaca.markets/v2/stocks/auctions",
                   {"symbols": "SPY,NVDA", "start": (today - timedelta(days=6)).isoformat(), "end": end, "feed": "sip"})
        for sym, days in (j.get("auctions") or {}).items():
            for d in days:
                o = d.get("o") or []
                log(f"auction {sym} {d.get('d', '')[:10]}: {len(o)} open prints, keys "
                    f"{sorted(o[0]) if o else []}, conditions {sorted({str(p.get('c')) for p in o})}, "
                    f"exchanges {sorted({str(p.get('x')) for p in o})}")
        parsed = a.opening_auctions(["SPY", "NVDA"], today - timedelta(days=6), today)
        bars = a.daily_bars(["SPY", "NVDA"], today - timedelta(days=6), today)
        for sym in ("SPY", "NVDA"):
            for b in bars.get(sym, []):
                ap = parsed.get(sym, {}).get(b["date"])
                if ap:
                    log(f"{sym} {b['date']}: auction open differs from bar open by {abs(ap / float(b['o']) - 1) * 1e4:.1f} bp")
    except Exception as e:
        log(f"auction shape check failed: {type(e).__name__}: {str(e)[:200] if isinstance(e, DataError) else ''}")


def cmd_eval(args) -> None:
    import anthropic

    from . import digest as digest_mod
    from . import evals, universe
    from .alpaca import Alpaca

    if os.environ.get("CLAUDE_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = os.environ["CLAUDE_API_KEY"]
    alpaca = Alpaca()
    client = anthropic.Anthropic(max_retries=3, timeout=300.0)
    day, _ = next_open(now_utc())
    try:
        rows = universe.fetch_nasdaq()
        universe.save(day, universe.build(rows, alpaca.assets()))
    except Exception as e:
        log(f"universe refresh failed ({type(e).__name__}), using the last snapshot")
    uni = universe.Universe.load()
    dig = digest_mod.load(day) or digest_mod.build(day, alpaca, uni, anthropic_client=None, log=log)
    only = [x.strip() for x in args.only.split(",") if x.strip()] or None
    report = evals.run(client, alpaca, uni, dig, log=log, only=only)
    rel = (evals.EVAL_DIR / report["stamp"]).relative_to(ROOT).as_posix()
    hits = scan_paths([ROOT / rel])
    if hits:
        sys.exit(f"key material found in eval output, not committing: {hits[:2]}")
    commit([rel], f"evals: {report['passed']} of {report['checks']} checks passed, ${report['total_cost']:.2f}",
           ["data/evals/"])


def cmd_scan_outgoing(_args) -> None:
    diff = git("diff", "origin/main..HEAD", check=False)
    hits = scan_text(diff, exact=False)
    if hits:
        sys.exit(f"refusing to push: {hits}")
    print("outgoing commits are clean")


def main() -> None:
    p = argparse.ArgumentParser(prog="trading")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gate-session")
    s = sub.add_parser("session-day")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--agents", default="")
    s.add_argument("--hard-cap", type=float, default=2.0)
    s.add_argument("--intraday", action="store_true")
    sub.add_parser("gate-mark")
    sub.add_parser("mark")
    sub.add_parser("site")
    sub.add_parser("check-sources")
    st = sub.add_parser("start")
    st.add_argument("date")
    sub.add_parser("scan-outgoing")
    ev = sub.add_parser("eval")
    ev.add_argument("--only", default="")
    args = p.parse_args()
    {"gate-session": cmd_gate_session, "session-day": cmd_session_day, "gate-mark": cmd_gate_mark,
     "mark": cmd_mark, "site": cmd_site, "check-sources": cmd_check_sources, "start": cmd_start,
     "scan-outgoing": cmd_scan_outgoing, "eval": cmd_eval}[args.cmd](args)


if __name__ == "__main__":
    main()
