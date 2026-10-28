# trading-agents: build plan

A live paper-trading experiment. Claude agents trade fake money once a day, before the US open,
and a public dashboard at trading.swasilewski.com shows how each one is doing against plain
benchmarks.

Hypothesis under test: from recent news, an LLM agent can make trading decisions that profit over
days or weeks.

Status: draft, 2026-10-28. Nothing is built yet.

## Decisions already made

- Fake money only. Our own ledger keeps the books; real prices come from Alpaca's free market data.
- All agents use Sonnet 5.5, with Haiku 5.5 as a helper that reads web pages and returns short
  answers. Same model everywhere, so the comparison measures the strategy rather than the model.
- Agents run before the US open, 13:30 Amsterdam time, and their orders fill at that day's open.
- Long-only, no leverage, no shorting.
- Open-universe agents may buy US-listed stocks only (ADRs allowed), price at least $5 and market
  cap at least $300M at decision time.
- The tech-ten agent's list: NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, AVGO, AMD, PLTR.
- Repo and dashboard are public.
- Budget: $100 of API credits per month, refreshed monthly.
- Starting capital $100,000 per agent, zero commission, 10 basis points of slippage per side.
- Trading days only. Monday's session reads the weekend's news.

## The agents

| Folder | What it is |
|---|---|
| `agents/open-quality/` | Open universe. Few, well-researched trades. Starts from the daily digest, has web search and page reading. |
| `agents/tech-ten/` | Same tools and digest, but may only hold the ten stocks above. |
| `agents/weird-links/` | Open universe. Told to hunt second-order effects: connect events across sources to a stock the headline does not mention. Every buy must carry a written causal chain with a source per link. |
| `agents/no-news/` | Same prompt as open-quality, but no digest, no web search, no page reading. Only prices, history, symbol search and its own memory. If it does as well as open-quality, the news is not what is driving results. |

Benchmarks, computed by code at no API cost:

- SPY buy-and-hold, QQQ buy-and-hold, the tech ten equal-weighted and held. All bought at the
  open of day one with the same slippage rule, dividends credited.
- A random-picks band per agent: keep the agent's real trade dates, weights and holding periods,
  swap the tickers for random ones from the same eligible universe, repeat 1,000 times, and show
  the 5th to 95th percentile and where the agent ranks. Arrives once there are enough trades to
  make it meaningful.

## Daily timeline

All times Amsterdam. GitHub cron is UTC and can run late or get dropped, so each job is scheduled
twice, off the top of the hour, and the script decides whether to act.

1. **Session job, cron 11:37 and 12:37 UTC on weekdays, plus manual dispatch.** The script checks
   the NYSE calendar (Alpaca `/v2/calendar`), that the Amsterdam time is past 13:30, and that
   today's session has not already run. Whichever cron firing passes those checks does the work;
   the other exits. In winter that is the 12:37 UTC firing (13:37 CET), in summer the 11:37 one
   (13:37 CEST). It then:
   1. Runs the marking step first if last night's did not happen (it is idempotent).
   2. Builds and commits the day's digest, frozen, identical for every news agent.
   3. Runs the four agents as a matrix, `fail-fast: false`, so one failure does not block the others.
   4. Each agent commits only its own folder: decision, memory changes, session log.
2. **US open, 15:30 Amsterdam (14:30 in the DST-mismatch weeks).** Nothing runs. Orders wait.
3. **Marking job, cron 21:47 and 23:17 UTC on weekdays.** After the close plus Alpaca's 15-minute
   delay on full-market data:
   1. Fills pending orders at the official open from the daily bar, plus slippage. If a session
      finished after 09:30 New York time, its orders fill at the open of the first one-minute bar
      after the decision timestamp instead. Nothing ever fills at a price the agent already saw.
   2. Applies stops and targets against the day's high and low (below).
   3. Applies splits and cash dividends from Alpaca `/v1/corporate-actions`.
   4. Marks every portfolio and benchmark to the close, writes the equity series.
   5. Writes the dashboard data files and commits.

