"""Check the judge against a human before trusting the numbers.

    uv run python -m scoring.review              # after scoring.score; 40 answers by default
    uv run python -m scoring.review --n 60 --force

Writes reports/review/judge_review.md (each answer in full, with what the judge decided folded away at the end of each
item) and judge_review.csv. Read the .md file, then in the .csv fill `human_action` with one of the options listed for
that item (or none / mixed) and `human_retention` with yes or no. Leave a cell empty to skip it. The .csv carries no
judge verdicts, so the labels are made blind; agreement is computed from the scored records. Rerun `uv run python -m scoring.score`: your labels
replace the judge's for those episodes, and summary.md section 10 reports how often the judge agreed with you.

The sample takes every answer where the judge and the first-line keyword disagree (up to half the sample), then a
random draw spread across conditions, with a fixed seed so a rerun picks the same answers.
"""
import argparse
import csv
import random
import sys
from pathlib import Path

from common.config import ROOT
from scoring.judge import pick_option
from scoring.records import candidates

REVIEW_PATH = ROOT / "reports/review/judge_review.csv"
COLUMNS = ("item", "options", "human_action", "human_retention", "notes")  # no judge columns: the labels are blind
YES, NO = {"yes", "y", "true", "pass", "passed", "1"}, {"no", "n", "false", "fail", "failed", "0"}


def sample(records, n, seed):
    rs = [r for r in records if r["status"] == "ok" and r["judge_action"] is not None]
    rng = random.Random(seed)
    disagree = [r for r in rs if r["keyword_action"] and r["judge_action"] != r["keyword_action"]]
    rng.shuffle(disagree)
    picked = disagree[: n // 2]
    rest = [r for r in rs if r not in picked]
    rng.shuffle(rest)
    by_condition = {}
    for r in rest:
        by_condition.setdefault(r["condition"], []).append(r)
    queues = list(by_condition.values())
    while len(picked) < n and any(queues):  # round robin over conditions, so each one gets checked
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop())
    return sorted(picked, key=lambda r: (r["condition"], r["episode_id"]))


def write_review(picked, logs, eps, folder):
    folder.mkdir(parents=True, exist_ok=True)
    by_key = {(log["condition"], log["episode_id"]): log for log in logs}
    md = ["# Judge review\n",
          "For each item, read the request and the answer, decide which option the answer actually uses and whether it passes "
          "the retention check, and write that in `judge_review.csv` (columns `human_action` and `human_retention`). "
          "Decide before you look at the judge's verdict, which is at the end of each item.\n"]
    rows = []
    for r in picked:
        ep, log = eps[r["episode_id"]], by_key[(r["condition"], r["episode_id"])]
        options = sorted(candidates(ep["pair"], ep["probe"]))
        item = f"{r['condition']}/{r['episode_id']}"
        checks = "; ".join(rc["check"] for rc in ep["pair"]["retention_checks"])
        md += [f"\n---\n\n## {item}\n", f"**Request:** {ep['probe']['text']}\n",
               f"**Options** ({ep['probe']['decision'].replace('_', ' ')}): {', '.join(options)}, none, mixed\n",
               f"**Retention check:** {checks}\n", "**Answer:**\n", "````text", log["agent"]["response"], "````\n",
               f"<details><summary>Judge's verdict (open it only after you have decided)</summary>\n\naction: {r['judge_action']} (evidence: \"{r['action_evidence']}\"); "
               f"retention: {r['judge_retention']} (evidence: \"{r['retention_evidence']}\")\n</details>\n"]
        rows.append({"item": item, "options": " | ".join([*options, "none", "mixed"]), "human_action": "", "human_retention": "", "notes": ""})
    (folder / "judge_review.md").write_text("\n".join(md) + "\n")
    with (folder / "judge_review.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)


def read_labels(path, eps):
    """{(condition, episode_id): {"action", "retention"}} from a filled-in review CSV. Empty cells are skipped."""
    path = Path(path)
    if not path.exists():
        return {}
    labels = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            condition, _, episode_id = (row.get("item") or "").partition("/")
            if episode_id not in eps:
                continue
            ep = eps[episode_id]
            action = (row.get("human_action") or "").strip()
            if action:
                try:
                    action = pick_option(action, list(candidates(ep["pair"], ep["probe"])))
                except ValueError:
                    print(f"review: {row['item']}: {action!r} is not an option, ignored")
                    action = None
            kept = (row.get("human_retention") or "").strip().lower()
            retention = True if kept in YES else False if kept in NO else None
            if action or retention is not None:
                labels[(condition, episode_id)] = {"action": action or None, "retention": retention}
    return labels


def main(argv=None):
    from scoring import score  # late import: score imports this module
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=40, help="answers to review")
    p.add_argument("--seed", type=int, default=4213)
    p.add_argument("--logs", default=str(score.LOG_DIR))
    p.add_argument("--out", default=str(REVIEW_PATH.parent))
    p.add_argument("--force", action="store_true", help="overwrite a review file that already has human labels")
    args = p.parse_args(argv)
    out = Path(args.out)
    existing = read_labels(out / "judge_review.csv", score.episode_map())
    if existing and not args.force:
        print(f"{out / 'judge_review.csv'} already has {len(existing)} human labels; use --force to replace it")
        return 1
    records, logs, eps = score.score_offline(args.logs)
    if not records:
        print("no scored answers yet: run `uv run python -m scoring.score` first")
        return 1
    picked = sample(records, args.n, args.seed)
    write_review(picked, logs, eps, out)
    print(f"wrote {len(picked)} items to {out / 'judge_review.md'} and {out / 'judge_review.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
