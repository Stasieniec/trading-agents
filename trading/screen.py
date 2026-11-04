"""The morning screen of sudden moves, for agents that trade them.

Every eligible stock's last session is measured against its own recent volatility and against its
industry, then the most unusual moves get a full row: the move in units of the stock's volatility,
the move net of its industry, volume against its 20-day average, the gap at the open, where it closed
in the day's range, the run-up before it, distance from the 52-week high and low, any pre-market
trading today, how many news stories named it, and whether earnings explain it.

Code computes the numbers; the agent decides what they mean. Built once with the digest.
"""

import math
import re
from datetime import date, datetime, timedelta
from statistics import median

import httpx

from .alpaca import Alpaca, DataError
from .timeutil import add_trading_days, previous_trading_day

EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings"
COLUMNS = ("ticker | cap | industry | last close (date) | 1d % | 1d in sd | 1d vs industry % | vol x avg | "
           "gap % | close in range | 5d % before | 20d % before | from 52w high | from 52w low | streak | "
           "pre-market % (vol) | stories | earnings")
NOTE = ("1d in sd: the last session's move divided by the stock's daily volatility over the 60 sessions "
        "before it. 1d vs industry: the move minus the median move of stocks in the same industry that day. "
        "close in range: 0 = closed at the day's low, 1 = at its high. streak: consecutive up (+) or down (-) "
        "closes. pre-market: the last one-minute price before the open against the last close, with shares "
        "traded so far. stories: news stories in the last day naming the ticker (roundups excluded). "
        "earnings: a report in the last two sessions, or one due in the next five.")


def _pct(a: float, b: float) -> float | None:
    return (a / b - 1) * 100 if b else None


def quick(bars: list[dict]) -> dict | None:
    """The last completed bar's move, its size in standard deviations, and its volume ratio."""
    if len(bars) < 22:
        return None
    c = [float(b["c"]) for b in bars]
    rets = [c[i] / c[i - 1] - 1 for i in range(max(1, len(c) - 61), len(c) - 1)]
    sd = math.sqrt(sum(r * r for r in rets) / len(rets)) if rets else 0.0
    vols = [float(b["v"]) for b in bars[-21:-1]]
    avg_v = sum(vols) / len(vols) if vols else 0.0
    r1 = c[-1] / c[-2] - 1
    return {"date": bars[-1]["date"], "r1": r1 * 100, "sd": sd * 100, "z": r1 / sd if sd else None,
            "vol_x": float(bars[-1]["v"]) / avg_v if avg_v else None}


def stats(bars: list[dict]) -> dict | None:
    """Full numbers for the last completed bar, against the bars before it. Bars oldest first."""
    q = quick(bars)
    if not q:
        return None
    c = [float(b["c"]) for b in bars]
    last = bars[-1]
    hi, lo = float(last["h"]), float(last["l"])
    year = bars[-253:]
    h52 = max(float(b["h"]) for b in year)
    l52 = min(float(b["l"]) for b in year)
    streak = 0
    for i in range(len(c) - 1, 0, -1):
        step = 1 if c[i] > c[i - 1] else -1 if c[i] < c[i - 1] else 0
        if step == 0 or (streak and (step > 0) != (streak > 0)):
            break
        streak += step
    return {**q, "close": c[-1],
            "gap": _pct(float(last["o"]), c[-2]),
            "range_pos": (c[-1] - lo) / (hi - lo) if hi > lo else None,
            "r5": _pct(c[-2], c[-7]) if len(c) >= 7 else None,
            "r20": _pct(c[-2], c[-22]) if len(c) >= 22 else None,
            "from_high": _pct(c[-1], h52), "from_low": _pct(c[-1], l52),
            "streak": streak}


def industry_moves(universe, moves: dict[str, dict]) -> dict[str, float]:
    """Median one-day move per industry (sector when the industry has fewer than five stocks)."""
    groups: dict[str, list[float]] = {}
    for sym, q in moves.items():
        row = universe.get(sym) or {}
        for key in ("i:" + (row.get("industry") or ""), "s:" + (row.get("sector") or "")):
            groups.setdefault(key, []).append(q["r1"])
    out = {}
    for sym in moves:
        row = universe.get(sym) or {}
        ind = groups.get("i:" + (row.get("industry") or ""), [])
        sec = groups.get("s:" + (row.get("sector") or ""), [])
        base = ind if len(ind) >= 5 and row.get("industry") else sec if len(sec) >= 5 and row.get("sector") else []
        if base:
            out[sym] = median(base)
    return out