### Fill and exit rules

- Agents ask for target weights, never share counts. Code converts weights to shares using the
  previous close, sells first, then buys. If cash would go negative at the actual fill price, buys
  are scaled down pro rata. Fractional shares allowed.
- Each buy carries a stop and a target. Code checks them every trading day from the fill day on:
  if the day's low reaches the stop, the position exits at the stop, or at the open if it gapped
  through. Same for the target on the high. If both are touched on the same day, the stop wins.
- Each buy carries a horizon in trading days. When it passes, the agent is told at its next
  session and must either close the position or write a fresh thesis with a new horizon. Code
  does not force the exit.
- A ticker with no bar on a trading day (halted) leaves its order unfilled and tells the agent.
  A delisting settles at the last price or merger terms.

## Data sources

| What | Source | Notes |
|---|---|---|
| Daily and minute bars, calendar, clock, corporate actions, news (Benzinga), most-actives | Alpaca Market Data, free Basic plan | 200 calls/min, history since 2016, full-market bars delayed 15 min, latest quotes IEX only. Keys: `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`. |
| Symbol search, market cap, sector, industry | Nasdaq screener JSON (`api.nasdaq.com/api/screener/stocks`) | One call gives every NASDAQ, NYSE and AMEX listing with name, sector, industry and market cap. Unofficial. Pulled once a day into a local snapshot that the search tool queries. Tested from a cloud session 2026-10-28. |
| Fallback prices | Yahoo chart JSON endpoint | Unofficial, rate-limited on shared IPs. Only used when Alpaca has no bar. |
| Headlines | CNBC RSS (search.cnbc.com), MarketWatch RSS, Nasdaq RSS, Alpaca news | All responded 2026-10-28. |
| Attention | ApeWisdom (Reddit ticker ranks), Yahoo trending tickers, Alpaca most-actives | |

Licensing: free tiers are for personal, non-display use. The public repo and dashboard publish
derived numbers (portfolio values, fills, P&L) and headline titles with links. Raw price tables
and article text never go into git; price history is cached with `actions/cache` instead.

### The daily digest

Built by code, frozen before any agent runs, committed as `data/digest/YYYY-MM-DD.json` and `.md`.
Roughly 2,000 tokens:

- Day and week moves for SPY, QQQ, IWM, DIA and the sector ETFs.
- About 15 headlines, deduplicated across sources and ranked by how many sources carry the story
  and how recent it is. Title, source, time, link, one line.
- Top movers and most-actives that pass the universe floor.
- Top Reddit tickers with rank change, Yahoo trending tickers.
- A 150-word market summary written by one Haiku call from the above.

## The agent harness

Python 3.12, the official `anthropic` SDK, a plain Messages API tool-use loop. No Agent SDK: it
brings Claude Code's system prompt and shell tools, which we would then have to lock down.

### What the agent sees at the start of a session

Order chosen so the cacheable part comes first and never changes between days:

1. Tool definitions and the shared system prompt (rules of the market, costs, the decision schema).
2. The agent's own personality prompt.
3. First user message: today's date and time, when orders will fill, its portfolio (cash,
   positions with entry, P&L, thesis, stop, target, horizon status), trades settled since last
   session with realised return against SPY (written by code), yesterday's summary, its general
   notes, a one-line index of its ticker files, and the digest (news agents only).

Price series are always listed oldest to newest and labelled that way, because Alpha Arena's models
misread newest-first series.

### Tools

