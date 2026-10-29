"""Checks every order before it reaches the ledger. Returns plain-language reasons the agent can act on."""

import re
from dataclasses import dataclass, field

from ..config import TECH_TEN, AgentConfig, slippage_for_market_cap
from ..ledger import State
from ..universe import Universe
from .urls import norm

NAME_SUFFIX = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|common stock|"
    r"class [a-z]|ordinary shares|american depositary shares|ads|n\.?v|s\.?a|ag|se|lp|l\.p|the)\b\.?", re.I)


@dataclass
class Context:
    agent: AgentConfig
    universe: Universe
    state: State
    closes: dict[str, float]
    session_date: str
    expired: set[str] = field(default_factory=set)
    read_ok_urls: set[str] = field(default_factory=set)
    seen_urls: set[str] = field(default_factory=set)
    headline_text: str = ""
    headline_symbols: set[str] = field(default_factory=set)


def company_core(name: str) -> str:
    core = NAME_SUFFIX.sub(" ", name)
    core = re.sub(r"[^A-Za-z0-9&' -]", " ", core)
    return " ".join(core.split())


def validate(orders: list[dict], ctx: Context) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    ok: list[dict] = []
    seen_tickers: set[str] = set()
    st = ctx.state
    prices = {t: ctx.closes.get(t, p.avg_cost) for t, p in st.positions.items()}
    equity = st.equity(prices)
    weights = {t: st.positions[t].qty * prices[t] / equity for t in st.positions} if equity else {}

    for i, o in enumerate(orders, 1):
        t = str(o.get("ticker", "")).strip().upper().replace("/", ".")
        o = {**o, "ticker": t}
        where = f"order {i} ({t or 'no ticker'})"
        action = o.get("action")
        if action not in ("set_weight", "close", "extend"):
            errors.append(f"{where}: action must be set_weight, close or extend")
            continue
        if t in seen_tickers:
            errors.append(f"{where}: one order per ticker per session")
            continue
        seen_tickers.add(t)
        held = t in st.positions

        if action in ("close", "extend") and not held:
            errors.append(f"{where}: you do not hold {t}")
            continue

        row = ctx.universe.get(t)
        if ctx.agent.universe == "tech-ten":
            if t not in TECH_TEN:
                errors.append(f"{where}: you may only trade {', '.join(TECH_TEN)}")
                continue
        w_new = o.get("target_weight") if isinstance(o.get("target_weight"), (int, float)) else 0.0
        w_old = weights.get(t, 0.0)
        # Opens, adds to or flips a position: the same evidence rules apply to a long and a short.
        increasing = action == "set_weight" and w_new != 0 and (
            abs(w_new) > abs(w_old) + 1e-9 or (w_old != 0 and (w_new > 0) != (w_old > 0)))
        shorting = increasing and w_new < 0
        if increasing and ctx.agent.universe == "open":
            if not row:
                errors.append(f"{where}: {t} is not a US listing in today's universe. Check the symbol with search_symbols.")
                continue
            if not row["eligible"]:
                errors.append(f"{where}: {t} is not eligible today: {'; '.join(row['reasons'])}")
                continue
        if shorting and not (row and row.get("shortable")):
            errors.append(f"{where}: {t} cannot be shorted: Alpaca does not list it as shortable and easy to borrow")
            continue
        if row and row.get("market_cap"):
            _, bp = slippage_for_market_cap(row["market_cap"])
        elif held:
            bp = st.positions[t].slippage_bp
        elif ctx.agent.universe == "tech-ten":
            bp = 10
        else:
            _, bp = slippage_for_market_cap(None)
        o["slippage_bp"] = bp

        if action == "close":
            ok.append(o)
            weights[t] = 0.0
            continue

        problems = []
        if action == "set_weight":
            w = o.get("target_weight")
            if not isinstance(w, (int, float)) or not -1 <= w <= 1 or w == 0:
                problems.append("target_weight must be from -1 to 1 and not 0: positive is long, negative is short "
                                "(use close to exit completely)")
        short_after = (w_new < 0) if action == "set_weight" else (held and st.positions[t].short)
        for k, lo, hi, label in (("stop_pct", 0, 100, "stop_pct must be between 0 and 100"),
                                 ("target_pct", 0, 100 if short_after else 10_000,
                                  "target_pct must be between 0 and 100 for a short (a price cannot fall below zero)"
                                  if short_after else "target_pct must be above 0"),
                                 ("probability", -1e-9, 1 + 1e-9, "probability must be between 0 and 1")):
            v = o.get(k)
            if not isinstance(v, (int, float)) or not lo < v < hi:
                problems.append(label)
        h = o.get("horizon_days")
        if not isinstance(h, int) or not 1 <= h <= 252:
            problems.append("horizon_days must be a whole number of trading days from 1 to 252")
        if not str(o.get("thesis", "")).strip():
            problems.append("thesis is empty")

        if ctx.agent.news and increasing:
            srcs = [norm(u) for u in o.get("sources") or [] if str(u).strip()]
            if not any(u in ctx.read_ok_urls for u in srcs):
                problems.append("cite at least one URL you read successfully with read_page this session")
            unknown = [u for u in srcs if u not in ctx.read_ok_urls and u not in ctx.seen_urls]
            if unknown:
                problems.append("these sources never appeared in this session's search results, digest or read_page: "
                                + ", ".join(unknown[:3]))
        if ctx.agent.causal_chain and increasing:
            chain = o.get("causal_chain") or []
            if len(chain) < 2 or any(not str(c.get("step", "")).strip() for c in chain):
                problems.append("weird-links positions need a causal chain of at least two steps")
            if ctx.headline_text:
                names = [t] + ([company_core(row["name"])] if row and row.get("name") else [])
                for n in names:
                    if len(n) < 2:
                        continue
                    flags = 0 if n == t else re.I
                    if re.search(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])", ctx.headline_text, flags) \
                            or t in ctx.headline_symbols:
                        problems.append(f"{t} ({n}) is named in today's digest headlines; weird-links must find "
                                        "companies the news does not name")
                        break
        if problems:
            errors.append(f"{where}: " + "; ".join(problems))
            continue
        ok.append(o)
        if action == "set_weight":
            weights[t] = float(o["target_weight"])

    total = sum(abs(w) for w in weights.values())
    if total > 1.0 + 1e-6:
        errors.append(f"longs plus shorts would come to {total:.1%} of equity; the absolute weights of all "
                      "holdings, named or not, must sum to at most 100% (no leverage)")
        ok = [o for o in ok if o["action"] != "set_weight"]
    answered = {o["ticker"] for o in ok}
    missing = sorted(ctx.expired - answered)
    if missing:
        errors.append("these positions have passed their horizon and need a close, extend or set_weight order: "
                      + ", ".join(missing))
    return ok, errors
