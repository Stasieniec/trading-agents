"""Round trips, equity series and the numbers the dashboard shows. No pass or fail anywhere."""

import math
from collections import defaultdict


def equity_series(events: list[dict]) -> list[dict]:
    # invested is net (shorts negative); gross counts both sides. Marks before shorts had no gross.
    return [{"date": e["date"], "equity": e["equity"], "cash": e["cash"], "invested": e["invested"],
             "gross": e.get("gross", e["invested"])} for e in events if e["type"] == "mark"]


def round_trips(events: list[dict], orders: list[dict], spy: dict[str, tuple[float, float]]) -> list[dict]:
    """Group fills into trades: a trade opens when a ticker goes from flat to held, long or short, and
    closes when it is flat again. For a long, bought_value is the entry and sold_value the exit; a short
    is the other way round. dividends is negative when a short paid them."""
    by_id = {o["id"]: o for o in orders}
    open_: dict[str, dict] = {}
    done: list[dict] = []
    qty: dict[str, float] = defaultdict(float)

    def close(t, e, reason):
        tr = open_.pop(t)
        tr.update(closed=e["date"], exit_reason=reason)
        qty[t] = 0.0
        done.append(_finish(tr, spy))

    for e in events:
        t = e.get("ticker")
        if e["type"] == "split" and t in open_:
            qty[t] *= e["ratio"]
            open_[t]["entry_qty"] *= e["ratio"]
            continue
        if e["type"] == "rename" and e["old"] in open_:
            open_[e["new"]] = open_.pop(e["old"])
            qty[e["new"]] = qty.pop(e["old"], 0.0)
            continue
        if e["type"] == "dividend" and t in open_:
            open_[t]["dividends"] += e["amount"]
            continue
        if e["type"] == "borrow_fee" and t in open_:
            open_[t]["fees"] += e["amount"]
            continue
        if e["type"] == "plan" and t in open_:
            o = by_id.get(e["order_id"], {})
            tr = open_[t]
            if e.get("extension"):
                tr["extensions"].append({"date": e["date"], "thesis": e["thesis"], "horizon_end": e["horizon_end"]})
            tr["horizon_end"] = e["horizon_end"]
            if not tr["thesis"]:
                tr.update(thesis=e["thesis"], probability=o.get("probability"), horizon_days=o.get("horizon_days"),
                          sources=o.get("sources", []), causal_chain=o.get("causal_chain", []),
                          stop_pct=o.get("stop_pct"), target_pct=o.get("target_pct"))
            continue
        if e["type"] == "settle" and t in open_:
            tr = open_[t]
            v = qty[t] * e["price"]
            if v >= 0:
                tr["sold_value"] += v
            else:
                tr["bought_value"] -= v
            close(t, e, e["reason"])
            continue
        if e["type"] != "fill":
            continue
        signed = e["qty"] if e["side"] == "buy" else -e["qty"]
        value = e["qty"] * e["price"]
        cur = qty[t]
        if t in open_ and (cur > 0) != (signed > 0):
            # Shrinks the trade. Anything past flat opens a new trade on the other side.
            used = min(abs(signed), abs(cur))
            tr = open_[t]
            tr["bought_value" if signed > 0 else "sold_value"] += value * used / abs(signed)
            qty[t] = cur + (used if signed > 0 else -used)
            rest = abs(signed) - used
            if abs(qty[t]) <= 1e-9:
                close(t, e, e["reason"])
            if rest <= 1e-9:
                continue
            value *= rest / abs(signed)
            signed = rest if signed > 0 else -rest
        if t not in open_:
            open_[t] = {"ticker": t, "side": "long" if signed > 0 else "short", "opened": e["date"],
                        "bought_value": 0.0, "sold_value": 0.0, "entry_qty": 0.0, "dividends": 0.0, "fees": 0.0,
                        "thesis": "", "extensions": [], "order_id": e["order_id"], "at": e.get("at", "open")}
        tr = open_[t]
        tr["bought_value" if signed > 0 else "sold_value"] += value
        tr["entry_qty"] += abs(signed)
        qty[t] += signed
    for t, tr in open_.items():
        tr["closed"] = None
        tr["open_qty"] = qty[t]
    return done + list(open_.values())


def _spy_return(spy, start: str, end: str, at: str = "open") -> float | None:
    if start not in spy or end not in spy:
        return None
    return spy[end][1] / spy[start][1 if at == "close" else 0] - 1


