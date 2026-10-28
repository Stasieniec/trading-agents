# trading-agents: build plan

A live paper-trading experiment. Claude agents trade fake money once a day, before the US open,
and a public dashboard at trading.swasilewski.com shows how each one is doing against plain
benchmarks.

Hypothesis under test: from recent news, an LLM agent can make trading decisions that profit over
days or weeks.

Status: built 2026-10-28, live from Thursday 2026-10-29. Revised before the build after three
independent reviews (experiment validity, security, feasibility).

## Decisions already made

- Fake money only. Our own ledger keeps the books; real prices come from Alpaca's free market data.
- All agents use Sonnet 5.5, with Haiku 5.5 as a helper that reads web pages and returns short
  answers. Same model everywhere, so the comparison measures the strategy rather than the model.
- Agents run before the US open, from 13:30 Amsterdam time, and their orders fill at that day's
  opening auction.
- Long-only, no leverage, no shorting.
- Open-universe agents may buy US-listed common stocks and ADRs only, price at least $5 and market
  cap at least $300M at decision time.
- The tech-ten agent's list: NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, AVGO, AMD, PLTR.
- Repo and dashboard are public.
- Budget: $100 of API credits per month, refreshed monthly.
- Starting capital $100,000 per agent, zero commission. Slippage per side by market cap at
  decision time: 10 bp above $10B, 25 bp from $2B to $10B, 50 bp from $300M to $2B. Applied to
  every fill, stop and target exits included.
- Cost caps: soft $0.90 and hard $2.00 per session, $95 per month across everything.
- Trading days only. Monday's session reads the weekend's news.
- No position size cap beyond long-only and no negative cash: the agent sizes its own bets.
- Expired horizons never close automatically; the agent must close or re-justify each one.

## The agents

| Folder | What it is |
|---|---|
| `agents/open-quality/` | Open universe. Few, well-researched trades. Starts from the daily digest, has web search and page reading. |
| `agents/tech-ten/` | Same tools and digest, but may only hold the ten stocks above. |
| `agents/weird-links/` | Open universe. Hunts second-order effects: connects events across sources to a stock the news does not mention. Every buy carries a written causal chain with a source per link, and code rejects a buy whose ticker or company name appears in that day's digest headlines. |
| `agents/no-news/` | Same prompt as open-quality, but no headlines, no web search, no page reading. It gets the price-only part of the digest (index and sector moves, top movers, most-actives) so it can still discover tickers the same way, plus prices, history, symbol search and its own memory. If it does as well as open-quality, the news is not what is driving results. |

Benchmarks, computed by code at no API cost:

- SPY buy-and-hold, QQQ buy-and-hold, the tech ten equal-weighted and held. Bought at the opening
  auction of day one with the same slippage rule, dividends credited.
- An exposure-matched SPY line per agent: the agent's invested fraction each day times SPY's
  return, the rest in cash. A "few trades" agent sitting mostly in cash looks brilliant in a
  falling market and poor in a rising one; this line separates that from stock picking.
- A random-picks band per agent, added after the first week: keep the agent's real trade dates,
  weights, holding periods and stop/target distances, swap each ticker for a random one from the
  same market-cap bucket of that day's eligible universe (tech-ten draws from the ten), repeat
  1,000 times, and show the 5th to 95th percentile and where the agent ranks.

## Daily timeline

All times Amsterdam unless stated. GitHub cron is UTC and can run late or get dropped, so the
session job has several firings, off the top of the hour, and the script decides whether to act.

1. **Session job, cron 11:37, 12:32, 12:37, 12:44, 12:52 and 13:07 UTC on weekdays, plus manual dispatch.**
   A firing proceeds only if: today is an NYSE trading day (Alpaca calendar), the Amsterdam time is
   past 13:30, the next open (Alpaca clock) is at least 30 minutes away, and today's session has
   not already run. That leaves two or three usable firings every day of the year, including the
   DST-mismatch weeks. Each agent session has a hard deadline three minutes before the open; a
   session that hits it becomes a hold. So nothing ever needs an intraday fill. The job then:
   1. Runs the marking step for any trading day not yet marked, in date order (idempotent).
   2. Builds and commits the day's digest, frozen, identical for every agent that gets it.
   3. Runs the four agents as a matrix, `fail-fast: false`, so one failure does not block the others.
   4. Each agent commits only its own folder: decision, memory changes, session log.
