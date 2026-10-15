"""Validate episode pairs: JSON Schema, then the semantic checks, then a walk of the conflict-resolution
pipeline over the gold tags that must reproduce each probe's expected memory and deciding rule.

    uv run python -m episodes.validate            # all pairs in episodes/pairs/
    uv run python -m episodes.validate a.json b.json
"""
import json
import operator
import re
import sys
from pathlib import Path

import jsonschema

from episodes.loader import PAIRS_DIR

SCHEMA = json.loads((Path(__file__).parent / "schema.json").read_text())
SCOPE_RANK = {"single_task": 0, "project": 1, "standing": 2}
OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq, "!=": operator.ne}
# Rule that decides each probe, per conflict type (README: Conflict resolution).
EXPECTED_RULES = {
    "project_override": (2, 1), "single_task_override": (2, 1), "conditional_scope": (2, 1),
    "same_scope_supersession": (4, 1), "same_scope_specificity": (3, 1),
}
SAME_TASK_CUE = re.compile(r"\b(continue|continuing|same (task|job)|from earlier|still working on)\b", re.I)
NEW_TASK_CUE = re.compile(r"\b(new task|different task|separate task|another task|unrelated task|new job|different job)\b", re.I)


def holds(condition, facts):
    """Evaluate `<var> <op> <value>` against probe facts. Unknown variable means the condition does not hold."""
    var, op, raw = re.match(r"^(\S+) (>=|<=|==|!=|>|<) (.+)$", condition).groups()
    if var not in facts:
        return False
    try:
        raw = float(raw)
    except ValueError:
        pass
    return OPS[op](facts[var]["value"], raw)


def resolve(pair, probe):
    """Walk the five-rule pipeline over gold tags. Returns (memory_id, rule) or raises on a tie."""
    facts = probe["facts"]
    cands = [m for m in pair["memories"] if m["decision"] == probe["decision"]]
    order = {s["session_id"]: s["order"] for s in pair["sessions"]}

    def applies(m):
        g = m["gold"]
        key_ok = (g["scope"] == "standing" or (g["scope"] == "project" and g["key"] == probe["active_project"])
                  or (g["scope"] == "single_task" and g["key"] == probe["task_id"]))
        return key_ok and (g["condition"] is None or holds(g["condition"], facts))

    cands = [m for m in cands if applies(m)]
    if not cands:
        raise ValueError("no applicable memory")
    if len(cands) == 1:
        return cands[0]["memory_id"], 1
    best = min(SCOPE_RANK[m["gold"]["scope"]] for m in cands)
    cands = [m for m in cands if SCOPE_RANK[m["gold"]["scope"]] == best]
    if len(cands) == 1:
        return cands[0]["memory_id"], 2
    if any(m["gold"]["condition"] for m in cands):
        cands = [m for m in cands if m["gold"]["condition"]]
        if len(cands) == 1:
            return cands[0]["memory_id"], 3
    latest = max(order[m["session_id"]] for m in cands)
    cands = [m for m in cands if order[m["session_id"]] == latest]
    if len(cands) == 1:
        return cands[0]["memory_id"], 4
    raise ValueError(f"tie between {[m['memory_id'] for m in cands]}")


