"""README Step 6: run episodes under conditions and write one JSON log per episode per condition.

    uv run python -m agent.runner --conditions no_memory mem0 --episodes po-01a po-01b
    uv run python -m agent.runner --conditions scope_write_mem0 scope_read_mem0     # all 40 episodes
    uv run python -m agent.runner --list

Logs go to runs/logs/<condition>/<episode_id>.json. An episode whose log exists without an error is skipped, so a
stopped run can be restarted; --force reruns it. The `gold_ref` block is for scoring only. Nothing in it reaches a system.
"""
import argparse
import json
import re
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone

import openai

from agent import agent
from agent.conditions import CONDITIONS
from common import ledger, llm
from common.config import CONFIG, ROOT
from episodes.loader import episodes

LOG_DIR = ROOT / "runs/logs"
RATE_LIMIT_WAITS_S = (20, 40, 80, 160)  # waits between attempts when the provider returns 429; the last attempt is final


def _usage(rows):
    by = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0})
    for r in rows:
        u = by[r["component"]]
        u["calls"] += 1
        for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "cost_usd"):
            u[k] += r[k]
    return {"total_cost_usd": sum(u["cost_usd"] for u in by.values()), "by_component": dict(by)}


def _action_hint(pair, probe, response):
    """The decision's action that the response's first line mentions first, or None. A scoring aid only, Step 7 owns the real mapping."""
    first = response.strip().splitlines()[0].lower() if response.strip() else ""
    actions = {m["action"] for m in pair["memories"] if m["decision"] == probe["decision"]}
    found = {a: m.start() for a in actions if (m := re.search(rf"(?<![a-z0-9]){re.escape(a.lower())}(?![a-z0-9])", first))}
    return min(found, key=found.get) if found else None


def _gold_ref(ep, response):
    pair, probe = ep["pair"], ep["probe"]
    return {
        "pair_id": pair["pair_id"], "conflict_type": pair["conflict_type"], "label": ep["label"], "in_scope": probe["in_scope"],
        "expected_action": probe["expected_action"], "expected_memory": probe["expected_memory"], "deciding_rule": probe["deciding_rule"],
        "action_first_mentioned": _action_hint(pair, probe, response) if response else None,
        "memory_actions": {m["memory_id"]: m["action"] for m in pair["memories"] if m["decision"] == probe["decision"]},
    }


def _attempt(ep, condition):
    with llm.context(episode=ep["episode_id"], condition=condition):
        result = CONDITIONS[condition](ep)
        prompt = agent.build_prompt(result["memories"], ep["probe"]["text"])
        response, model = agent.act(prompt)
    return result, prompt, response, model


def run_episode(ep, condition):
    """Run one episode under one condition and return its log dict. Exceptions other than BudgetExceeded are recorded in the log.

    A provider rate limit (HTTP 429) reruns the whole episode after a wait, since the memory namespace is reset between
    attempts. Spend from failed attempts stays in the usage block because it was really spent.
    """
    log = {"episode_id": ep["episode_id"], "condition": condition, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "model": CONFIG["llm"]["model"], "probe": ep["probe"]["text"], "error": None, "attempts": 0}
    n_before, response = len(ledger.rows()), ""
    for wait in (*RATE_LIMIT_WAITS_S, None):
        log["attempts"] += 1
        try:
            result, prompt, response, model = _attempt(ep, condition)
            log |= {**result, "prompt": prompt, "agent": {"model": model, "response": response,
                                                          "first_line": response.strip().splitlines()[0] if response.strip() else ""}}
            log["error"] = None
            break
        except llm.BudgetExceeded:
            raise
        except Exception as e:
            log["error"] = {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()}
            if not isinstance(e, openai.RateLimitError) or wait is None:
                break
            print(f"  rate limited on {condition}/{ep['episode_id']}, waiting {wait}s", flush=True)
            time.sleep(wait)
    log["usage"] = _usage(ledger.rows()[n_before:])
    log["gold_ref"] = _gold_ref(ep, response)
    return log


def log_path(condition, episode_id):
    return LOG_DIR / condition / f"{episode_id}.json"


def _done(path):
    try:
        return json.loads(path.read_text())["error"] is None
    except (OSError, ValueError, KeyError):
        return False


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--conditions", nargs="+", choices=list(CONDITIONS), help="conditions to run")
    p.add_argument("--episodes", nargs="+", help="episode ids such as po-01a; default is all 40")
    p.add_argument("--force", action="store_true", help="rerun episodes that already have a log")
    p.add_argument("--list", action="store_true", help="print the condition names and exit")
    args = p.parse_args(argv)
    if args.list or not args.conditions:
        print("\n".join(CONDITIONS))
        return 0

    eps = [e for e in episodes() if not args.episodes or e["episode_id"] in args.episodes]
    unknown = set(args.episodes or []) - {e["episode_id"] for e in eps}
    if unknown:
        p.error(f"unknown episodes: {sorted(unknown)}")

    llm.start_run()
    failed = 0
    for condition in args.conditions:
        for ep in eps:
            path = log_path(condition, ep["episode_id"])
            if _done(path) and not args.force:
                print(f"skip {condition}/{ep['episode_id']} (log exists)")
                continue
            log = run_episode(ep, condition)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(log, indent=2, default=str))
            failed += bool(log["error"])
            status = f"ERROR {log['error']['type']}: {log['error']['message'][:80]}" if log["error"] else repr(log["agent"]["first_line"][:70])
            print(f"{condition}/{ep['episode_id']}  ${log['usage']['total_cost_usd']:.5f}  {status}")
    print(f"\nledger total ${ledger.total():.4f} of ${llm.budget():.2f}; {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
