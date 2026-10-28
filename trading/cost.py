"""What each API call cost, from its usage block, and what the month has cost so far."""

import json
from datetime import date

from .config import (AGENTS_DIR, DATA_DIR, HAIKU_LONG_MULTIPLIER, HAIKU_LONG_PROMPT_TOKENS, PRICES,
                     WEB_SEARCH_USD)


def _get(u, name, default=0):
    if isinstance(u, dict):
        return u.get(name) or default
    return getattr(u, name, None) or default


def call_cost(model: str, usage) -> float:
    p = PRICES[model]
    inp = _get(u := usage, "input_tokens")
    cw = _get(u, "cache_creation_input_tokens")
    cr = _get(u, "cache_read_input_tokens")
    out = _get(u, "output_tokens")
    mult = 1.0
    if model.startswith("claude-haiku") and inp + cw + cr > HAIKU_LONG_PROMPT_TOKENS:
        mult = HAIKU_LONG_MULTIPLIER
    usd = mult * (inp * p["input"] + cw * p["cache_write"] + cr * p["cache_read"] + out * p["output"]) / 1e6
    stu = _get(u, "server_tool_use", None)
    if stu:
        usd += _get(stu, "web_search_requests") * WEB_SEARCH_USD
    return usd


def month_spend(today: date) -> float:
    """Every recorded API cost this calendar month: sessions, dry runs, digest summaries."""
    prefix = today.strftime("%Y-%m")
    total = 0.0
    for p in list(AGENTS_DIR.glob(f"*/sessions/{prefix}-*/usage.json")) + \
            list((DATA_DIR / "dryruns").glob(f"{prefix}-*/*/usage.json")) + \
            list((DATA_DIR / "evals").glob(f"{prefix}-*/*/usage.json")):
        try:
            total += json.loads(p.read_text()).get("total_cost", 0.0)
        except (OSError, ValueError):
            pass
    for p in list((DATA_DIR / "digest").glob(f"{prefix}-*.json")) + \
            list((DATA_DIR / "dryruns").glob(f"{prefix}-*/digest.json")):
        try:
            u = json.loads(p.read_text()).get("usage") or {}
            total += u.get("cost", 0.0)
        except (OSError, ValueError):
            pass
    return total
