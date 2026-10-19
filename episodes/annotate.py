"""Independent double-labelling of memories (README: Gold labels).

    uv run python -m episodes.annotate export out_dir            # one blank CSV per annotator (same content)
    uv run python -m episodes.annotate agree a.csv b.csv         # per-field agreement and the disagreements
    uv run python -m episodes.annotate agree a.csv b.csv --draft # also each annotator against the drafted gold labels
"""
import csv
import sys
from pathlib import Path

from episodes.loader import load_pairs

FIELDS = ("scope", "key", "condition")
COLUMNS = ("memory_id", "task_id", "active_project", "memory_text", *FIELDS)


def blind_rows(pairs=None):
    """One row per memory: the text, its session's task id and active project, and blank label columns. No gold leaks."""
    rows = []
    for pair in pairs if pairs is not None else load_pairs():
        sessions = {s["session_id"]: s for s in pair["sessions"]}
        for m in pair["memories"]:
            s = sessions[m["session_id"]]
            rows.append({"memory_id": f"{pair['pair_id']}/{m['memory_id']}", "task_id": s["task_id"],
                         "active_project": s["active_project"] or "", "memory_text": m["text"], **dict.fromkeys(FIELDS, "")})
    return rows


def gold_rows(pairs=None):
    return {f"{p['pair_id']}/{m['memory_id']}": {f: m["gold"][f] or "" for f in FIELDS}
            for p in (pairs if pairs is not None else load_pairs()) for m in p["memories"]}


def read_labels(path):
    with open(path, newline="") as f:
        return {r["memory_id"]: {k: (r[k] or "").strip() for k in FIELDS} for r in csv.DictReader(f)}


def agreement(a, b):
    """Per-field fraction of memories on which two label sets agree, plus the list of (memory_id, field, a, b) disagreements."""
    ids = sorted(set(a) & set(b))
    diffs = [(i, f, a[i][f], b[i][f]) for i in ids for f in FIELDS if a[i][f] != b[i][f]]
    rates = {f: 1 - sum(d[1] == f for d in diffs) / len(ids) for f in FIELDS} if ids else {}
    return rates, diffs


def main(argv):
    if argv[:1] == ["export"]:
        out = Path(argv[1])
        out.mkdir(parents=True, exist_ok=True)
        for name in ("annotator_a.csv", "annotator_b.csv"):
            with open(out / name, "w", newline="") as f:
                w = csv.DictWriter(f, COLUMNS)
                w.writeheader()
                w.writerows(blind_rows())
        print(f"wrote {out}/annotator_a.csv and annotator_b.csv")
        return 0
    if argv[:1] == ["agree"]:
        a, b = read_labels(argv[1]), read_labels(argv[2])
        rates, diffs = agreement(a, b)
        print("annotator A vs B: " + ", ".join(f"{f} {r:.0%}" for f, r in rates.items()))
        for d in diffs:
            print("  disagree", *d)
        if "--draft" in argv:
            gold = gold_rows()
            for name, labels in (("A", a), ("B", b)):
                rates, _ = agreement(labels, gold)
                print(f"annotator {name} vs draft: " + ", ".join(f"{f} {r:.0%}" for f, r in rates.items()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
