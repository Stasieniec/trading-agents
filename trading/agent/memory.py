"""An agent's markdown memory. Writes are confined to agents/<name>/memory/ by construction."""

import json
import re
from pathlib import Path

from ..config import NOTE_CAPS_WORDS, TICKER_LOG_KEEP

TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


class MemoryError_(Exception):
    pass


def _words(s: str) -> int:
    return len(s.split())


class Memory:
    def __init__(self, agent_dir: Path, records_dir: Path | None = None):
        self.dir = (agent_dir / "memory").resolve()
        self.records = (records_dir or agent_dir / "records").resolve()
        (self.dir / "tickers").mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        n = name.strip()
        if n.lower() in ("notes", "summary"):
            p = self.dir / f"{n.lower()}.md"
        elif TICKER_RE.match(n.upper()):
            p = self.dir / "tickers" / f"{n.upper()}.md"
        else:
            raise MemoryError_("note names are 'notes', 'summary' or a ticker symbol")
        rp = p.resolve()
        if not rp.is_relative_to(self.dir):
            raise MemoryError_("note path outside memory folder")
        return rp

    def read(self, name: str) -> str:
        p = self._path(name)
        text = p.read_text() if p.exists() else ""
        if p.parent.name == "tickers":
            rec = self.records / f"{p.stem}.json"
            if rec.exists():
                text += "\n\n## Record (written by code, read-only)\n" + _render_record(json.loads(rec.read_text()))
        return text or f"No note called {name} yet."

    def list(self) -> list[dict]:
        out = []
        for p in sorted((self.dir / "tickers").glob("*.md")):
            view = _section(p.read_text(), "Current view").strip().splitlines()
            out.append({"name": p.stem, "words": _words(p.read_text()), "first_line": (view[0] if view else "")[:160]})
        return out

    def write_notes(self, content: str) -> str:
        cap = NOTE_CAPS_WORDS["notes"]
        if _words(content) > cap:
            raise MemoryError_(f"notes would be {_words(content)} words, the cap is {cap}. Condense and try again.")
        self._path("notes").write_text(content.strip() + "\n")
        return f"notes saved ({_words(content)} words)"

    def update_ticker(self, ticker: str, current_view: str, log_entry: str, day: str) -> str:
        p = self._path(ticker)
        t = p.stem
        old = p.read_text() if p.exists() else ""
        view = current_view.strip() or _section(old, "Current view").strip()
        log = [ln for ln in _section(old, "Log").splitlines() if ln.startswith("- ")]
        if log_entry.strip():
            log.append(f"- {day}: " + " ".join(log_entry.split()))
        archived = []
        if len(log) > TICKER_LOG_KEEP:
            archived, log = log[:-TICKER_LOG_KEEP], log[-TICKER_LOG_KEEP:]
        text = f"# {t}\n\n## Current view\n\n{view}\n\n## Log\n\n" + "\n".join(log) + "\n"
        cap = NOTE_CAPS_WORDS["ticker"]
        if _words(text) > cap:
            raise MemoryError_(f"{t} note would be {_words(text)} words, the cap is {cap}. Shorten the current view.")
        if archived:
            arch = self.dir / "tickers" / "archive" / f"{t}.md"
            arch.parent.mkdir(exist_ok=True)
            with open(arch, "a") as f:
                f.write("\n".join(archived) + "\n")
        p.write_text(text)
        return f"{t} note saved ({_words(text)} words)"

    def write_summary(self, text: str) -> None:
        self._path("summary").write_text(text.strip() + "\n")

    def index(self) -> str:
        rows = self.list()
        if not rows:
            return "(no ticker notes yet)"
        return "\n".join(f"- {r['name']}: {r['first_line']}" for r in rows)


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def _render_record(rec: dict) -> str:
    lines = []
    for tr in rec.get("trades", []):
        if tr.get("closed"):
            ex = f", against SPY {tr['excess'] * 100:+.1f} points" if tr.get("excess") is not None else ""
            lines.append(f"- {tr['opened']} to {tr['closed']}: {tr['return'] * 100:+.1f}%{ex}, exit by {tr.get('exit_reason')}")
        else:
            lines.append(f"- open since {tr['opened']}")
    return "\n".join(lines) or "- no trades"