2. **US open.** Nothing runs. Orders wait.
3. **Marking job, cron 21:47 and 23:17 UTC on weekdays,** after the close plus Alpaca's 15-minute
   delay on full-market data. In this order:
   1. Corporate actions: fetch a trailing 10 days from `/v1/corporate-actions` (entries can arrive
      late) and apply each one once, keyed by its id. Splits adjust share counts, cost basis,
      stop and target levels and pending orders. Cash dividends are credited on the ex-date.
   2. Fills: pending orders fill at the primary-exchange opening auction price
      (`/v2/stocks/auctions`), falling back to the daily bar's open when there is none. Bars whose
      open or close lies outside their high-low range are rejected. Shares are sized from equity
      marked at that open divided by the fill price, sells before buys.
   3. Stops and targets, from the fill day on (below).
   4. Marks every portfolio and benchmark to the close, writes the equity series, sums spend.
   5. Writes the dashboard data files and commits.

### Order and exit rules

- An order names a ticker and a target weight. Holdings an agent does not name keep their share
  count; only named tickers trade. The validator checks the whole resulting book: weights sum to
  at most 1, no negative cash. An empty order list is a normal outcome and the prompt says so.
- Stops and targets are percentages from the fill price (for example stop 8% below, target 15%
  above), so a gap at the open can never produce a same-bar round trip. Code checks them every
  trading day from the fill day on: if the day's low reaches the stop, the position exits at the
  stop, or at the open if it gapped through. Same for the target on the high. If both are touched
  on the same day, the stop wins. Slippage applies to these exits too.
- Each buy carries a horizon in trading days. When it passes, code does not close the position.
  The agent's next session lists it as expired, and `submit_decision` is rejected until every
  expired position has an explicit answer: close it, or extend it with a fresh thesis, horizon,
  stop and target. So no position sits around unexamined. The original thesis and date stay
  visible next to every extension, and the dashboard shows how often each agent extends.
- A ticker with no bar on a trading day (halted) leaves its order unfilled and tells the agent.
  A delisting settles at the last price or merger terms.

## Data sources

| What | Source | Notes |
|---|---|---|
| Daily bars, opening auctions, corporate actions, news (Benzinga), most-actives, movers | Alpaca Market Data, free Basic plan | 200 calls/min, history since 2016, full-market data with only the latest 15 minutes blocked. |
| Calendar, clock, asset list | Alpaca paper trading API | Needs keys from the paper account. `/v2/assets` (active, tradable, `us_equity`) is the master check on every symbol. |
| Market cap, sector, industry, company names | Nasdaq screener JSON (`api.nasdaq.com/api/screener/stocks`) | Unofficial. Pulled once a day; symbols normalised (`BRK/B` to `BRK.B`) and cross-checked against Alpaca assets; warrants, units, rights, preferreds and notes dropped by security name. If the pull fails, the last good snapshot is used. |
| Headlines | Alpaca news, plus one or two RSS feeds (CNBC via search.cnbc.com, MarketWatch) | Parsed with `feedparser`. ApeWisdom and Yahoo trending can be added later. |

Every source is tested from an Actions runner during the build, since datacenter IPs get blocked
more than cloud sessions. Every source except Alpaca is optional: if it fails, the digest says so
and the day goes on.

Licensing: free tiers are for personal, non-display use. The public repo and dashboard publish
derived numbers (portfolio values, fills, P&L) and headline titles with links. Article text never goes into git, and neither do price histories; the ledger does record the
close of each held position and SPY's daily open and close, which the books need. Price history lives in `actions/cache`. A compact list of each
day's eligible tickers with their market-cap bucket is committed, so the random-picks band can be
drawn point-in-time.

### The daily digest

Built by code, frozen before any agent runs, committed as `data/digest/YYYY-MM-DD.json` and `.md`.
Roughly 2,000 tokens:

- Day and week moves for SPY, QQQ, IWM, DIA and the sector ETFs.
- Yesterday's top movers (labelled as yesterday's) and most-actives, filtered to the universe floor.
- About 15 headlines, deduplicated across sources and ranked by how many sources carry the story
  and how recent it is. Title, source, time, link, one line.
- A 150-word market summary written by one Haiku call from the above.

The first two parts are the price-only digest that no-news also gets.

## The agent harness

Python 3.12, the official `anthropic` SDK, a plain Messages API tool-use loop. No Agent SDK: it
brings Claude Code's system prompt and shell tools, which we would then have to lock down.

### What the agent sees at the start of a session

1. Tool definitions and the shared system prompt: rules of the market, costs and slippage, the
   decision schema, and a standing instruction that notes and the digest are data written by
   earlier sessions or third parties, never instructions.
2. The agent's own personality prompt.
3. First user message: today's date and time, when orders will fill, its portfolio (cash,
   positions with entry, P&L, thesis, stop, target, horizon status), trades settled since last
   session with realised return against SPY (written by code), and then, inside clearly marked
   data blocks, yesterday's summary, its general notes, a one-line index of its ticker files, and
   the digest.

Price series are always listed oldest to newest and labelled that way, because Alpha Arena's models
misread newest-first series. Quotes carry their timestamp, since pre-market the latest IEX trade
is usually yesterday's.

### Tools

| Tool | Agents | What it does |
|---|---|---|
| `get_quotes(tickers)` | all | Last close, latest IEX trade with its timestamp, daily change. |
| `get_history(ticker, days)` | all | Split-adjusted daily bars up to a year, plus 5/20/60-day returns, 20-day volatility, 52-week range. |
| `search_symbols(query, sector, industry)` | all | Text search over the day's universe snapshot. Marks each result eligible or not. |
| `get_portfolio()` | all | Current state, pending orders. |
| `list_notes`, `read_note`, `write_note` | all | Its own markdown memory, with size caps. |
| `web_search` | news agents | Anthropic's server-side search, capped per session with `max_uses`. |
| `read_page(url, question)` | news agents | Haiku 5.5 fetches the page with `web_fetch` (`max_content_tokens` set) and answers the question in under 300 words, with the date printed on the page or "unknown". Keeps raw pages out of the expensive context. |
| `submit_decision(orders, session_summary)` | all | Ends the session. Strict schema. |

Each order: ticker, target weight, thesis, horizon in trading days, stop and target as
percentages, probability that it beats SPY over the horizon, sources, and for weird-links a causal
chain. Validation:

- The ticker is in Alpaca's asset list and passes the floor, or is one of the ten.
- The resulting book is valid (above).
- News agents: every buy cites at least one URL that was passed to `read_page` and fetched
  successfully in this session. Other cited URLs must come from structured `web_search` results.
  URLs are normalised before matching; text that merely contains a URL does not count. Each
  citation is stored with Haiku's answer and the page date, so stale articles show up.
- Weird-links: the ticker and company name do not appear in the day's digest headlines.

Invalid orders come back with reasons and the agent gets one chance to resubmit. If it never
submits, the day is a hold and the harness writes the summary itself with the reason.

Loop details: handle `pause_turn` from server tools; keep history append-only (tool results are
trimmed before they are first sent, never afterwards, so the cache and thinking blocks stay valid);
effort `high` for the agents and `low` for the Haiku helpers. Dry runs at `medium` produced
sessions of one or two tool calls. A decision submitted before any research tool has been used is
bounced once, after the first dry runs showed agents deciding on turn one.

### Memory

```
agents/<name>/
  prompt.md               personality, written by us
  memory/                 the only place write_note can touch
    summary.md            end-of-session summary, overwritten daily, read first next session
    notes.md              general notes, max ~2,000 words
    tickers/NVDA.md       one per ticker it has researched or traded, max ~1,500 words
  records/NVDA.json       code-owned: entries, exits, realised return against SPY
  sessions/YYYY-MM-DD/
    transcript.jsonl      model and tool calls; price-tool results and page text stripped
    decision.json         validated orders as submitted
    usage.json            tokens and cost per call, session total, prompt hash
  ledger/
    orders.jsonl          every order with its id (agent, date, sequence)
    fills.jsonl           every fill, written only by the marking job
    equity.csv            daily equity
```

