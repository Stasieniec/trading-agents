"""Alpaca market data on the free Basic plan, plus the asset list from the trading API.

Errors never carry request headers: httpx prints them in clear, and the secret key is one.
"""

import os
import time
from datetime import date, datetime, timedelta

import httpx

from .secrets import redact
from .timeutil import UTC

DATA = "https://data.alpaca.markets"
TRADING_BASES = ["https://paper-api.alpaca.markets", "https://api.alpaca.markets"]


class DataError(Exception):
    pass


class Alpaca:
    def __init__(self, key: str | None = None, secret: str | None = None):
        key = key or os.environ.get("ALPACA_KEY", "")
        secret = secret or os.environ.get("ALPACA_SECRET", "")
        if not key or not secret:
            raise DataError("Alpaca keys missing (ALPACA_KEY, ALPACA_SECRET)")
        self._client = httpx.Client(
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
            timeout=30.0,
        )

    def _get(self, url: str, params: dict | None = None) -> dict | list:
        for attempt in range(4):
            try:
                r = self._client.get(url, params=params)
            except httpx.HTTPError as e:
                if attempt == 3:
                    raise DataError(f"network error on {url.split('?')[0]}: {type(e).__name__}") from None
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt + 1)
                continue
            if r.status_code != 200:
                body = redact(r.text[:200])
                raise DataError(f"HTTP {r.status_code} on {url.split('?')[0]}: {body}")
            return r.json()
        raise DataError(f"gave up on {url.split('?')[0]} after retries")

    def _paged(self, url: str, params: dict, key: str) -> dict:
        """Merge paginated {key: {symbol: [items]}} responses."""
        out: dict[str, list] = {}
        params = dict(params)
        while True:
            j = self._get(url, params)
            for sym, items in (j.get(key) or {}).items():
                out.setdefault(sym, []).extend(items)
            tok = j.get("next_page_token")
            if not tok:
                return out
            params["page_token"] = tok

    @staticmethod
    def _chunks(symbols: list[str], n: int = 100):
        symbols = sorted(set(symbols))
        for i in range(0, len(symbols), n):
            yield symbols[i:i + n]

    def daily_bars(self, symbols: list[str], start: date, end: date, adjustment: str = "raw") -> dict[str, list[dict]]:
        """Daily SIP bars keyed by symbol, each bar with a 'date' field, oldest first.

        end is clipped to now minus 16 minutes, since the free plan blocks the latest 15.
        """
        latest = datetime.now(UTC) - timedelta(minutes=16)
        end_ts = min(datetime(end.year, end.month, end.day, 23, 59, tzinfo=UTC), latest)
        out: dict[str, list[dict]] = {}
        for chunk in self._chunks(symbols):
            res = self._paged(f"{DATA}/v2/stocks/bars", {
                "symbols": ",".join(chunk), "timeframe": "1Day",
                "start": start.isoformat(), "end": end_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "adjustment": adjustment, "feed": "sip", "limit": 10000,
            }, "bars")
            for sym, bars in res.items():
                for b in bars:
                    b["date"] = b["t"][:10]
                out[sym] = sorted(bars, key=lambda b: b["t"])
        return out

    def opening_auctions(self, symbols: list[str], start: date, end: date) -> dict[str, dict[str, float]]:
        """Official opening auction price per symbol per date, where Alpaca has one."""
        out: dict[str, dict[str, float]] = {}
        latest = datetime.now(UTC) - timedelta(minutes=16)
        end_ts = min(datetime(end.year, end.month, end.day, 23, 59, tzinfo=UTC), latest)
        for chunk in self._chunks(symbols):
            res = self._paged(f"{DATA}/v2/stocks/auctions", {
                "symbols": ",".join(chunk), "start": start.isoformat(),
                "end": end_ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "feed": "sip", "limit": 10000,
            }, "auctions")
            for sym, days in res.items():
                for day in days:
                    price = _official_open(day.get("o") or [])
                    if price:
                        out.setdefault(sym, {})[day["d"][:10]] = price
        return out

    def first_minute_open(self, symbols: list[str], after: datetime) -> dict[str, float]:
        """Open of the first one-minute SIP bar starting at or after a moment, per symbol."""
        start = after.replace(second=0, microsecond=0)
        if start < after:
            start += timedelta(minutes=1)
        out: dict[str, float] = {}
        for chunk in self._chunks(symbols):
            res = self._paged(f"{DATA}/v2/stocks/bars", {
                "symbols": ",".join(chunk), "timeframe": "1Min", "feed": "sip", "adjustment": "raw",
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 10000,
            }, "bars")
            for sym, bars in res.items():
                bars = sorted(bars, key=lambda b: b["t"])
                if bars:
                    out[sym] = float(bars[0]["o"])
        return out

    def corporate_actions(self, symbols: list[str], start: date, end: date) -> list[dict]:
        """Flattened corporate actions, each with 'kind' and 'id'."""
        if not symbols:
            return []
        out = []
        for chunk in self._chunks(symbols, 50):
            params = {"symbols": ",".join(chunk), "start": start.isoformat(), "end": end.isoformat(), "limit": 1000}
            while True:
                j = self._get(f"{DATA}/v1/corporate-actions", params)
                for kind, items in (j.get("corporate_actions") or {}).items():
                    for it in items:
                        it["kind"] = kind
                        out.append(it)
                tok = j.get("next_page_token")
                if not tok:
                    break
                params["page_token"] = tok
        uniq = {a.get("id") or f"{a['kind']}:{a.get('symbol')}:{a.get('ex_date')}": a for a in out}
        return list(uniq.values())

    def news(self, start: datetime, end: datetime, pages: int = 8, include_content: bool = False) -> list[dict]:
        """Up to pages x 50 stories in the window, newest first."""
        params = {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "limit": 50, "sort": "desc", "include_content": "true" if include_content else "false"}
        out = []
        for _ in range(pages):
            j = self._get(f"{DATA}/v1beta1/news", params)
            out += j.get("news", [])
            tok = j.get("next_page_token")
            if not tok:
                break
            params["page_token"] = tok
        return out

    def most_actives(self, top: int = 20) -> list[dict]:
        j = self._get(f"{DATA}/v1beta1/screener/stocks/most-actives", {"by": "volume", "top": top})
        return j.get("most_actives", [])

    def movers(self, top: int = 20) -> dict:
        return self._get(f"{DATA}/v1beta1/screener/stocks/movers", {"top": top})

    def latest_trades(self, symbols: list[str]) -> dict[str, dict]:
        out = {}
        for chunk in self._chunks(symbols):
            j = self._get(f"{DATA}/v2/stocks/trades/latest", {"symbols": ",".join(chunk), "feed": "iex"})
            out.update(j.get("trades", {}))
        return out

    def assets(self) -> list[dict]:
        last = None
        for base in TRADING_BASES:
            try:
                return self._get(f"{base}/v2/assets", {"status": "active", "asset_class": "us_equity"})
            except DataError as e:
                last = e
        raise last


def _official_open(prints: list[dict]) -> float | None:
    """Pick the official opening print: condition Q (official open) or O (opening print) first."""
    for want in ("Q", "O"):
        for p in prints:
            if want in str(p.get("c", "")) and p.get("p"):
                return float(p["p"])
    for p in prints:
        if p.get("p"):
            return float(p["p"])
    return None


def bar_is_sane(b: dict) -> bool:
    try:
        lo, hi = float(b["l"]), float(b["h"])
        return lo > 0 and lo <= float(b["o"]) <= hi and lo <= float(b["c"]) <= hi
    except (KeyError, TypeError, ValueError):
        return False