def _finish(tr: dict, spy) -> dict:
    """A long beats SPY when it returns more than SPY. A short beats SPY when its stock does worse than
    SPY, which is the short's return plus SPY's (the short against a long SPY hedge)."""
    if tr.get("side") == "short":
        entry = tr["sold_value"]
        ret = (entry + tr["dividends"] - tr["fees"] - tr["bought_value"]) / entry if entry else 0.0
    else:
        ret = (tr["sold_value"] + tr["dividends"]) / tr["bought_value"] - 1 if tr["bought_value"] else 0.0
    tr["return"] = ret
    tr["spy_return"] = _spy_return(spy, tr["opened"], tr["closed"], tr.get("at", "open"))
    if tr["spy_return"] is None:
        tr["excess"] = None
    elif tr.get("side") == "short":
        tr["excess"] = ret + tr["spy_return"]
    else:
        tr["excess"] = ret - tr["spy_return"]
    tr["beat_spy"] = tr["excess"] > 0 if tr["excess"] is not None else None
    return tr


def daily_returns(series: list[dict]) -> list[float]:
    out = []
    for a, b in zip(series, series[1:]):
        out.append(b["equity"] / a["equity"] - 1 if a["equity"] else 0.0)
    return out


def max_drawdown(values: list[float]) -> float:
    peak, worst = -math.inf, 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return worst


def summarize(series: list[dict], spy_series: list[dict], start_cash: float, trades: list[dict],
              traded_value: float, slippage_paid: float) -> dict:
    """Headline numbers for one portfolio. spy_series is the SPY benchmark's equity series."""
    if not series:
        return {"days": 0}
    vals = [s["equity"] for s in series]
    spy = {s["date"]: s["equity"] for s in spy_series}
    # Day-one return counts from the starting cash, since trades fill at that day's open.
    eq = [{"date": "start", "equity": start_cash}] + series
    sp = [{"date": "start", "equity": start_cash}] + [{"date": s["date"], "equity": spy.get(s["date"])} for s in series]
    r = daily_returns(eq)
    rs = [b["equity"] / a["equity"] - 1 if a["equity"] and b["equity"] else 0.0 for a, b in zip(sp, sp[1:])]
    invested = [s["invested"] / s["equity"] if s["equity"] else 0.0 for s in series]
    gross = [s.get("gross", s["invested"]) / s["equity"] if s["equity"] else 0.0 for s in series]
    # Exposure-matched: yesterday's invested fraction of SPY's return, the rest in cash.
    f_prev = [invested[0]] + invested[:-1]
    rm = [f * x for f, x in zip(f_prev, rs)]
    ex = [a - b for a, b in zip(r, rs)]
    exm = [a - b for a, b in zip(r, rm)]
    n = len(r)

    def cum(xs):
        v = 1.0
        for x in xs:
            v *= 1 + x
        return v - 1

    def se_cum(xs):
        if len(xs) < 2:
            return None
        m = sum(xs) / len(xs)
        var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
        return math.sqrt(var) * math.sqrt(len(xs))

    closed = [t for t in trades if t.get("closed")]
    briers = [(t["probability"] - (1.0 if t["beat_spy"] else 0.0)) ** 2
              for t in closed if t.get("probability") is not None and t.get("beat_spy") is not None]
    avg_eq = sum(vals) / len(vals)
    matched_curve = []
    v = start_cash
    for x in rm:
        v *= 1 + x
        matched_curve.append(v)
    return {
        "days": n,
        "equity": vals[-1],
        "total_return": vals[-1] / start_cash - 1,
        "spy_return": cum(rs),
        "excess_vs_spy": cum(r) - cum(rs),
        "excess_vs_spy_se": se_cum(ex),
        "matched_return": cum(rm),
        "excess_vs_matched": cum(r) - cum(rm),
        "excess_vs_matched_se": se_cum(exm),
        "max_drawdown": max_drawdown([start_cash] + vals),
        "avg_invested": sum(invested) / len(invested),
        "avg_gross": sum(gross) / len(gross),
        "trades_closed": len(closed),
        "trades_open": len(trades) - len(closed),
        "win_rate_vs_spy": (sum(1 for t in closed if t.get("beat_spy")) / len(closed)) if closed else None,
        "turnover": traded_value / avg_eq if avg_eq else 0.0,
        "slippage_paid": slippage_paid,
        "brier": sum(briers) / len(briers) if briers else None,
        "brier_n": len(briers),
        "matched_curve": matched_curve,
        "invested_fraction": invested,
        "gross_fraction": gross,
    }


def overlap(a: dict[str, float], b: dict[str, float]) -> float | None:
    """Share of equity the two books hold in common, by weight: the same stock on the same side."""
    if not a and not b:
        return None
    keys = set(a) | set(b)
    return sum(min(abs(a.get(k, 0.0)), abs(b.get(k, 0.0))) for k in keys if a.get(k, 0.0) * b.get(k, 0.0) > 0)


def correlation(x: list[float], y: list[float]) -> float | None:
    n = min(len(x), len(y))
    if n < 5:
        return None
    x, y = x[-n:], y[-n:]
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)