def fetch_earnings(day: date, log=print) -> dict[str, list[str]]:
    """Earnings reports from two sessions back to five ahead, per symbol, as 'YYYY-MM-DD before open' etc.
    Nasdaq's public calendar; a failure leaves the column empty."""
    when = {"time-pre-market": "before open", "time-after-hours": "after close"}
    days = [previous_trading_day(previous_trading_day(day)), previous_trading_day(day), day]
    days += [add_trading_days(day, i) for i in range(1, 6)]
    out: dict[str, list[str]] = {}
    for d in days:
        try:
            r = httpx.get(EARNINGS_URL, params={"date": d.isoformat()}, timeout=20.0,
                          headers={"User-Agent": "Mozilla/5.0 (research project)", "Accept": "application/json"})
            r.raise_for_status()
            rows = (r.json().get("data") or {}).get("rows") or []
        except Exception as e:  # the calendar is a nice-to-have
            log(f"screen: earnings calendar for {d} failed ({type(e).__name__})")
            continue
        for row in rows:
            sym = str(row.get("symbol") or "").strip().upper().replace("/", ".")
            if re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", sym):
                out.setdefault(sym, []).append(f"{d.isoformat()} {when.get(row.get('time'), 'time not given')}")
    return out


def _rows(universe, alpaca: Alpaca, day: date, syms: list[str], ind: dict[str, float],
          mentions: dict[str, int], earnings: dict[str, list[str]]) -> list[dict]:
    bars = alpaca.daily_bars(syms, day - timedelta(days=380), day, adjustment="split")
    try:
        pre = alpaca.premarket(syms, day)
    except DataError:
        pre = {}
    out = []
    for t in syms:
        done = [b for b in bars.get(t) or [] if b["date"] < day.isoformat()]  # finished sessions only
        s = stats(done)
        if not s:
            out.append({"ticker": t, "missing": True})
            continue
        p = pre.get(t)
        row = universe.get(t) or {}
        out.append({"ticker": t, "market_cap": row.get("market_cap"), "industry": row.get("industry") or "",
                    "shortable": bool(row.get("shortable")),
                    "vs_industry": s["r1"] - ind[t] if t in ind else None,
                    "pre": _pct(p["price"], s["close"]) if p else None, "pre_volume": p["volume"] if p else None,
                    "stories": mentions.get(t, 0), "earnings": earnings.get(t, []), **s})
    return out


def build(universe, alpaca: Alpaca, day: date, mentions: dict[str, int], log=print,
          per_side: int = 10, by_volume: int = 5, by_earnings: int = 5) -> dict:
    """The day's screen: every eligible stock's last move measured, the most unusual given full rows."""
    syms = sorted(s for s, r in universe.rows.items() if r.get("eligible"))
    prev = previous_trading_day(day)
    bars = alpaca.daily_bars(syms, prev - timedelta(days=130), prev, adjustment="split")
    moves = {}
    for s in syms:
        bl = [b for b in bars.get(s) or [] if b["date"] <= prev.isoformat()]
        q = quick(bl)
        if q and q["date"] == prev.isoformat() and q["z"] is not None:
            moves[s] = q
    ind = industry_moves(universe, moves)
    earnings = {s: v for s, v in fetch_earnings(day, log).items() if s in universe.rows}

    def adj_z(s):  # the move net of its industry, in the stock's own standard deviations
        q = moves[s]
        return (q["r1"] - ind.get(s, 0.0)) / q["sd"] if q["sd"] else 0.0

    ranked = sorted(moves, key=adj_z)
    pick = ranked[-per_side:][::-1] + ranked[:per_side]
    for s in sorted(moves, key=lambda s: -(moves[s]["vol_x"] or 0)):
        if len(pick) >= 2 * per_side + by_volume:
            break
        if s not in pick:
            pick.append(s)
    # Reporting right now: the move is still to come, so the daily bars do not show it yet.
    now_reports = [s for s, v in earnings.items() if s in moves and s not in pick
                   and any(x.startswith(prev.isoformat() + " after") or x.startswith(day.isoformat() + " before")
                           for x in v)]
    pick += sorted(now_reports, key=lambda s: -((universe.get(s) or {}).get("market_cap") or 0))[:by_earnings]
    rows = _rows(universe, alpaca, day, pick, ind, mentions, earnings)
    log(f"screen: {len(moves)} stocks measured, {len(rows)} rows")
    return {"day": day.isoformat(), "measured": len(moves), "built_at": datetime.now().astimezone().isoformat(),
            "rows": rows, "industry_moves": {s: round(v, 3) for s, v in ind.items() if s in pick},
            "mentions": mentions, "earnings": earnings}


