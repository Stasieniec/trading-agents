"""Every number the experiment runs on, in one place. See docs/PLAN.md for where each came from."""

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site-data"
CACHE_DIR = ROOT / ".cache"
PROMPTS_DIR = ROOT / "trading" / "prompts"
EXPERIMENT_FILE = DATA_DIR / "experiment.json"

REPO = "Stasieniec/trading-agents"

MODEL = "claude-sonnet-5-5"
HELPER_MODEL = "claude-haiku-5-5"
EFFORT = "high"
HELPER_EFFORT = "low"

# USD per million tokens, from platform.claude.com pricing, read 2026-10-28.
PRICES = {
    "claude-sonnet-5-5": {"input": 2.00, "cache_write": 2.50, "cache_read": 0.10, "output": 10.00},
    "claude-haiku-5-5": {"input": 0.10, "cache_write": 0.125, "cache_read": 0.01, "output": 0.50},
}
HAIKU_LONG_PROMPT_TOKENS = 100_000  # Haiku 5.5 bills 5x above this prompt size
HAIKU_LONG_MULTIPLIER = 5.0
WEB_SEARCH_USD = 0.01  # $10 per 1,000 searches

SOFT_CAP_USD = 0.90
HARD_CAP_USD = 2.00
MONTHLY_CAP_USD = 95.0
MAX_TURNS = 40
MAX_SESSION_MINUTES = 25
DEADLINE_BEFORE_OPEN_MIN = 3
MIN_LEAD_BEFORE_OPEN_MIN = 30
LOCAL_TZ = "Europe/Amsterdam"
LOCAL_START = (13, 30)
WEB_SEARCH_MAX_USES = 8
READ_PAGE_MAX_CALLS = 10

START_CASH = 100_000.0
MIN_PRICE = 5.0
MIN_MARKET_CAP = 300e6
MIN_TRADE_USD = 100.0  # smaller rebalances are skipped as dust

# Slippage per side, basis points, by market cap at decision time.
SLIPPAGE_BUCKETS = [(10e9, "large", 10), (2e9, "mid", 25), (MIN_MARKET_CAP, "small", 50)]
BENCHMARK_SLIPPAGE_BP = 10

TECH_TEN = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD", "PLTR"]
BENCHMARKS = {
    "spy": {"label": "SPY buy and hold", "weights": {"SPY": 1.0}},
    "qqq": {"label": "QQQ buy and hold", "weights": {"QQQ": 1.0}},
    "tech-ten-ew": {"label": "Tech ten, equal weight", "weights": {t: 0.1 for t in TECH_TEN}},
}

NOTE_CAPS_WORDS = {"notes": 2000, "ticker": 1500}
TICKER_LOG_KEEP = 15


@dataclass(frozen=True)
class AgentConfig:
    name: str
    label: str
    description: str
    news: bool  # headlines, web search, page reading
    universe: str  # "open" or "tech-ten"
    causal_chain: bool = False  # weird-links: must explain the chain, ticker not in headlines
    tools: tuple = field(default=())


AGENTS = {
    "open-quality": AgentConfig(
        "open-quality", "Open universe, quality",
        "Any eligible US stock. A few well-researched trades from the day's news.",
        news=True, universe="open"),
    "tech-ten": AgentConfig(
        "tech-ten", "Tech ten",
        "Same tools and news, but only " + ", ".join(TECH_TEN) + ".",
        news=True, universe="tech-ten"),
    "weird-links": AgentConfig(
        "weird-links", "Weird links",
        "Any eligible US stock. Second-order effects: events traced to a company the news never names.",
        news=True, universe="open", causal_chain=True),
    "no-news": AgentConfig(
        "no-news", "No news",
        "Same prompt as open universe, but no headlines and no web. Prices, movers and memory only.",
        news=False, universe="open"),
}


def slippage_for_market_cap(market_cap: float | None) -> tuple[str, int]:
    if market_cap is None:
        return "small", SLIPPAGE_BUCKETS[-1][2]
    for floor, name, bp in SLIPPAGE_BUCKETS:
        if market_cap >= floor:
            return name, bp
    return "small", SLIPPAGE_BUCKETS[-1][2]
