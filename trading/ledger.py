"""The books. Pure functions over an append-only event log, so every number can be replayed.

Orders are written by agent sessions (ledger/orders.jsonl). Everything that changes holdings or
cash is an event written only by the marking job (ledger/events.jsonl). State is the replay of
events from the start, never stored as the source of truth.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import BORROW_FEE_ANNUAL, BORROW_FEE_DAY_COUNT, MIN_TRADE_USD, START_CASH
from .timeutil import add_trading_days


@dataclass
class Position:
    ticker: str
    qty: float  # negative for a short
    cost: float  # total cost basis, including slippage; negative for a short (minus the proceeds)
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
    exits_from: str = ""  # first day stops and targets apply; later than the fill day for intraday fills

    @property
    def avg_cost(self) -> float:
        return self.cost / self.qty if self.qty else 0.0

    @property
    def short(self) -> bool:
        return self.qty < 0

    def pnl_pct(self, price: float) -> float:
        """Gain on the position at this price, as a fraction of its cost: positive when a short's price falls."""
        if not self.avg_cost:
            return 0.0
        return (self.avg_cost - price) / self.avg_cost if self.short else price / self.avg_cost - 1


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

    def gross(self, prices: dict[str, float]) -> float:
        return sum(abs(p.qty) * prices.get(t, p.avg_cost) for t, p in self.positions.items())


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
        px = e["price"]
        signed = e["qty"] if e["side"] == "buy" else -e["qty"]
        s.slippage_paid += abs(e["qty"] * (px - e["ref_price"]))
        s.traded_value += e["qty"] * px
        s.cash -= signed * px
        p = s.positions.get(t)
        if p and (p.qty > 0) != (signed > 0):
            # Reduces the position. Anything beyond its size opens the other side.
            used = min(abs(signed), abs(p.qty))
            p.cost -= p.cost * used / abs(p.qty)
            p.qty += used if signed > 0 else -used
            rest = abs(signed) - used
            if abs(p.qty) <= 1e-9:
                del s.positions[t]
                p = None
            signed = (rest if signed > 0 else -rest) if rest > 1e-9 else 0.0
        if signed:
            if p:
                p.qty += signed
                p.cost += signed * px
            else:
                s.positions[t] = Position(t, signed, signed * px, e["date"], original_date=e["date"])
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
            p.exits_from = e.get("exits_from", e["date"])
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
        s.cash += e["amount"]  # negative for a short, which owes the dividend
        s.applied_actions.add(e["action_id"])
    elif k == "borrow_fee":
        s.cash -= e["amount"]
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
    """Fill one day's orders at the given prices. Sizes from equity marked at those prices.

    orders: the day's orders, any action. opens: fill reference price per ticker (opening
    auction, else bar open, or the first minute after the decision). prev_close: fallback for
    valuing holdings with no price here. A negative target weight is a short. Trades that shrink a
    position go first; trades that grow one are scaled together so longs plus shorts stay within
    equity, which also keeps cash from going negative.
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

    def marks():
        return {t: opens.get(t) or prev_close.get(t) or p.avg_cost for t, p in s.positions.items()}

    # Equity before any of today's trades.
    equity = s.equity(marks())

    plans: list[tuple[dict, float]] = []
    shrink: list[tuple[dict, float]] = []  # signed share change toward zero
    grow: list[tuple[dict, float]] = []  # signed share change away from zero
    for o in todo:
        t = o["ticker"]
        price = ref(t)
        if price is None:
            emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": t,
                  "reason": "no opening price (halted or not trading)"})
            continue
        held = s.positions.get(t)
        cur = held.qty if held else 0.0
        if o["action"] == "close":
            if cur:
                shrink.append((o, -cur))
            else:
                emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": t, "reason": "nothing to close"})
        elif o["action"] == "extend":
            if held:
                plans.append((o, price))
            else:
                emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": t, "reason": "no position to extend"})
        else:  # set_weight
            want = float(o["target_weight"]) * equity / price
            if abs(want - cur) * price < MIN_TRADE_USD:
                if held:
                    plans.append((o, price))
                else:
                    emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": t, "reason": "trade too small"})
            elif cur and (want > 0) != (cur > 0):
                shrink.append((o, -cur))  # flip: close the old side, then open the new one
                grow.append((o, want))
            elif abs(want) < abs(cur):
                shrink.append((o, want - cur))
            else:
                grow.append((o, want - cur))

    def fill(o, q, value=None, scale=None):
        t = o["ticker"]
        p0 = ref(t)
        bp = o.get("slippage_bp", 10)
        side = "buy" if q > 0 else "sell"
        px = p0 * (1 + bp / 1e4) if q > 0 else p0 * (1 - bp / 1e4)
        # Sized net of slippage on both sides, so longs plus shorts end within equity after costs.
        qty = abs(q) if value is None else value * scale / (p0 * (1 + bp / 1e4))
        ev = {"type": "fill", "order_id": o["id"], "date": d, "ticker": t, "side": side, "qty": qty,
              "price": px, "ref_price": p0, "slippage_bp": bp, "reason": o["action"],
              "at": o.get("fill_at", "open")}
        if scale is not None:
            ev["scaled"] = round(scale, 6)
        return ev

    for o, q in shrink:
        emit(fill(o, q))
        if o["action"] == "set_weight" and o["ticker"] in s.positions and not any(g is o for g, _ in grow):
            plans.append((o, ref(o["ticker"])))

    m = marks()
    room = max(0.0, s.equity(m) - s.gross(m))
    want = sum(abs(q) * ref(o["ticker"]) for o, q in grow)
    scale = min(1.0, room / want) if want > 0 else 1.0
    for o, q in grow:
        value = abs(q) * ref(o["ticker"])
        ev = fill(o, q, value, scale)
        if ev["qty"] * ev["price"] < MIN_TRADE_USD:
            emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": o["ticker"],
                  "reason": "not enough cash" if q > 0 else "no room left within 100% of equity"})
            continue
        emit(ev)
        plans.append((o, ref(o["ticker"])))

    for o, p0 in plans:
        t = o["ticker"]
        p = s.positions.get(t)
        if not p:
            continue
        has_plan = o.get("stop_pct") is not None  # benchmarks carry no plan
        sign = -1 if p.short else 1  # a short's stop sits above the fill and its target below
        emit({"type": "plan", "order_id": o["id"], "date": d, "ticker": t,
              "stop_price": p0 * (1 - sign * float(o["stop_pct"]) / 100) if has_plan else None,
              "target_price": p0 * (1 + sign * float(o["target_pct"]) / 100) if has_plan else None,
              "horizon_end": add_trading_days(day, int(o["horizon_days"])).isoformat() if has_plan else None,
              "thesis": o.get("thesis", ""), "slippage_bp": o.get("slippage_bp", 10),
              "extension": o["action"] == "extend",
              # Filled after the open: the day's earlier highs and lows happened before the position existed.
              "exits_from": d if o.get("fill_at", "open") == "open" else add_trading_days(day, 1).isoformat()})
    for o in todo:
        if o["id"] not in s.done_orders:
            emit({"type": "cancel", "order_id": o["id"], "date": d, "ticker": o["ticker"], "reason": "not executed"})
    return out


def exit_events(s: State, day: date, bars: dict[str, dict]) -> list[dict]:
    """Stops and targets against the day's bar. Stop wins when both are touched.

    A long stops out when the price falls to its stop; a short when it rises to its stop. Targets
    work the other way round."""
    d = day.isoformat()
    out = []
    for t, p in list(s.positions.items()):
        b = bars.get(t)
        if not b or (p.stop_price is None and p.target_price is None) or (p.exits_from and p.exits_from > d):
            continue
        o, h, lo = float(b["o"]), float(b["h"]), float(b["l"])
        if p.short:
            hit_stop_open = p.stop_price is not None and o >= p.stop_price
            hit_stop = p.stop_price is not None and h >= p.stop_price
            hit_target_open = p.target_price is not None and o <= p.target_price
            hit_target = p.target_price is not None and lo <= p.target_price
        else:
            hit_stop_open = p.stop_price is not None and o <= p.stop_price
            hit_stop = p.stop_price is not None and lo <= p.stop_price
            hit_target_open = p.target_price is not None and o >= p.target_price
            hit_target = p.target_price is not None and h >= p.target_price
        level, reason = None, None
        if hit_stop_open:
            level, reason = o, "stop (gapped through at the open)"
        elif hit_stop:
            level, reason = p.stop_price, "stop"
        elif hit_target_open:
            level, reason = o, "target (gapped through at the open)"
        elif hit_target:
            level, reason = p.target_price, "target"
        if level is None:
            continue
        bp = p.slippage_bp
        ev = {"type": "fill", "order_id": "", "date": d, "ticker": t, "side": "buy" if p.short else "sell",
              "qty": abs(p.qty), "price": level * (1 + bp / 1e4) if p.short else level * (1 - bp / 1e4),
              "ref_price": level, "slippage_bp": bp, "reason": reason}
        apply_event(s, ev)
        out.append(ev)
    return out


def borrow_fee_events(s: State, day: date, closes: dict[str, float]) -> list[dict]:
    """The fee for holding each short overnight, on its value at the close, for every calendar day until
    the next session (a Friday short pays for the weekend). Positions covered the same day pay nothing."""
    out = []
    nights = (add_trading_days(day, 1) - day).days
    for t, p in sorted(s.positions.items()):
        if not p.short:
            continue
        value = -p.qty * closes.get(t, p.avg_cost)
        ev = {"type": "borrow_fee", "date": day.isoformat(), "ticker": t, "value": value, "days": nights,
              "rate": BORROW_FEE_ANNUAL, "amount": value * BORROW_FEE_ANNUAL * nights / BORROW_FEE_DAY_COUNT}
        apply_event(s, ev)
        out.append(ev)
    return out


def mark_event(s: State, day: date, closes: dict[str, float]) -> dict:
    prices = {t: closes.get(t, p.avg_cost) for t, p in s.positions.items()}
    invested = sum(p.qty * prices[t] for t, p in s.positions.items())  # net: shorts count negative
    ev = {"type": "mark", "date": day.isoformat(), "cash": s.cash, "invested": invested,
          "gross": sum(abs(p.qty) * prices[t] for t, p in s.positions.items()),
          "equity": s.cash + invested,
          "prices": {t: prices[t] for t in sorted(prices)},
          "qty": {t: p.qty for t, p in sorted(s.positions.items())}}
    apply_event(s, ev)
    return ev