A ticker file has `## Current view` (the agent overwrites it) and `## Log` (dated entries; the
harness moves entries beyond the last 15 into an archive file). `read_note` on a ticker returns the
file plus its code-owned record, which the agent cannot write. Facts from code and opinions from
the model stay apart, which is the main defence against memory drifting into a story the agent
tells itself. Writes over the size cap are rejected with a request to condense. Positions, cash and
P&L never live in the notes.

Note names must match `^[A-Z0-9.-]{1,10}$` for tickers or be `notes`/`summary`, and the resolved
path must sit under that agent's `memory/` folder.

Every session records a hash of its prompts. When a prompt changes, the equity curve gets a marker
and the stats are shown per prompt version, so a tweak in week two does not quietly mix two
experiments.

### Cost control

Estimate: $0.40 to $0.90 per Sonnet session, so four agents on about 21 trading days is roughly
$35 to $75 a month. The dry run measures the real figure.

- Automatic prompt caching (top-level `cache_control`), so every turn reads the whole growing
  conversation from cache instead of only the static prefix. The date sits in the first user
  message so it never breaks the cache. Caches last minutes, so nothing carries over between days.
- Per-session cost counted after every model response. At the soft cap the harness tells the
  agent to submit now; at the hard cap the session stops and the day becomes a hold.
- Spend per session is in each `usage.json`. Before a session starts, the harness sums the month's
  files, dry runs included; at $95, sessions are skipped until the next month and the dashboard
  says so. The harness only sees its own spend, so the Console workspace limit is what makes $95
  hold if the key is ever used elsewhere. At the hard cap of $2.00, four agents could in theory
  hit $95 before month end; the dashboard shows the projection so that is visible early.
- Also capped: 40 model turns, 25 minutes, and the deadline three minutes before the open.
- A Console spend limit of $95 a month on the key's workspace, set by Stas.

## Running it

- **GitHub Actions** in the public repo, free. `session.yml` and `mark.yml`, plus
  `workflow_dispatch` on both for manual runs and dry runs.
- One concurrency group shared by both workflows, set at workflow level (on the matrix job it
  would serialise the agents). The queue setting gets checked during the build so a third queued
  run cannot cancel a pending one; since firings are redundant, a cancelled duplicate is harmless.
- Every agent job commits once, at the end. A crash before that commit leaves nothing, so a rerun
  starts clean; a crash after it means the rerun sees the session already exists and skips.
  Order ids are agent plus date plus sequence, and the marking job skips ids already filled, so
  nothing can fill twice.
- Parallel jobs touch only their own folders, so `git pull --rebase` and retry is enough.
- Missed days show on the dashboard: portfolios are marked every trading day whether or not the
  agent ran, and a red banner appears when the newest session is more than one trading day old.
  That also catches GitHub's 60-day schedule shutdown.
- Failure emails go to whoever last changed the cron line or re-enabled the workflow. Commits from
  Claude sessions are not authored as Stas, so once the schedule is live he disables and
  re-enables both workflows in the GitHub UI once.

## Dashboard

A Cloudflare Worker named `trading-agents` on the custom domain trading.swasilewski.com. It serves
the HTML page and the vendored JavaScript (uPlot, marked, DOMPurify, bundled into the Worker
rather than loaded from a CDN) straight from the Worker script, which avoids the static asset
upload that fails behind the cloud-session proxy. The browser fetches the JSON data files directly
from `raw.githubusercontent.com/Stasieniec/trading-agents/main/site-data/`, which allows
cross-origin reads and caches for 5 minutes. No database, no secrets. Data changes need no
redeploy; only page changes do.

- **Overview:** equity curves for the four agents and the benchmarks, rebased to 100. A table per
  agent: total return, excess return against SPY and against the exposure-matched line with a
  plus-minus two standard error range, max drawdown, average invested fraction, trades, turnover,
  slippage paid, days run, API spend. A plain sentence on what this many days, and single runs
  per agent, can and cannot show. No pass or fail labels.
