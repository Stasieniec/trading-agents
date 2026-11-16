"""US economic releases with their actual, consensus and previous figures, from Nasdaq's public calendar.

A release appears before it happens with its consensus and the previous figure; the actual fills in
once it is out. Nasdaq labels its time field "gmt", but the times are New York time (jobless claims show
as 08:30)."""

import html
import re
from datetime import date

import httpx

from .secrets import redact

URL = "https://api.nasdaq.com/api/calendar/economicevents"


def _clean(x) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(x or ""))).strip()


def fetch(day: date) -> list[dict]:
    r = httpx.get(URL, params={"date": day.isoformat()}, timeout=20.0,
                  headers={"User-Agent": "Mozilla/5.0 (research project)", "Accept": "application/json"})
    r.raise_for_status()
    rows = (r.json().get("data") or {}).get("rows") or []
    out = []
    for row in rows:
        if _clean(row.get("country")) != "United States":
            continue
        out.append({"date": day.isoformat(), "time": _clean(row.get("gmt")), "event": redact(_clean(row.get("eventName"))),
                    "actual": _clean(row.get("actual")), "consensus": _clean(row.get("consensus")),
                    "previous": _clean(row.get("previous"))})
    return out


def render(rows: list[dict]) -> str:
    if not rows:
        return "No US releases listed."
    lines = ["date | time (New York) | release | actual | consensus | previous"]
    for r in rows:
        lines.append(" | ".join([r["date"], r["time"] or "n/a", r["event"], r["actual"] or "not out yet",
                                 r["consensus"] or "n/a", r["previous"] or "n/a"]))
    return "\n".join(lines)