def check_pair(pair):
    """Return a list of problems with one pair (empty if valid)."""
    errs = [f"schema: {e.message} at /{'/'.join(map(str, e.absolute_path))}" for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(pair)]
    if errs:
        return errs
    sessions = {s["session_id"]: s for s in pair["sessions"]}
    mems = {m["memory_id"]: m for m in pair["memories"]}
    if len(sessions) != len(pair["sessions"]) or len(mems) != len(pair["memories"]):
        errs.append("duplicate session_id or memory_id")
    if sorted(s["order"] for s in pair["sessions"]) != list(range(1, len(sessions) + 1)):
        errs.append("session order must be 1..n")

    for s in pair["sessions"]:
        if s["active_project"] and s["active_project"] not in s["text"]:
            errs.append(f"session {s['session_id']}: active project {s['active_project']!r} not in its text")
    for m in pair["memories"]:
        s = sessions.get(m["session_id"])
        if s is None:
            errs.append(f"memory {m['memory_id']}: unknown session {m['session_id']}")
        elif m["text"] not in s["text"]:
            errs.append(f"memory {m['memory_id']}: text is not a verbatim substring of session {m['session_id']}")
        g = m["gold"]
        if (g["scope"] == "standing") != (g["key"] is None):
            errs.append(f"memory {m['memory_id']}: key must be null exactly when scope is standing")
        if g["scope"] == "single_task" and s and g["key"] != s["task_id"]:
            errs.append(f"memory {m['memory_id']}: single_task key must equal its session's task_id")
        if g["scope"] == "project" and s and g["key"] != s["active_project"]:
            errs.append(f"memory {m['memory_id']}: project key must equal its session's active_project")
        if (m["role"] == "unrelated") != (m["decision"] is None) or (m["decision"] is None) != (m["action"] is None):
            errs.append(f"memory {m['memory_id']}: decision and action must both be null exactly for unrelated memories")
    for rc in pair["retention_checks"]:
        if rc["memory_id"] not in mems or mems[rc["memory_id"]]["role"] != "unrelated":
            errs.append(f"retention check refers to {rc['memory_id']!r}, which is not an unrelated memory")
    if not pair["retention_checks"]:
        errs.append("needs at least one retention check")
    if errs:
        return errs

    a, b = pair["probes"]["A"], pair["probes"]["B"]
    if not (a["in_scope"] and not b["in_scope"]):
        errs.append("probe A must be in scope and probe B out of scope")
    if a["expected_action"] == b["expected_action"]:
        errs.append("probes A and B must have different expected actions")
    if a["decision"] != b["decision"]:
        errs.append("probes A and B must bear on the same decision")
    for label, p in (("A", a), ("B", b)):
        if p["active_project"] and p["active_project"] not in p["text"]:
            errs.append(f"probe {label}: project {p['active_project']!r} not in its text")
        for var, f in p["facts"].items():
            if f["text"] not in p["text"]:
                errs.append(f"probe {label}: fact {var!r} text {f['text']!r} not in probe text")
        try:
            mid, rule = resolve(pair, p)
        except ValueError as e:
            errs.append(f"probe {label}: gold walk fails: {e}")
            continue
        if mid != p["expected_memory"] or rule != p["deciding_rule"]:
            errs.append(f"probe {label}: gold walk gives {mid} by rule {rule}, file says {p['expected_memory']} by rule {p['deciding_rule']}")
        if mems.get(p["expected_memory"], {}).get("action") != p["expected_action"]:
            errs.append(f"probe {label}: expected_action does not match the action of {p['expected_memory']}")
    want = EXPECTED_RULES[pair["conflict_type"]]
    if (a["deciding_rule"], b["deciding_rule"]) != want:
        errs.append(f"{pair['conflict_type']} needs deciding rules {want} for (A, B)")
    if pair["conflict_type"] == "single_task_override":
        if not SAME_TASK_CUE.search(a["text"]) or a["task_id"] not in {s["task_id"] for s in pair["sessions"]}:
            errs.append("single_task probe A needs a same-task cue in its text and the memory session's task_id")
        if not NEW_TASK_CUE.search(b["text"]) or b["task_id"] in {s["task_id"] for s in pair["sessions"]}:
            errs.append("single_task probe B needs a new-task cue in its text and a task_id not used by any session")
    return errs


def main(paths):
    paths = [Path(p) for p in paths] or sorted(PAIRS_DIR.glob("*.json"))
    bad = 0
    for p in paths:
        errs = check_pair(json.loads(p.read_text()))
        bad += bool(errs)
        print(f"{'FAIL' if errs else 'ok  '} {p.name}")
        for e in errs:
            print(f"     - {e}")
    print(f"\n{len(paths) - bad}/{len(paths)} pairs valid")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
