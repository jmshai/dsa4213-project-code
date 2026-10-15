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
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path("runs/ledger.jsonl")


def _path(path):
    return Path(path or os.environ.get("LEDGER_PATH") or DEFAULT_PATH)


def append(*, component, cost_usd, model=None, episode=None, condition=None,
           prompt_tokens=0, completion_tokens=0, reasoning_tokens=0, note=None, path=None):
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "component": component, "episode": episode, "condition": condition, "model": model,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens, "cost_usd": cost_usd, "note": note,
    }
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def rows(path=None):
    p = _path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def total(path=None):
    return sum(r["cost_usd"] for r in rows(path))


def totals_by(field, path=None):
    """Sum cost_usd, prompt_tokens and completion_tokens per value of `field`."""
    out = defaultdict(lambda: {"cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "calls": 0})
    for r in rows(path):
        t = out[r[field]]
        t["cost_usd"] += r["cost_usd"]
        t["prompt_tokens"] += r["prompt_tokens"]
        t["completion_tokens"] += r["completion_tokens"]
        t["calls"] += 1
    return dict(out)