- **Per agent:** positions, trade log with thesis, horizon, sources and outcome, a Brier score for
  the stated probabilities once trades have settled, the latest session summary, general notes and
  ticker files rendered from markdown, a link to every session on GitHub.
- **Comparison:** holdings overlap and daily-return correlation between agents.
- **Health:** missed and failed sessions, spend against the monthly cap.

Rendering model-written text safely: every JSON field goes in with `textContent`. Markdown goes
through DOMPurify restricted to text tags and links; links must be https and get
`rel="nofollow noopener noreferrer ugc"`; no images, styles or forms. Content Security Policy:
`default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'
https://raw.githubusercontent.com; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.

## Keeping the keys safe in a public repo

The model never sees a key, so a prompt injection has nothing to hand over. The work is making
sure the harness never writes one anywhere.

- Keys live only in GitHub Actions secrets: `CLAUDE_API_KEY` (exists), `ALPACA_KEY` and
  `ALPACA_SECRET` (added 2026-10-28).
- Secrets go as environment variables only to the steps that call the APIs. Checkout uses
  `persist-credentials: false`; the GitHub token is given to the push step alone.
- One `redact()` function replaces the exact value of every secret and is applied to every string
  bound for a transcript, a log line or a tool result. Tool errors return a status code and a fixed
  message, never the raw exception (httpx prints the `x-api-key` and Alpaca secret headers in
  clear). No debug logging of the SDK or httpx in Actions.
- At the end of each step that holds secrets, a scan checks its whole output folder for the exact
  secret values; every commit step also scans for key patterns (`sk-ant-` and Alpaca's formats).
  A match fails the job before anything is pushed.
- The agent's writes are confined to its `memory/` folder by path checks, and before committing,
  each job fails if `git diff --cached --name-only` lists anything outside the folder it owns. This
  stops an agent from rewriting harness code that later runs with the keys, or faking its ledger.
- Model output never goes into a `run:` line through `${{ }}` (commit messages included); it is
  passed through files or environment variables.
- Workflows trigger only on `schedule` and `workflow_dispatch`. No pull request triggers.
- Workflow `permissions` default to read; only the jobs that commit get `contents: write`.
- Only first-party actions, pinned by major version tag. Python dependencies locked with hashes.
- No Actions artifacts: on a public repo anyone signed in to GitHub can download them.
- Anthropic is a GitHub secret scanning partner: a leaked `sk-ant-` key found in a public repo is
  reported and deactivated automatically, and the owner gets an email.

What Stas sets by hand:

- GitHub repo settings:
  - Advanced Security: turn on Secret Protection and Push protection, which are off at repository
    level by default.
  - Actions > General: allow only GitHub-authored actions; workflow permissions read-only; untick
    "Allow GitHub Actions to create and approve pull requests"; require approval for fork pull
    request workflows from all outside contributors.
  - Add no collaborators.
- Anthropic Console: a dedicated workspace for this project with a monthly spend limit, the key
  created inside it (never an admin key), and leak notices going to an inbox he reads.
- Alpaca: keys generated from the paper account.
- If a key ever leaks: revoke it. Deleting the commit does not help.

## Build order

1. Repo skeleton: package layout, agent configs, `.gitignore`, `redact()`, the scan scripts,
   workflows with the schedule commented out.
2. Market data layer: Alpaca clients, universe snapshot, calendar, caching. A manual Actions run
   that tests every source from a runner.
3. Ledger and market simulation: corporate actions, fills, slippage, stops and targets, marking,
   benchmarks including the exposure-matched line. Unit tests on the arithmetic, since this is
   where a silent bug would fake a result.
4. Digest builder.
5. Agent harness: the loop, tools, validation, memory tools and path checks, cost caps, logging.
6. The four prompts.
7. Dry run in Actions via manual dispatch: one session per agent, with a low cost cap, to measure
   real spend.
8. Dashboard Worker, deployed to trading.swasilewski.com.
9. Turn the schedule on. Day one is the first trading day after that, when all agents and
   benchmarks start from $100,000.
10. After the first week: the random-picks band, and real spend against the estimate.

Deferred until the basics run: a `research(question)` tool where Haiku runs its own search loop
(overlaps `web_search` plus `read_page`), Reddit and Yahoo trending in the digest.