def scan(universe, alpaca: Alpaca, day: date, tickers: list[str], screen: dict | None, limit: int = 20) -> list[dict]:
    """Full rows for any tickers, with the industry, news and earnings context of today's screen."""
    syms = [t.strip().upper().replace("/", ".") for t in tickers if t.strip()][:limit]
    if not syms:
        return []
    sc = screen or {}
    ind = sc.get("industry_moves") or {}
    rows = _rows(universe, alpaca, day, syms, ind, sc.get("mentions") or {}, sc.get("earnings") or {})
    return rows


def _f(x, fmt="{:+.1f}") -> str:
    return fmt.format(x) if isinstance(x, (int, float)) else "n/a"


def render(rows: list[dict]) -> str:
    if not rows:
        return "no rows"
    lines = [COLUMNS]
    for r in rows:
        if r.get("missing"):
            lines.append(f"{r['ticker']} | not enough history")
            continue
        cap = f"${r['market_cap'] / 1e9:.1f}B" if r.get("market_cap") else "n/a"
        short = "" if r.get("shortable") else " (not shortable)"
        pre = f"{_f(r['pre'])} ({int(r['pre_volume']):,})" if r.get("pre") is not None else "none"
        lines.append(" | ".join([
            r["ticker"] + short, cap, (r.get("industry") or "")[:28], f"{r['close']:.2f} ({r['date']})",
            _f(r["r1"]), _f(r["z"]), _f(r.get("vs_industry")), _f(r["vol_x"], "{:.1f}"), _f(r["gap"]),
            _f(r["range_pos"], "{:.2f}"), _f(r["r5"]), _f(r["r20"]), _f(r["from_high"]), _f(r["from_low"]),
            f"{r['streak']:+d}", pre, str(r.get("stories", 0)), "; ".join(r.get("earnings") or []) or "none"]))
    lines.append(NOTE)
    return "\n".join(lines)


def outcomes(day: date, alpaca: Alpaca, load_digest, lookbacks=(1, 3, 5)) -> str:
    """How the rows of earlier screens did afterwards: from the open of the screen's own day (the first
    price anyone could have traded) to the last close, against SPY over the same days, grouped by the
    direction of the screened move and by whether news or earnings came with it. load_digest(day)
    returns that day's stored digest or None."""
    prev = previous_trading_day(day)
    screens = []
    d = day
    for k in range(1, max(lookbacks) + 1):
        d = previous_trading_day(d)
        if k in lookbacks:
            dig = load_digest(d) or {}
            rows = [r for r in ((dig.get("screen") or {}).get("rows") or []) if not r.get("missing")]
            if rows:
                screens.append((k, d, rows))
    if not screens:
        return ""
    syms = sorted({r["ticker"] for _, _, rows in screens for r in rows} | {"SPY"})
    bars = alpaca.daily_bars(syms, min(d for _, d, _ in screens), prev, adjustment="split")
    by = {s: {b["date"]: b for b in bl} for s, bl in bars.items()}

    def ret(sym, start: date):
        b0, b1 = by.get(sym, {}).get(start.isoformat()), by.get(sym, {}).get(prev.isoformat())
        return float(b1["c"]) / float(b0["o"]) - 1 if b0 and b1 else None

    lines = ["screen of | rows | move | news or earnings | mean vs SPY | went on in the same direction"]
    for k, d, rows in screens:
        spy = ret("SPY", d)
        if spy is None:
            continue
        groups: dict[tuple, list[float]] = {}
        for r in rows:
            x = ret(r["ticker"], d)
            if x is None:
                continue
            news = bool(r.get("stories")) or any(e[:10] <= d.isoformat() for e in r.get("earnings") or [])
            groups.setdefault(("up" if r["r1"] > 0 else "down", news), []).append(x - spy)
        for (move, news), xs in sorted(groups.items()):
            same = sum(1 for x in xs if (x > 0) == (move == "up"))
            lines.append(f"{d.isoformat()} ({k} {'session' if k == 1 else 'sessions'} ago) | {len(xs)} | {move} | "
                         f"{'yes' if news else 'no'} | {sum(xs) / len(xs) * 100:+.2f}% | {same} of {len(xs)}")
    if len(lines) == 1:
        return ""
    lines.append("Each row of an earlier screen is followed from the open of the screen's day to the last close. "
                 "The samples are small and overlap; treat them as hints about what is working now.")
    return "\n".join(lines)