| Tool | Agents | What it does |
|---|---|---|
| `get_quotes(tickers)` | all | Last close, latest IEX trade if any, daily change. |
| `get_history(ticker, days)` | all | Daily bars up to a year, plus 5/20/60-day returns, 20-day volatility, 52-week range. |
| `search_symbols(query, sector, industry)` | all | Text search over the day's Nasdaq snapshot. Marks each result eligible or not under the floor. |
| `get_portfolio()` | all | Current state, pending orders. |
| `list_notes`, `read_note`, `write_note` | all | Its own markdown memory, with size caps. |
| `web_search` | news agents | Anthropic's server-side search, capped per session with `max_uses`. |
| `read_page(url, question)` | news agents | Haiku 5.5 fetches the page with `web_fetch` and answers the question in under 300 words, with the page's publish date. Keeps raw pages out of the expensive context. |
| `research(question)` | news agents | Haiku 5.5 runs its own short search-and-read loop and returns an answer with sources. |
| `submit_decision(orders, session_summary)` | all | Ends the session. Strict schema. |

Each order in `submit_decision`: ticker, target weight, thesis, horizon in trading days, stop,
target, probability that it beats SPY over the horizon, sources (URLs), and for weird-links a
causal chain. The harness validates every order: ticker exists and passes the floor (or is in the
ten), weights sum to at most 1, stop below and target above the last price, and for news agents
every cited URL actually appeared in this session's tool results. Invalid orders come back with
reasons and the agent gets one chance to resubmit. If it never submits, the day is a hold and the
harness writes the summary itself with the reason.

### Memory

```
agents/<name>/
  prompt.md               personality, written by us
  memory/
    summary.md            end-of-session summary, overwritten daily, read first next session
    notes.md              general notes, max ~2,000 words
    tickers/NVDA.md       one per ticker it has researched or traded, max ~1,500 words
  sessions/YYYY-MM-DD/
    transcript.jsonl      every model call and tool call, tool results trimmed to 2,000 chars
    decision.json         validated orders as submitted
    usage.json            tokens and cost per call, session total
  ledger/
    orders.jsonl          every order with its id (agent, date, sequence)
    fills.jsonl           every fill, written only by the marking job
    equity.csv            daily equity
```

Each ticker file has three parts: `## Current view` (the agent overwrites it), `## Log` (the
agent appends dated entries; the harness moves entries beyond the last 15 into an archive file),
and `## Record` (written only by code: entries, exits, realised return against SPY). Facts from
code and opinions from the model stay apart, which is the main defence against memory drifting
into a story the agent tells itself. Writes over the size cap are rejected with a request to
condense. Full untrimmed transcripts are kept as Actions artifacts for 90 days.

Positions, cash and P&L never live in the notes. They always come fresh from the ledger.

### Cost control

Estimated $0.35 to $0.80 per session on Sonnet 5.5 with caching, so four agents on about 21
trading days is roughly $30 to $70 a month.

- Prompt caching on the static prefix. The date sits in the first user message so it never breaks
  the cache.
- Per-session cost counted after every model response. At the soft cap the harness tells the
  agent to submit now; at the hard cap the session stops and the day becomes a hold.
- A spend ledger (`data/spend.csv`) checked before each session; once the month's total reaches
  the monthly cap, sessions are skipped and the dashboard says so.
- Also capped: 40 model turns and 25 minutes per session.
- A Console spend limit on the key's workspace as the last line, set by Stas.

## Running it

- **GitHub Actions** in the public repo, free. `session.yml` and `mark.yml` as above, plus
  `workflow_dispatch` on both for manual runs and dry runs.
- A concurrency group shared by both workflows so they never overlap.
- Every agent job commits once, at the end. A crash before that commit leaves nothing, so a rerun
  starts clean; a crash after it means the rerun sees the session already exists and skips.
  Order ids are agent plus date plus sequence, and the marking job skips ids already filled, so
  nothing can fill twice.
- Pushes from parallel jobs touch different folders, so `git pull --rebase` and retry is enough.
- Missed days show on the dashboard: portfolios are marked every trading day whether or not the
  agent ran, and a red banner appears when the newest session is more than one trading day old.
  That also catches GitHub's 60-day schedule shutdown.
- Failed runs email whoever GitHub considers the workflow's owner. To check after the first run.

