"""Append-only cost ledger: one JSON object per line in runs/ledger.jsonl.

Fields per line:
    ts                   ISO-8601 UTC timestamp
    component            "agent", "mem0", "supermemory", "tagger", ...
    episode              episode id, or null
    condition            experimental condition, or null
    model                model id, or null for non-LLM entries
    prompt_tokens        int
    completion_tokens    int
    reasoning_tokens     int (included in completion_tokens)
    cost_usd             float, from OpenRouter's usage.cost or tokens x listed price
    note                 free text, or null

The file is per machine. OpenRouter's key-level usage (common.llm.key_usage) covers teammates sharing a key.
"""
import contextlib
import contextvars
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from common.config import ROOT

DEFAULT_PATH = ROOT / "runs/ledger.jsonl"  # anchored to the repo so the budget guard reads one ledger from any cwd
_context = contextvars.ContextVar("ledger_context", default={})


@contextlib.contextmanager
def context(**fields):
    """Label every row appended in the block, e.g. context(episode="tool-01a", condition="mem0"). Explicit arguments win."""
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def _path():
    return Path(os.environ.get("LEDGER_PATH") or DEFAULT_PATH)


def append(*, component, cost_usd, model=None, episode=None, condition=None,
           prompt_tokens=0, completion_tokens=0, reasoning_tokens=0, note=None):
    ctx = _context.get()
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "component": component, "episode": episode or ctx.get("episode"), "condition": condition or ctx.get("condition"),
        "model": model, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens, "cost_usd": cost_usd, "note": note,
    }
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def rows():
    p = _path()
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def total():
    return sum(r["cost_usd"] for r in rows())


def totals_by(field):
    """Sum cost_usd, prompt_tokens and completion_tokens per value of `field`."""
    out = defaultdict(lambda: {"cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "calls": 0})
    for r in rows():
        t = out[r[field]]
        t["cost_usd"] += r["cost_usd"]
        t["prompt_tokens"] += r["prompt_tokens"]
        t["completion_tokens"] += r["completion_tokens"]
        t["calls"] += 1
    return dict(out)
