"""The books. Pure functions over an append-only event log, so every number can be replayed.

Orders are written by agent sessions (ledger/orders.jsonl). Everything that changes holdings or
cash is an event written only by the marking job (ledger/events.jsonl). State is the replay of
events from the start, never stored as the source of truth.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import MIN_TRADE_USD, START_CASH
from .timeutil import add_trading_days


@dataclass
class Position:
    ticker: str
    qty: float
    cost: float  # total cost basis, including slippage
    opened: str
    stop_price: float | None = None
    target_price: float | None = None
    horizon_end: str | None = None
    thesis: str = ""
    original_thesis: str = ""
    original_date: str = ""
    order_id: str = ""
    extensions: int = 0
    slippage_bp: int = 10

    @property
    def avg_cost(self) -> float:
        return self.cost / self.qty if self.qty else 0.0


@dataclass
class State:
    cash: float = START_CASH
    positions: dict[str, Position] = field(default_factory=dict)
    done_orders: set = field(default_factory=set)
    applied_actions: set = field(default_factory=set)
    last_marked: str | None = None
    slippage_paid: float = 0.0
    traded_value: float = 0.0

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(p.qty * prices.get(t, p.avg_cost) for t, p in self.positions.items())


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def apply_event(s: State, e: dict) -> None:
    t = e.get("ticker")
    k = e["type"]
    if k == "fill":
        value = e["qty"] * e["price"]
        s.slippage_paid += abs(e["qty"] * (e["price"] - e["ref_price"]))
        s.traded_value += value
        if e["side"] == "buy":
            s.cash -= value
            p = s.positions.get(t)
            if p:
                p.qty += e["qty"]
                p.cost += value
            else:
                s.positions[t] = Position(t, e["qty"], value, e["date"], original_date=e["date"])
        else:
            p = s.positions[t]
            s.cash += value
            frac = e["qty"] / p.qty if p.qty else 1.0
            p.cost -= p.cost * frac
            p.qty -= e["qty"]
            if p.qty <= 1e-9:
                del s.positions[t]
        if e.get("order_id"):
            s.done_orders.add(e["order_id"])
        if abs(s.cash) < 1e-6:
            s.cash = 0.0  # float dust from sizing to exactly the available cash
    elif k == "plan":
        p = s.positions.get(t)
        if p:
            if not p.original_thesis:
                p.original_thesis = e["thesis"]
            elif e.get("extension"):
                p.extensions += 1
            p.stop_price = e["stop_price"]
            p.target_price = e["target_price"]
            p.horizon_end = e["horizon_end"]
            p.thesis = e["thesis"]
            p.order_id = e["order_id"]
            p.slippage_bp = e.get("slippage_bp", p.slippage_bp)
        s.done_orders.add(e["order_id"])
    elif k == "cancel":
        s.done_orders.add(e["order_id"])
    elif k == "split":
        p = s.positions.get(t)
        if p:
            r = e["ratio"]
            p.qty *= r
            if p.stop_price:
                p.stop_price /= r
            if p.target_price:
                p.target_price /= r
        s.applied_actions.add(e["action_id"])
    elif k == "dividend":
        s.cash += e["amount"]
        s.applied_actions.add(e["action_id"])
    elif k == "rename":
        p = s.positions.pop(e["old"], None)
        if p:
            p.ticker = e["new"]
            s.positions[e["new"]] = p
        s.applied_actions.add(e["action_id"])
    elif k == "settle":
        p = s.positions.pop(t, None)
        if p:
            s.cash += p.qty * e["price"]
        s.applied_actions.add(e["action_id"])
    elif k == "noop_action":
        s.applied_actions.add(e["action_id"])
    elif k == "mark":
        s.last_marked = e["date"]


def replay(events: list[dict]) -> State:
    s = State()
    for e in events:
        apply_event(s, e)
    return s


# ---------------------------------------------------------------------------
# One trading day, in the order the plan fixes: corporate actions, fills, exits, mark.


def corporate_action_events(s: State, actions: list[dict], day: date) -> list[dict]:
    """Events for actions on held tickers that take effect on or before this day."""
    out = []
    d = day.isoformat()
    for a in sorted(actions, key=lambda a: (a.get("ex_date") or a.get("effective_date") or a.get("process_date") or "")):
        aid = a.get("id") or f"{a['kind']}:{a.get('symbol')}:{a.get('ex_date')}"
        if aid in s.applied_actions:
            continue
        when = a.get("ex_date") or a.get("effective_date") or a.get("process_date")
        if not when or when > d:
            continue
        kind = a["kind"]
        sym = a.get("symbol") or a.get("acquiree_symbol") or a.get("old_symbol")
        held = s.positions.get(sym) if sym else None
        if held and when <= held.opened:
            # Bought on or after the ex-date: the fill price already reflects it, and no dividend is due.
            ev = {"type": "noop_action", "action_id": aid, "date": d, "ticker": sym, "kind": kind,
                  "note": "position opened on or after the ex-date"}
            apply_event(s, ev)
            out.append(ev)
            continue
        if kind in ("forward_splits", "reverse_splits", "unit_splits"):
            if held and a.get("old_rate") and a.get("new_rate"):
                ratio = float(a["new_rate"]) / float(a["old_rate"])
                ev = {"type": "split", "action_id": aid, "date": d, "ticker": sym, "ratio": ratio, "ex_date": when}
                apply_event(s, ev)
                out.append(ev)
        elif kind == "cash_dividends":
            if held and a.get("rate"):
                amount = held.qty * float(a["rate"])
                ev = {"type": "dividend", "action_id": aid, "date": d, "ticker": sym, "qty": held.qty,
                      "rate": float(a["rate"]), "amount": amount, "ex_date": when}
                apply_event(s, ev)
                out.append(ev)
        elif kind == "name_changes":
            if a.get("old_symbol") in s.positions and a.get("new_symbol"):
                ev = {"type": "rename", "action_id": aid, "date": d, "old": a["old_symbol"], "new": a["new_symbol"]}
                apply_event(s, ev)
                out.append(ev)
        elif kind == "cash_mergers":
            if held and a.get("rate"):
                ev = {"type": "settle", "action_id": aid, "date": d, "ticker": sym, "price": float(a["rate"]),
                      "reason": "cash merger"}
                apply_event(s, ev)
                out.append(ev)
        elif kind == "worthless_removals":
            if held:
                ev = {"type": "settle", "action_id": aid, "date": d, "ticker": sym, "price": 0.0,
                      "reason": "worthless removal"}
                apply_event(s, ev)
                out.append(ev)
        elif held:
            # Stock mergers, spin-offs and the rest: recorded so a human can see it, not modelled.
            ev = {"type": "noop_action", "action_id": aid, "date": d, "ticker": sym, "kind": kind,
                  "note": "corporate action not modelled"}
            apply_event(s, ev)
            out.append(ev)
    return out


def fill_orders(s: State, orders: list[dict], day: date, opens: dict[str, float],
                prev_close: dict[str, float]) -> list[dict]:
    """Fill one day's orders at the open. Sizes from equity marked at that open.

    orders: the day's orders, any action. opens: fill reference price per ticker (opening
    auction, else bar open). prev_close: fallback for valuing holdings with no open today.
    """
    d = day.isoformat()
    out: list[dict] = []
    todo = [o for o in orders if o["id"] not in s.done_orders]
    if not todo:
        return out

    def emit(ev):
        apply_event(s, ev)
        out.append(ev)

    def ref(t):
        return opens.get(t)

    # Equity at the open, before any of today's trades.
    marks = {t: opens.get(t) or prev_close.get(t) or p.avg_cost for t, p in s.positions.items()}
    equity = s.equity(marks)

    plans: list[tuple[dict, float]] = []
    sells: list[tuple[dict, float]] = []
    buys: list[tuple[dict, float]] = []
    for o in todo:
        t = o["ticker"]
        price = ref(t)
        if price is None:
            emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": t,
                  "reason": "no opening price (halted or not trading)"})
            continue
        held = s.positions.get(t)
        cur_qty = held.qty if held else 0.0
        if o["action"] == "close":
            if cur_qty > 0:
                sells.append((o, cur_qty))
            else:
                emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": t, "reason": "nothing to close"})
        elif o["action"] == "extend":
            if held:
                plans.append((o, price))
            else:
                emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": t, "reason": "no position to extend"})
        else:  # set_weight
            target_value = float(o["target_weight"]) * equity
            diff = target_value - cur_qty * price
            if abs(diff) < MIN_TRADE_USD:
                if held:
                    plans.append((o, price))
                else:
                    emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": t, "reason": "trade too small"})
            elif diff < 0:
                sells.append((o, min(cur_qty, -diff / price)))
            else:
                buys.append((o, diff))

    for o, qty in sells:
        t = o["ticker"]
        p0 = ref(t)
        bp = o.get("slippage_bp", 10)
        emit({"type": "fill", "order_id": o["id"], "date": d, "ticker": t, "side": "sell", "qty": qty,
              "price": p0 * (1 - bp / 1e4), "ref_price": p0, "slippage_bp": bp, "reason": o["action"]})
        if o["action"] == "set_weight" and t in s.positions:
            plans.append((o, p0))

    want = sum(v for _, v in buys)
    scale = min(1.0, s.cash / want) if want > 0 else 1.0
    for o, value in buys:
        t = o["ticker"]
        p0 = ref(t)
        bp = o.get("slippage_bp", 10)
        px = p0 * (1 + bp / 1e4)
        qty = value * scale / px
        if qty * px < MIN_TRADE_USD:
            emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": t, "reason": "not enough cash"})
            continue
        emit({"type": "fill", "order_id": o["id"], "date": d, "ticker": t, "side": "buy", "qty": qty,
              "price": px, "ref_price": p0, "slippage_bp": bp, "reason": "set_weight",
              "scaled": round(scale, 6)})
        plans.append((o, p0))

    for o, p0 in plans:
        t = o["ticker"]
        if t not in s.positions:
            continue
        has_plan = o.get("stop_pct") is not None  # benchmarks carry no plan
        emit({"type": "plan", "order_id": o["id"], "date": d, "ticker": t,
              "stop_price": p0 * (1 - float(o["stop_pct"]) / 100) if has_plan else None,
              "target_price": p0 * (1 + float(o["target_pct"]) / 100) if has_plan else None,
              "horizon_end": add_trading_days(day, int(o["horizon_days"])).isoformat() if has_plan else None,
              "thesis": o.get("thesis", ""), "slippage_bp": o.get("slippage_bp", 10),
              "extension": o["action"] == "extend"})
    for o in todo:
        if o["id"] not in s.done_orders:
            emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": o["ticker"], "reason": "not executed"})
    return out


def exit_events(s: State, day: date, bars: dict[str, dict]) -> list[dict]:
    """Stops and targets against the day's bar. Stop wins when both are touched."""
    d = day.isoformat()
    out = []
    for t, p in list(s.positions.items()):
        b = bars.get(t)
        if not b or (p.stop_price is None and p.target_price is None):
            continue
        o, h, lo = float(b["o"]), float(b["h"]), float(b["l"])
        level, reason = None, None
        if p.stop_price is not None and o <= p.stop_price:
            level, reason = o, "stop (gapped through at the open)"
        elif p.stop_price is not None and lo <= p.stop_price:
            level, reason = p.stop_price, "stop"
        elif p.target_price is not None and o >= p.target_price:
            level, reason = o, "target (gapped through at the open)"
        elif p.target_price is not None and h >= p.target_price:
            level, reason = p.target_price, "target"
        if level is None:
            continue
        bp = p.slippage_bp
        ev = {"type": "fill", "order_id": "", "date": d, "ticker": t, "side": "sell", "qty": p.qty,
              "price": level * (1 - bp / 1e4), "ref_price": level, "slippage_bp": bp, "reason": reason}
        apply_event(s, ev)
        out.append(ev)
    return out


def mark_event(s: State, day: date, closes: dict[str, float]) -> dict:
    prices = {t: closes.get(t, p.avg_cost) for t, p in s.positions.items()}
    invested = sum(p.qty * prices[t] for t, p in s.positions.items())
    ev = {"type": "mark", "date": day.isoformat(), "cash": s.cash, "invested": invested,
          "equity": s.cash + invested,
          "prices": {t: prices[t] for t in sorted(prices)},
          "qty": {t: p.qty for t, p in sorted(s.positions.items())}}
    apply_event(s, ev)
    return ev
