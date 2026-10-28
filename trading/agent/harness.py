"""One agent session: a plain Messages API tool-use loop with hard limits on money, turns and time."""

import hashlib
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import anthropic

from ..alpaca import Alpaca
from ..config import (AGENTS_DIR, EFFORT, HARD_CAP_USD, MAX_SESSION_MINUTES, MAX_TURNS, MODEL,
                      PROMPTS_DIR, SOFT_CAP_USD, TECH_TEN, AgentConfig)
from ..cost import call_cost
from ..digest import render
from ..ledger import append_jsonl
from ..market import state_for
from ..secrets import redact
from ..timeutil import UTC
from ..universe import Universe
from .memory import Memory
from .tools import ToolBox, definitions, expired_positions, portfolio_text
from .urls import norm
from .validate import Context, validate


def system_prompt(agent: AgentConfig) -> str:
    shared = (PROMPTS_DIR / "system.md").read_text()
    own = (AGENTS_DIR / agent.name / "prompt.md").read_text()
    return shared.strip() + "\n\n# Your strategy\n\n" + own.strip()


def prompt_hash(agent: AgentConfig) -> str:
    return hashlib.sha256(system_prompt(agent).encode()).hexdigest()[:12]


def _clean_block(b) -> dict:
    d = b.model_dump() if hasattr(b, "model_dump") else dict(b)
    d.pop("signature", None)
    if d.get("type") == "web_search_tool_result" and isinstance(d.get("content"), list):
        d["content"] = [{"url": r.get("url"), "title": r.get("title"), "page_age": r.get("page_age")}
                        for r in d["content"]]
    return d


