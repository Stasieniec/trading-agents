"""NYSE calendar and the two clocks this experiment lives on."""

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

NY = ZoneInfo("America/New_York")
UTC = timezone.utc


@lru_cache(maxsize=1)
def _cal():
    return xcals.get_calendar("XNYS")


def now_utc() -> datetime:
    return datetime.now(UTC)


def is_trading_day(d: date) -> bool:
    return _cal().is_session(d.isoformat())


def session_times(d: date) -> tuple[datetime, datetime]:
    """Open and close of a trading day, in UTC."""
    cal = _cal()
    o = cal.session_open(d.isoformat()).to_pydatetime()
    c = cal.session_close(d.isoformat()).to_pydatetime()
    return o.astimezone(UTC), c.astimezone(UTC)


def trading_days(start: date, end: date) -> list[date]:
    """Trading days from start to end, inclusive."""
    if end < start:
        return []
    sessions = _cal().sessions_in_range(start.isoformat(), end.isoformat())
    return [s.date() for s in sessions]


def next_trading_day(d: date) -> date:
    x = d + timedelta(days=1)
    while not is_trading_day(x):
        x += timedelta(days=1)
    return x


def previous_trading_day(d: date) -> date:
    x = d - timedelta(days=1)
    while not is_trading_day(x):
        x -= timedelta(days=1)
    return x


def add_trading_days(d: date, n: int) -> date:
    x = d
    for _ in range(n):
        x = next_trading_day(x)
    return x


def trading_days_between(a: date, b: date) -> int:
    """Number of trading days after a, up to and including b."""
    if b <= a:
        return 0
    return len(trading_days(a + timedelta(days=1), b))


def last_closed_day(now: datetime, delay_min: int = 16) -> date | None:
    """Latest trading day whose close (plus the data delay) has passed."""
    d = now.astimezone(NY).date()
    for _ in range(10):
        if is_trading_day(d):
            _, close = session_times(d)
            if now >= close + timedelta(minutes=delay_min):
                return d
        d -= timedelta(days=1)
    return None


def next_open(now: datetime) -> tuple[date, datetime]:
    """The next opening bell at or after now."""
    d = now.astimezone(NY).date()
    for _ in range(10):
        if is_trading_day(d):
            o, _ = session_times(d)
            if o > now:
                return d, o
        d += timedelta(days=1)
    raise RuntimeError("no open found within 10 days")
