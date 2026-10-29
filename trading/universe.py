"""The daily universe: every US listing from the Nasdaq screener, cross-checked with Alpaca.

The full snapshot (names, sectors, market caps) stays in .cache, which Actions keeps between runs.
Only a compact list of eligible tickers and their size bucket is committed, so the random-picks
band can be drawn from what was actually eligible on each day.
"""

import csv
import json
import re
from datetime import date

import httpx

from .config import CACHE_DIR, DATA_DIR, MIN_MARKET_CAP, MIN_PRICE, slippage_for_market_cap

NASDAQ_URL = "https://api.nasdaq.com/api/screener/stocks"
EXCLUDE_NAME = re.compile(
    r"\b(warrants?|units?|rights?|preferred|notes due|debentures?|subordinated|"
    r"depositary shares,? each representing|contingent value)\b|\d+(\.\d+)?%", re.I)
TRADABLE_EXCHANGES = {"NASDAQ", "NYSE", "ARCA", "AMEX", "BATS", "NYSEARCA"}

SNAPSHOT_DIR = CACHE_DIR / "universe"
COMPACT_DIR = DATA_DIR / "universe"


def _num(s) -> float | None:
    if s in (None, "", "NA", "N/A"):
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").replace("%", ""))
    except ValueError:
        return None


def fetch_nasdaq() -> list[dict]:
    r = httpx.get(NASDAQ_URL, params={"tableonly": "true", "download": "true", "limit": 10000},
                  headers={"User-Agent": "Mozilla/5.0 (research project)", "Accept": "application/json"},
                  timeout=60.0)
    r.raise_for_status()
    rows = (r.json().get("data") or {}).get("rows") or []
    out = []
    for row in rows:
        sym = (row.get("symbol") or "").strip().upper().replace("/", ".").replace("^", ".P")
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "name": (row.get("name") or "").strip(),
            "price": _num(row.get("lastsale")),
            "market_cap": _num(row.get("marketCap")),
            "sector": (row.get("sector") or "").strip(),
            "industry": (row.get("industry") or "").strip(),
            "country": (row.get("country") or "").strip(),
            "pct_change": _num(row.get("pctchange")),
        })
    return out


def build(nasdaq_rows: list[dict], alpaca_assets: list[dict] | None) -> list[dict]:
    tradable = None
    if alpaca_assets:
        tradable = {a["symbol"].upper(): a for a in alpaca_assets
                    if a.get("tradable") and a.get("status") == "active"
                    and a.get("exchange", "").upper() in TRADABLE_EXCHANGES}
    out = []
    for r in nasdaq_rows:
        reasons = []
        if EXCLUDE_NAME.search(r["name"]):
            reasons.append("not a common stock or ADR")
        if tradable is not None and r["symbol"] not in tradable:
            reasons.append("not an active Alpaca-listed US equity")
        if r["price"] is None or r["price"] < MIN_PRICE:
            reasons.append(f"price under ${MIN_PRICE:.0f}")
        if r["market_cap"] is None or r["market_cap"] < MIN_MARKET_CAP:
            reasons.append("market cap under $300M")
        bucket, _ = slippage_for_market_cap(r["market_cap"])
        a = (tradable or {}).get(r["symbol"]) or {}
        # Shorts need Alpaca to say the stock is both shortable and easy to borrow.
        out.append({**r, "eligible": not reasons, "reasons": reasons, "bucket": bucket,
                    "shortable": bool(a.get("shortable") and a.get("easy_to_borrow"))})
    return out


def save(day: date, universe: list[dict]) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SNAPSHOT_DIR / "latest.json").write_text(json.dumps({"date": day.isoformat(), "rows": universe}))
    COMPACT_DIR.mkdir(parents=True, exist_ok=True)
    with open(COMPACT_DIR / f"{day.isoformat()}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "bucket", "shortable"])
        for r in sorted(universe, key=lambda r: r["symbol"]):
            if r["eligible"]:
                w.writerow([r["symbol"], r["bucket"], int(bool(r.get("shortable")))])


class Universe:
    def __init__(self, rows: list[dict], as_of: str):
        self.as_of = as_of
        self.rows = {r["symbol"]: r for r in rows}

    @classmethod
    def load(cls) -> "Universe":
        p = SNAPSHOT_DIR / "latest.json"
        if p.exists():
            j = json.loads(p.read_text())
            return cls(j["rows"], j["date"])
        # Fall back to the newest committed compact list: eligibility works, names do not.
        files = sorted(COMPACT_DIR.glob("*.csv"))
        if not files:
            return cls([], "none")
        rows = []
        with open(files[-1]) as f:
            for r in csv.DictReader(f):
                rows.append({"symbol": r["symbol"], "name": "", "price": None, "market_cap": None,
                             "sector": "", "industry": "", "eligible": True, "reasons": [],
                             "bucket": r["bucket"], "shortable": r.get("shortable") == "1"})
        return cls(rows, files[-1].stem)

    def get(self, symbol: str) -> dict | None:
        return self.rows.get(symbol.upper())

    def search(self, query: str = "", sector: str = "", industry: str = "", limit: int = 25) -> list[dict]:
        q, s, ind = query.lower().strip(), sector.lower().strip(), industry.lower().strip()
        hits = []
        for r in self.rows.values():
            if s and s not in r["sector"].lower():
                continue
            if ind and ind not in r["industry"].lower():
                continue
            if q:
                sym_hit = r["symbol"].lower() == q
                name_hit = q in r["name"].lower()
                text_hit = q in r["industry"].lower() or q in r["sector"].lower()
                if not (sym_hit or name_hit or text_hit):
                    continue
                score = 0 if sym_hit else 1 if name_hit else 2
            else:
                score = 1
            hits.append((score, -(r["market_cap"] or 0), r))
        hits.sort(key=lambda h: (h[0], h[1]))
        return [h[2] for h in hits[:limit]]