class Session:
    def __init__(self, agent: AgentConfig, day: date, deadline: datetime, digest: dict | None,
                 universe: Universe, out_dir: Path, client: anthropic.Anthropic | None = None,
                 alpaca: Alpaca | None = None, dry_run: bool = False, hard_cap: float = HARD_CAP_USD,
                 memory_dir: Path | None = None, log=print):
        self.agent, self.day, self.digest, self.universe = agent, day, digest, universe
        self.out = out_dir
        self.dry_run = dry_run
        self.hard_cap = hard_cap
        self.soft_cap = min(SOFT_CAP_USD, hard_cap * 0.6)
        self.deadline = min(deadline, datetime.now(UTC) + timedelta(minutes=MAX_SESSION_MINUTES))
        self.client = client or anthropic.Anthropic(max_retries=3, timeout=300.0)
        self.alpaca = alpaca or Alpaca()
        self.log = lambda m: log(f"[{agent.name}] {m}")
        self.cost = 0.0
        self.calls: list[dict] = []
        self.out.mkdir(parents=True, exist_ok=True)
        self.transcript = open(self.out / "transcript.jsonl", "w")
        self.state, self.closes = state_for(agent.name)
        mem_root = memory_dir or (AGENTS_DIR / agent.name)
        self.memory = Memory(mem_root, records_dir=AGENTS_DIR / agent.name / "records")
        self.tools = ToolBox(agent, day, self.alpaca, universe, self.memory, self.state, self.closes,
                             self.client, self._add_cost, self.log)

    def _add_cost(self, model: str, usage, what: str) -> None:
        c = call_cost(model, usage)
        self.cost += c
        u = usage.model_dump() if hasattr(usage, "model_dump") else usage
        self.calls.append({"model": model, "what": what, "cost": c, "usage": u})

    def _write(self, kind: str, **kw) -> None:
        self.transcript.write(redact(json.dumps({"kind": kind, "t": datetime.now(UTC).isoformat(), **kw},
                                                default=str)) + "\n")
        self.transcript.flush()

    def first_message(self) -> str:
        a = self.agent
        mem = self.memory
        summary = mem.read("summary") if (mem.dir / "summary.md").exists() else "(first session, no summary yet)"
        notes = mem.read("notes") if (mem.dir / "notes.md").exists() else "(no general notes yet)"
        expired = expired_positions(self.state, self.day)
        parts = [
            f"Today is {self.day:%A %Y-%m-%d}. The time is {datetime.now(UTC):%H:%M} UTC, before the US open. "
            f"Orders you submit fill at today's opening auction.",
            "## Your portfolio\n" + portfolio_text(self.state, self.closes, self.day),
        ]
        if expired:
            parts.append("Positions past their horizon, which need a close, extend or set_weight order today: "
                         + ", ".join(sorted(expired)))
        settled = self._settled_since_last()
        if settled:
            parts.append("## Trades settled since your last session (written by code)\n" + settled)
        if a.universe == "tech-ten":
            parts.append("Your universe: " + ", ".join(TECH_TEN) + ".")
        parts.append(f'<data source="your summary from the last session">\n{summary}\n</data>')
        parts.append(f'<data source="your general notes">\n{notes}\n</data>')
        parts.append(f'<data source="index of your ticker notes">\n{mem.index()}\n</data>')
        if self.digest:
            parts.append(f'<data source="today\'s digest">\n{render(self.digest, news=a.news)}\n</data>')
        else:
            parts.append("Today's digest could not be built. Work from your tools.")
        return "\n\n".join(parts)

    def _settled_since_last(self) -> str:
        recs = AGENTS_DIR / self.agent.name / "records"
        if not recs.exists():
            return ""
        prev = sorted(p.name for p in (AGENTS_DIR / self.agent.name / "sessions").glob("*") if p.name < self.day.isoformat())
        since = prev[-1] if prev else ""
        lines = []
        for p in sorted(recs.glob("*.json")):
            for tr in json.loads(p.read_text()).get("trades", []):
                if tr.get("closed") and tr["closed"] >= since:
                    ex = f", {tr['excess'] * 100:+.1f} points against SPY" if tr.get("excess") is not None else ""
                    lines.append(f"- {tr['ticker']}: {tr['opened']} to {tr['closed']}, {tr['return'] * 100:+.1f}%{ex}, "
                                 f"exit by {tr.get('exit_reason')}. Your probability was {tr.get('probability')}.")
        return "\n".join(lines)

    def run(self) -> dict:
        t0 = time.time()
        result = {"agent": self.agent.name, "date": self.day.isoformat(), "dry_run": self.dry_run,
                  "status": "hold", "reason": "", "orders": [], "rejected": [], "prompt_hash": prompt_hash(self.agent)}
        try:
            self._loop(result)
        except anthropic.APIError as e:
            result.update(status="failed", reason=f"API error {type(e).__name__} {getattr(e, 'status_code', '')}")
        except Exception as e:
            result.update(status="failed", reason=f"harness error {type(e).__name__}: {redact(str(e))[:200]}")
        result["total_cost"] = self.cost
        result["seconds"] = round(time.time() - t0)
        self._finish(result)
        self.transcript.close()
        return result

    def _loop(self, result: dict) -> None:
        system = system_prompt(self.agent)
        tools = definitions(self.agent)
        first = self.first_message()
        self._write("system", text=system)
        self._write("user", text=first)
        messages: list[dict] = [{"role": "user", "content": first}]
        seen_urls = {norm(h["url"]) for h in (self.digest or {}).get("headlines", []) if h.get("url")} if self.agent.news else set()
        soft_sent = turns_warned = nudged = False
        attempts = 0
        for turn in range(1, MAX_TURNS + 1):
            remaining = (self.deadline - datetime.now(UTC)).total_seconds()
            if remaining < 60:
                result["reason"] = "deadline before the open reached"
                return
            if self.cost >= self.hard_cap:
                result["reason"] = f"hard cost cap ${self.hard_cap:.2f} reached"
                return
            r = self.client.with_options(timeout=min(300.0, remaining)).messages.create(
                model=MODEL, max_tokens=16000, system=system, tools=tools, messages=messages,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": EFFORT}, cache_control={"type": "ephemeral"})
            self._add_cost(MODEL, r.usage, "turn")
            self._write("assistant", turn=turn, stop_reason=r.stop_reason, cost=self.cost,
                        content=[_clean_block(b) for b in r.content], usage=r.usage.model_dump())
            messages.append({"role": "assistant", "content": r.content})
            for b in r.content:
                if b.type == "web_search_tool_result" and isinstance(b.content, list):
                    seen_urls |= {norm(x.url) for x in b.content if getattr(x, "url", None)}

            if r.stop_reason == "refusal":
                result["reason"] = "model declined the request"
                return
            if r.stop_reason == "pause_turn":
                continue
            uses = [b for b in r.content if b.type == "tool_use"]
            if not uses:
                if nudged:
                    result["reason"] = "ended without submitting a decision"
                    return
                nudged = True
                messages.append({"role": "user", "content": "Call submit_decision now. An empty order list is fine."})
                continue

            results = []
            submitted = None
            for u in uses:
                if u.name == "submit_decision":
                    attempts += 1
                    submitted = (u, attempts)
                    continue
                out, err = self.tools.run(u.name, u.input)
                logged = "[price data omitted from the public log]" if u.name in ("get_quotes", "get_history") else out
                self._write("tool", name=u.name, input=u.input, output=logged, is_error=err)
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": out, "is_error": err})

            if submitted:
                u, n = submitted
                ctx = Context(agent=self.agent, universe=self.universe, state=self.state, closes=self.closes,
                              session_date=self.day.isoformat(), expired=expired_positions(self.state, self.day),
                              read_ok_urls=self.tools.read_ok_urls, seen_urls=seen_urls,
                              headline_text=_headline_text(self.digest), headline_symbols=_headline_symbols(self.digest))
                orders = list(u.input.get("orders") or [])
                ok, errors = validate(orders, ctx)
                self._write("decision", attempt=n, input=u.input, accepted=len(ok), errors=errors)
                if not errors or n >= 2:
                    result.update(status="decided", orders=ok, rejected=errors,
                                  summary=str(u.input.get("session_summary", "")),
                                  reason="" if not errors else "some orders rejected after the resubmission")
                    return
                results.append({"type": "tool_result", "tool_use_id": u.id, "is_error": True,
                                "content": "Nothing was accepted yet. Fix these and call submit_decision once more "
                                           "with the full order list; after that, invalid orders are dropped:\n- "
                                           + "\n- ".join(errors)})
            messages.append({"role": "user", "content": results})

            if not soft_sent and self.cost >= self.soft_cap:
                soft_sent = True
                messages.append({"role": "system", "content": "The research budget for this session is spent. "
                                 "Do no more research: call submit_decision now."})
            elif not turns_warned and turn >= MAX_TURNS - 3:
                turns_warned = True
                messages.append({"role": "system", "content": "Three turns left. Call submit_decision now."})
        result["reason"] = f"turn limit of {MAX_TURNS} reached"

    def _finish(self, result: dict) -> None:
        day = self.day.isoformat()
        orders = []
        for i, o in enumerate(result.get("orders", []), 1):
            srcs = []
            for s in o.get("sources") or []:
                a = self.tools.read_answers.get(norm(s))
                srcs.append({"url": s, "read": bool(a), "answer": a["answer"][:600] if a else ""})
            orders.append({**o, "id": f"{self.agent.name}-{day}-{i:02d}", "session_date": day,
                           "decided_at": datetime.now(UTC).isoformat(), "prompt_hash": result["prompt_hash"],
                           "sources": srcs})
        result["orders"] = orders
        summary = result.get("summary") or ""
        if result["status"] != "decided":
            summary = (f"The harness wrote this summary: the session on {day} ended without a decision "
                       f"({result['reason'] or result['status']}). Nothing traded; all positions held.\n\n" + summary)
        self.memory.write_summary(f"Session {day}.\n\n{summary}")
        (self.out / "decision.json").write_text(redact(json.dumps(result, indent=1, default=str)))
        (self.out / "usage.json").write_text(json.dumps({"total_cost": self.cost, "calls": self.calls,
                                                         "prompt_hash": result["prompt_hash"]}, indent=1, default=str))
        if not self.dry_run and orders:
            append_jsonl(AGENTS_DIR / self.agent.name / "ledger" / "orders.jsonl", orders)
        self.log(f"{result['status']}: {len(orders)} orders, ${self.cost:.3f}, {result.get('reason', '')}")


def _headline_text(digest: dict | None) -> str:
    if not digest:
        return ""
    return "\n".join(f"{h['title']} {h['line']}" for h in digest.get("headlines", []))


def _headline_symbols(digest: dict | None) -> set[str]:
    if not digest:
        return set()
    return {s for h in digest.get("headlines", []) for s in h.get("symbols", [])}
