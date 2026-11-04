"""The morning screen of sudden moves, for agents that trade them.

Candidates are the eligible stocks that moved most in the last session (the Nasdaq snapshot carries
every listing's change), or any tickers asked for. Each gets the numbers that tell an ordinary move
from an extreme one: the move in units of its own recent volatility, volume against its average,
the gap at the open, where it closed in the day's range, the run-up before it, distance from the
52-week high and low, any pre-market trade, and how many of today's headlines name it.
"""

import math
from datetime import date, timedelta

from .alpaca import Alpaca

COLUMNS = ("ticker | cap | last close (date) | 1d % | 1d in sd | vol x avg | gap % | close in range | "
           "5d % before | 20d % before | from 52w high | from 52w low | streak | pre-market % | headlines")


def candidates(universe, top: int = 12) -> list[str]:
    """The biggest gainers and losers of the last session among eligible stocks."""
    rows = [r for r in universe.rows.values() if r.get("eligible") and isinstance(r.get("pct_change"), (int, float))]
    up = sorted(rows, key=lambda r: -r["pct_change"])[:top]
    down = sorted(rows, key=lambda r: r["pct_change"])[:top]
    return [r["symbol"] for r in up + down if abs(r["pct_change"]) > 0]


def _pct(a: float, b: float) -> float | None:
    return (a / b - 1) * 100 if b else None


def stats(bars: list[dict]) -> dict | None:
    """Numbers for the last completed bar, against the bars before it. Bars oldest first."""
    if len(bars) < 22:
        return None
    c = [float(b["c"]) for b in bars]
    last, prev = bars[-1], bars[-2]
    rets = [c[i] / c[i - 1] - 1 for i in range(max(1, len(c) - 61), len(c) - 1)]
    sd = math.sqrt(sum(r * r for r in rets) / len(rets)) if rets else 0.0
    r1 = c[-1] / c[-2] - 1
    vols = [float(b["v"]) for b in bars[-21:-1]]
    avg_v = sum(vols) / len(vols) if vols else 0.0
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
    return {
        "date": last["date"], "close": c[-1], "r1": r1 * 100,
        "z": r1 / sd if sd else None,
        "vol_x": float(last["v"]) / avg_v if avg_v else None,
        "gap": _pct(float(last["o"]), c[-2]),
        "range_pos": (c[-1] - lo) / (hi - lo) if hi > lo else None,
        "r5": _pct(c[-2], c[-7]) if len(c) >= 7 else None,
        "r20": _pct(c[-2], c[-22]) if len(c) >= 22 else None,
        "from_high": _pct(c[-1], h52), "from_low": _pct(c[-1], l52),
        "streak": streak,
        "prev_close": float(prev["c"]),
    }


def scan(universe, alpaca: Alpaca, day: date, tickers: list[str] | None = None,
         news_mentions: list[dict] | None = None, limit: int = 30) -> list[dict]:
    syms = [t.strip().upper().replace("/", ".") for t in (tickers or candidates(universe))][:limit]
    if not syms:
        return []
    bars = alpaca.daily_bars(syms, day - timedelta(days=380), day, adjustment="split")
    trades = alpaca.latest_trades(syms)
    mentions = {m["symbol"]: m["stories"] for m in news_mentions or []}
    out = []
    for t in syms:
        done = [b for b in bars.get(t) or [] if b["date"] < day.isoformat()]  # finished sessions only
        s = stats(done)
        if not s:
            out.append({"ticker": t, "missing": True})
            continue
        tr = trades.get(t)
        pre = None
        if tr and str(tr.get("t", ""))[:10] == day.isoformat() and tr.get("p"):
            pre = _pct(float(tr["p"]), s["close"])
        row = universe.get(t) or {}
        out.append({"ticker": t, "market_cap": row.get("market_cap"), "shortable": bool(row.get("shortable")),
                    "pre": pre, "headlines": mentions.get(t, 0), **s})
    return out


def _f(x, fmt="{:+.1f}") -> str:
    return fmt.format(x) if isinstance(x, (int, float)) else "n/a"


def render(rows: list[dict]) -> str:
    if not rows:
        return "no candidates"
    lines = [COLUMNS]
    for r in rows:
        if r.get("missing"):
            lines.append(f"{r['ticker']} | not enough history")
            continue
        cap = f"${r['market_cap'] / 1e9:.1f}B" if r.get("market_cap") else "n/a"
        short = "" if r.get("shortable") else " (not shortable)"
        lines.append(" | ".join([
            r["ticker"] + short, cap, f"{r['close']:.2f} ({r['date']})", _f(r["r1"]), _f(r["z"]),
            _f(r["vol_x"], "{:.1f}"), _f(r["gap"]), _f(r["range_pos"], "{:.2f}"), _f(r["r5"]), _f(r["r20"]),
            _f(r["from_high"]), _f(r["from_low"]), f"{r['streak']:+d}", _f(r["pre"]), str(r["headlines"])]))
    lines.append("1d in sd: the last session's move divided by the stock's daily volatility over the 60 sessions "
                 "before it. close in range: 0 = closed at the day's low, 1 = at its high. streak: consecutive "
                 "up (+) or down (-) closes. pre-market %: the latest IEX trade today against the last close, "
                 "where there is one. headlines: today's digest stories naming the ticker.")
    return "\n".join(lines)