## Dashboard

A Cloudflare Worker named `trading-agents` on the custom domain trading.swasilewski.com. It serves
one HTML page from the Worker script itself (so no static asset upload, which fails behind the
cloud-session proxy) and passes through the JSON data files from
`raw.githubusercontent.com/Stasieniec/trading-agents/main/site-data/`, cached for 5 minutes. No
database, no secrets. Data changes need no redeploy; only page changes do.

- **Overview:** equity curves for the four agents and three benchmarks, rebased to 100. A table
  per agent: total return, excess return against SPY with a plus-minus two standard error range
  that narrows as days accumulate, max drawdown, trades, days run, API spend. A plain sentence on
  what this many days can and cannot show. No pass or fail labels.
- **Per agent:** positions, trade log with thesis, horizon and outcome, the latest session
  summary, general notes and ticker files rendered from markdown, a link to every session's
  transcript on GitHub.
- **Health:** missed and failed sessions, spend against the monthly cap.

Libraries pinned from jsDelivr: uPlot for charts, marked plus DOMPurify for the markdown.

## Keeping the keys safe in a public repo

- Keys live only in GitHub Actions secrets: `CLAUDE_API_KEY` (exists), `ALPACA_API_KEY_ID` and
  `ALPACA_API_SECRET_KEY` (to add). Never in the repo, never in chat, never in a prompt.
- Secrets are passed as environment variables to the single step that needs them, never at
  workflow level, and never to the checkout or commit steps.
- Workflows trigger only on `schedule` and `workflow_dispatch`. No `pull_request` or
  `pull_request_target` triggers, so nobody can open a pull request that runs code with the keys.
  Only Stas can dispatch.
- Workflow `permissions` default to read; only the jobs that commit get `contents: write`.
- Only first-party actions (`actions/checkout`, `actions/setup-python`, `actions/cache`,
  `actions/upload-artifact`), pinned to commit SHAs.
- The agent has no shell, no code execution on our runner and no tool that reads the environment.
  Its web tools run on Anthropic's servers. A prompt injection on a web page can try to talk it
  into things, but it never has the key to leak.
- Before every commit, a script scans the staged diff for the exact values of every secret in the
  environment and for key patterns (`sk-ant-` and Alpaca's formats). A match fails the job before
  anything is pushed.
- GitHub secret scanning with push protection switched on for the repo.
- `.env` is gitignored for local runs.
- The API key belongs to a dedicated Console workspace with its own spend limit, so even a leaked
  key can burn at most that. Alpaca keys reach a paper account with no money behind it.

## Build order

1. Repo skeleton: package layout, agent configs, `.gitignore`, the secret-scan script, workflows
   with the schedule commented out.
2. Market data layer: Alpaca client, Nasdaq universe snapshot, calendar, caching. Tests against
   recorded responses.
3. Ledger and market simulation: fills, slippage, stops and targets, splits, dividends, marking,
   benchmarks. Unit tests on the arithmetic, since this is where a silent bug would fake a result.
4. Digest builder.
5. Agent harness: the loop, tools, validation, memory tools, cost caps, logging.
6. The four prompts.
7. Dry run in Actions via manual dispatch: one session per agent, with a low cost cap.
8. Dashboard Worker, deployed to trading.swasilewski.com.
9. Turn the schedule on. Day one is the first trading day after that, when all agents and
   benchmarks start from $100,000.
10. After the first week: the random-picks band and a check of real spend against the estimate.

## Still to decide

- Cost caps. Proposed: soft $0.75 and hard $1.00 per session, monthly stop at $80 (leaving room
  for development and the Playground). Numbers are a starting point, not a decision.
- Position size cap. Proposed: none beyond long-only and no negative cash, since "few quality
  trades" may mean concentrated bets. The alternative is a maximum weight per position.
- Whether an expired horizon should close the position automatically. Proposed: no, the agent must
  decide, and the dashboard shows how often it extends a stale thesis.
