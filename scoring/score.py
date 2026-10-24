"""README Step 7: score every run log and write reports/.

    uv run python -m scoring.score --dry-run     # how many judge calls are needed and roughly what they cost; no API calls
    uv run python -m scoring.score               # judge whatever is not cached yet, then write reports/
    uv run python -m scoring.score --offline     # no API calls: cached verdicts only, others fall back to the first-line keyword
    uv run python -m scoring.score --conditions no_memory mem0 scope_write_mem0 --gold-status adjudicated

Reads the agent.runner logs in runs/logs/. Judge calls go through common/llm.py (ledger component "judge") and are
cached in runs/judge_cache.jsonl. Human labels in reports/review/judge_review.csv (scoring.review) override the judge.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import ledger, llm
from common.config import CONFIG, ROOT
from episodes.loader import episodes
from scoring import report, review, tables
from scoring.judge import CACHE_PATH, OUTPUT_TOKENS_ESTIMATE, VERSION, Cache, Judge, SETTINGS
from scoring.records import score_log

LOG_DIR = ROOT / "runs/logs"
OUT_DIR = ROOT / "reports"


def episode_map():
    return {e["episode_id"]: e for e in episodes()}


def load_logs(log_dir, conditions=None):
    logs = []
    for path in sorted(Path(log_dir).glob("*/*.json")):
        if conditions and path.parent.name not in conditions:
            continue
        try:
            logs.append(json.loads(path.read_text()))
        except ValueError:
            print(f"skipped unreadable log {path}")
    return logs


def score_all(logs, eps, judge, overrides, progress=False):
    records, checks = [], []
    for i, log in enumerate(logs, 1):
        rec, cs = score_log(log, eps[log["episode_id"]], judge, overrides.get((log["condition"], log["episode_id"])))
        records.append(rec)
        checks += cs
        if progress and (i % 20 == 0 or i == len(logs)):
            print(f"  scored {i}/{len(logs)} logs, {judge.calls} judge calls so far", flush=True)
    return records, checks


def score_offline(log_dir=LOG_DIR, cache_path=CACHE_PATH):
    """Records from cached verdicts only (no API calls), for scoring.review."""
    eps = episode_map()
    logs = [log for log in load_logs(log_dir) if log.get("episode_id") in eps]
    records, _ = score_all(logs, eps, Judge(Cache(cache_path), mode="offline"), {})
    return records, logs, eps


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--logs", default=str(LOG_DIR), help="folder of runner logs (default runs/logs)")
    p.add_argument("--out", default=str(OUT_DIR), help="where to write the report (default reports)")
    p.add_argument("--conditions", nargs="+", help="score only these conditions")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="count the judge calls needed, make none")
    mode.add_argument("--offline", action="store_true", help="make no judge calls; use the cache and the keyword fallback")
    p.add_argument("--gold-status", choices=["draft", "adjudicated"], default="draft", help="printed in the report")
    p.add_argument("--cache", default=str(CACHE_PATH), help="judge cache (default runs/judge_cache.jsonl)")
    p.add_argument("--review", help="human review CSV (default <out>/review/judge_review.csv)")
    args = p.parse_args(argv)

    eps = episode_map()
    logs = load_logs(args.logs, args.conditions)
    unknown = sorted({log.get("episode_id") for log in logs if log.get("episode_id") not in eps}, key=str)
    if unknown:
        print(f"ignoring logs for episodes that are not in the suite: {unknown}")
    logs = [log for log in logs if log.get("episode_id") in eps]
    if not logs:
        print(f"no logs in {args.logs}. Run the episodes first: uv run python -m agent.runner --conditions all")
        return 1
    overrides = review.read_labels(Path(args.review) if args.review else Path(args.out) / "review/judge_review.csv", eps)
    cache = Cache(args.cache)

    plan = Judge(cache, mode="plan")
    score_all(logs, eps, plan, overrides)
    needed = len(plan.planned)
    tokens = sum(t for _, t in plan.planned)
    if args.dry_run:
        if not needed:
            print(f"{len(logs)} logs, every judge verdict is cached. Nothing to pay for.")
            return 0
        price = None
        try:
            price = llm._price(SETTINGS["model"])
        except Exception as e:  # noqa: BLE001 - the estimate is a convenience
            print(f"(could not fetch the price list: {type(e).__name__})")
        out_tokens = needed * OUTPUT_TOKENS_ESTIMATE
        cost = f", about ${(tokens - out_tokens) * price[0] + out_tokens * price[1]:.3f}" if price else ""
        print(f"{len(logs)} logs need {needed} judge calls ({sum(k == 'answer' for k, _ in plan.planned)} answers, "
              f"{sum(k == 'notes' for k, _ in plan.planned)} note matches), roughly {tokens:,} tokens{cost} with {SETTINGS['model']}.")
        return 0

    judge = Judge(cache, mode="offline" if args.offline else "call")
    if needed and not args.offline:
        print(f"judging {needed} new items with {SETTINGS['model']} (about {tokens:,} tokens); cached verdicts are reused")
        llm.start_run()
    records, checks = score_all(logs, eps, judge, overrides, progress=bool(needed and not args.offline))
    if judge.errors:
        print(f"{len(judge.errors)} judge calls failed and fell back to the first-line keyword; rerun to retry them. First: {judge.errors[0]}")

    meta = {"scored_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "logs": len(logs), "log_dir": args.logs,
            "agent_model": CONFIG["llm"]["model"], "judge_model": SETTINGS["model"], "judge_version": VERSION,
            "gold_status": args.gold_status, "judge_usd": ledger.totals_by("component").get("judge", {}).get("cost_usd", 0.0),
            "probe_changed": sum(r["probe_changed"] for r in records)}
    paths = report.write_all(args.out, records, checks, logs, eps, meta)

    print(f"\n{'condition':<26}{'episodes right':>16}{'pairs right':>13}{'retention':>11}")
    ret = {r["condition"]: r for r in tables.retention(records)}
    for r in tables.adherence(records):
        print(f"{r['condition']:<26}{report.frac(r['correct'], r['episodes']):>16}{report.frac(r['pairs_both_correct'], r['pairs']):>13}"
              f"{report.pct(ret[r['condition']]['retention']):>11}")
    print(f"\nwrote {paths['summary']}, {paths['examples']} and {paths['episode_scores']}"
          + (f", plus {sum(k.startswith('figure:') for k in paths)} figures" if any(k.startswith("figure:") for k in paths) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
