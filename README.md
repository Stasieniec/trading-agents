# trading-agents

A live paper-trading experiment: Claude agents trade fake money once a day, before the US open,
against real prices. Dashboard: https://trading.swasilewski.com

Plan and every design decision: [docs/PLAN.md](docs/PLAN.md).

- `agents/<name>/` each agent's prompt, markdown memory, session logs and ledger
- `trading/` the harness, market simulation, data sources and site builder
- `data/` daily digests, eligible-universe lists, benchmark ledgers
- `site-data/` JSON the dashboard reads
- `dashboard/` the Cloudflare Worker that serves the dashboard

Workflows: `session` (before the open), `mark` (after the close), `tests`, `check-sources`.
Run a dry run from the Actions tab: session, Run workflow, dry run ticked.
