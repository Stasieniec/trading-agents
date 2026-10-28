"""Keeping key material out of everything this repo writes."""

import os
import re
from pathlib import Path

SECRET_ENV_VARS = ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ALPACA_KEY", "ALPACA_SECRET", "GITHUB_TOKEN"]
KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\b[PA]K[A-Z0-9]{18}\b"),  # Alpaca key ids
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
]


def _secret_values() -> list[str]:
    vals = []
    for name in SECRET_ENV_VARS:
        v = os.environ.get(name, "")
        if len(v) >= 8:
            vals.append(v)
    return vals


def redact(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    for v in _secret_values():
        text = text.replace(v, "[redacted]")
    for p in KEY_PATTERNS:
        text = p.sub("[redacted]", text)
    return text


def scan_text(text: str, exact: bool = True) -> list[str]:
    hits = []
    if exact:
        for v in _secret_values():
            if v in text:
                hits.append("exact secret value")
    for p in KEY_PATTERNS:
        if p.search(text):
            hits.append(f"key pattern {p.pattern[:12]}")
    return hits


def scan_paths(paths: list[Path], exact: bool = True) -> list[str]:
    """Return 'path: reason' for every file that contains key material."""
    found = []
    for root in paths:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for f in files:
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            for reason in scan_text(text, exact=exact):
                found.append(f"{f}: {reason}")
    return found
