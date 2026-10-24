"""Step 7: score one run log against the gold of its episode.

Each log becomes one record (one row of reports/episode_scores.csv) and a list of tag checks (tagging accuracy).

Action and category. The judge says which candidate action the answer takes. The action maps back to the memory that
calls for it, and the gold tags say why that memory was the wrong one (README: Conflict resolution):
    correct       the expected action
    over_apply    a memory that does not apply to this probe: another project or task, or a condition that fails
    under_apply   a memory that applies but is broader (rule 2) or less specific (rule 3) than the one that should win
    superseded    a memory of the same scope and specificity that a later one replaced (rule 4)
    other_action  none of the candidate actions
    hedged        several actions, or the choice left to the user (rule 5: no memory wins, counted as a failure)
    default       the no-memory floor picked a competing action; it saw no memory, so that is its default, not a misapplied memory

Failure stage, for a wrong answer, first that applies:
    no_memory     the floor condition, nothing to retrieve
    extraction    Mem0 did not keep the memory that should win (Mem0 only: its stored list is its memories)
    retrieval     the memory that should win was not retrieved for the probe
    scope_lost    a competing memory reached the agent without its limit (no project, task or condition), and no
                  correct tag restored it (plain baselines and read-time tagging)
    tagging       the scope layer's tag on a competing memory was wrong or missing
    reasoning     the agent had the right memories with correct scope information and still chose wrong
For the full transcript every memory is in front of the agent, so its failures are reasoning failures.
"""
import re

from agent.conditions import CONDITION_INFO
from episodes.validate import SCOPE_RANK, holds
from scoring.textmatch import norm, note_text, verbatim_matches

CATEGORIES = ("correct", "over_apply", "under_apply", "superseded", "other_action", "hedged", "default")
STAGES = ("correct", "no_memory", "extraction", "retrieval", "scope_lost", "tagging", "reasoning", "unknown")
STORED_IS_MEMORIES = {"mem0"}  # Supermemory lists documents, not the memories it extracted from them
KEY_STOPWORDS = {"project", "the", "a", "an"}
COND_RE = re.compile(r"^\s*([A-Za-z_][\w ]*?)\s*(>=|<=|==|!=|=|>|<)\s*(.+?)\s*$")
MULTIPLIERS = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}


def condition_info(name, log=None):
    if name in CONDITION_INFO:
        return CONDITION_INFO[name]
    log = log or {}
    return {"role": "other", "system": "unknown" if log.get("stored") is not None or log.get("retrieved") else None,
            "layer": "write" if log.get("written") is not None else "read" if log.get("tagged") is not None else None}


def candidates(pair, probe):
    """{action: memory_id} for the memories that compete on the probe's decision."""
    return {m["action"]: m["memory_id"] for m in pair["memories"] if m["decision"] == probe["decision"]}


def applies(memory, probe):
    """Rule 1 of the pipeline on gold tags, as in episodes.validate.resolve."""
    g = memory["gold"]
    key_ok = (g["scope"] == "standing" or (g["scope"] == "project" and g["key"] == probe["active_project"])
              or (g["scope"] == "single_task" and g["key"] == probe["task_id"]))
    return key_ok and (g["condition"] is None or holds(g["condition"], probe["facts"]))


def classify(pair, probe, action):
    """Category of an action on a probe. None when there is no action to score."""
    if action is None:
        return None
    if action == probe["expected_action"]:
        return "correct"
    if action in ("none", "mixed"):
        return "other_action" if action == "none" else "hedged"
    chosen_id = candidates(pair, probe).get(action)
    if chosen_id is None:
        return "other_action"
    mems = {m["memory_id"]: m for m in pair["memories"]}
    chosen, expected = mems[chosen_id]["gold"], mems[probe["expected_memory"]]["gold"]
    if not applies(mems[chosen_id], probe):
        return "over_apply"
    if SCOPE_RANK[chosen["scope"]] > SCOPE_RANK[expected["scope"]] or (
            chosen["scope"] == expected["scope"] and expected["condition"] and not chosen["condition"]):
        return "under_apply"
    return "superseded"


# ---- tag comparison -------------------------------------------------------------------------------------------------

def _key_tokens(key):
    return set(re.findall(r"[a-z0-9]+", (key or "").lower())) - KEY_STOPWORDS


def key_ok(pred_key, gold):
    """None for single_task (task ids are gold-only, README Step 4). Standing: the key must be empty. Project: every
    word of the gold project name (other than "project") must appear in the predicted key."""
    if gold["scope"] == "single_task":
        return None
    if gold["scope"] == "standing":
        return not pred_key
    want, got = _key_tokens(gold["key"]), _key_tokens(pred_key)
    return bool(got) and want <= got


def _value(raw):
    v = raw.strip().strip("'\"").lower()
    try:
        return float(v.replace(",", "").replace("_", ""))
    except ValueError:
        pass
    m = re.fullmatch(r"([-+]?\d[\d,_]*(?:\.\d+)?)\s*([a-z]+)?", v)
    if m:  # 1M, 1.5k; other units (mb, hours) keep the number, since the variable name carries the unit
        return float(m[1].replace(",", "").replace("_", "")) * MULTIPLIERS.get(m[2] or "", 1)
    return re.sub(r"[^a-z0-9]+", " ", v).strip()


def parse_condition(text):
    m = COND_RE.match(text or "")
    if not m:
        return None
    var, op, value = m.groups()
    return re.sub(r"\W+", "_", var.strip().lower()), "==" if op == "=" else op, _value(value)


def condition_ok(pred, gold):
    """(strict, lenient). Strict: variable, operator and value match. Lenient: operator and value match, so a tagger
    that names the variable differently ("file_size_mb" for "size_mb") still gets the condition right."""
    if not pred and not gold:
        return True, True
    if not pred or not gold:
        return False, False
    p, g = parse_condition(pred), parse_condition(gold)
    if p is None or g is None:
        same = norm(pred) == norm(gold)
        return same, same
    if isinstance(p[2], float) and isinstance(g[2], float):
        same_value = abs(p[2] - g[2]) <= 1e-9 * max(1.0, abs(g[2]))
    else:
        same_value = p[2] == g[2]
    lenient = p[1] == g[1] and same_value
    return lenient and p[0] == g[0], lenient


def compare_tag(tag, gold):
    """Field-by-field comparison of a layer tag ({scope, key, condition} or None) with a gold tag."""
    if not tag:
        return {"tagged": False, "scope_ok": False, "key_ok": None if gold["scope"] == "single_task" else False,
                "condition_ok": False, "condition_lenient_ok": False, "all_ok": False}
    scope = tag.get("scope") == gold["scope"]
    key = key_ok(tag.get("key"), gold)
    strict, lenient = condition_ok(tag.get("condition"), gold["condition"])
    return {"tagged": True, "scope_ok": scope, "key_ok": key, "condition_ok": strict, "condition_lenient_ok": lenient,
            "all_ok": scope and key is not False and lenient}


# ---- matching notes to gold memories --------------------------------------------------------------------------------

def match_notes(texts, pair, judge, episode, condition):
    """{text: [{"id", "keeps_limit"}] or None (unknown)} for each distinct note text. Verbatim quotes first, the judge for the rest."""
    memories = pair["memories"]
    found = {t: verbatim_matches(t, memories) for t in dict.fromkeys(t for t in texts if t)}
    left = [t for t, m in found.items() if not m]
    if left:
        res = judge.notes(statements=[(m["memory_id"], m["text"]) for m in memories], notes=left, episode=episode, condition=condition)
        for t, r in zip(left, res if res is not None else [None] * len(left)):
            found[t] = r
    return found


def _ids(notes):
    """Union of matched memory ids over notes; None if no note could be matched (all unknown)."""
    known = [n for n in notes if n is not None]
    if notes and not known:
        return None
    return {x["id"] for n in known for x in n}


def _all_or_none(values):
    if any(v is False for v in values):
        return False
    if values and all(v is True for v in values):
        return True
    return None


# ---- one log --------------------------------------------------------------------------------------------------------

def score_log(log, ep, judge, override=None):
    """Return (record, tag_checks) for one run log. `override` is a human label {"action", "retention"} or None."""
    pair, probe = ep["pair"], ep["probe"]
    name = log["condition"]
    info = condition_info(name, log)
    usage = log.get("usage") or {}
    by = usage.get("by_component") or {}
    rec = {
        "condition": name, "episode_id": ep["episode_id"], "pair_id": pair["pair_id"], "conflict_type": pair["conflict_type"],
        "label": ep["label"], "in_scope": probe["in_scope"], "deciding_rule": probe["deciding_rule"], "decision": probe["decision"],
        "expected_action": probe["expected_action"], "expected_memory": probe["expected_memory"],
        "role": info["role"], "system": info["system"], "layer": info["layer"],
        "status": "error" if log.get("error") or "agent" not in log else "ok",
        "error": (log.get("error") or {}).get("type"), "probe_changed": log.get("probe") not in (None, probe["text"]),
        "cost_usd": usage.get("total_cost_usd", 0.0),
        "prompt_tokens": sum(c.get("prompt_tokens", 0) for c in by.values()),
        "completion_tokens": sum(c.get("completion_tokens", 0) for c in by.values()),
        "cost_by_component": {k: c.get("cost_usd", 0.0) for k, c in by.items()},
        "action": None, "action_source": None, "action_evidence": "", "judge_action": None, "keyword_action": None,
        "chosen_memory": None, "category": None, "correct": None,
        "retention": None, "retention_source": None, "judge_retention": None, "retention_evidence": "",
        "stored_n": None, "retrieved_n": None, "expected_stored": None, "expected_retrieved": None,
        "scope_problems": "", "stage": None, "write_found": None, "write_total": None, "tags_kept": None, "tags_total": None,
        "first_line": (log.get("agent") or {}).get("first_line", ""),
    }
    if rec["status"] != "ok":
        return rec, []

    cands = candidates(pair, probe)
    checks = [rc["check"] for rc in pair["retention_checks"]]
    keyword = (log.get("gold_ref") or {}).get("action_first_mentioned")
    rec["keyword_action"] = keyword
    verdict = judge.answer(request=probe["text"], answer=log["agent"]["response"], decision=probe["decision"].replace("_", " "),
                           options=list(cands), checks=checks, episode=ep["episode_id"], condition=name)
    if verdict:
        rec.update(action=verdict["action"], action_source="judge", action_evidence=verdict["action_evidence"],
                   judge_action=verdict["action"], retention=_all_or_none(verdict["checks"]), judge_retention=_all_or_none(verdict["checks"]),
                   retention_source="judge", retention_evidence=" | ".join(e for e in verdict["check_evidence"] if e))
    elif keyword:
        rec.update(action=keyword, action_source="keyword")
    if override:
        if override.get("action"):
            rec.update(action=override["action"], action_source="human")
        if override.get("retention") is not None:
            rec.update(retention=override["retention"], retention_source="human")
    rec["chosen_memory"] = cands.get(rec["action"])
    rec["category"] = classify(pair, probe, rec["action"])
    if info["role"] == "floor" and rec["category"] in ("over_apply", "under_apply", "superseded"):
        rec["category"] = "default"
    rec["correct"] = None if rec["category"] is None else rec["category"] == "correct"

    tag_checks, problems = [], []
    if info["role"] == "floor":
        rec["expected_retrieved"] = False
    elif info["system"] is None:
        rec["expected_retrieved"] = True if info["role"] == "control" else None
    else:
        problems, tag_checks = _pipeline(log, ep, info, judge, rec)
    rec["scope_problems"] = ";".join(f"{kind}:{mid}" for kind, mid in problems)
    rec["stage"] = _stage(rec, info, problems)
    return rec, tag_checks


def _pipeline(log, ep, info, judge, rec):
    """Retrieval, scope information and tag checks for a memory-system condition. Fills rec in place."""
    pair, probe = ep["pair"], ep["probe"]
    gold = {m["memory_id"]: m["gold"] for m in pair["memories"]}
    relevant = {m["memory_id"] for m in pair["memories"] if m["decision"] == probe["decision"]}
    use_stored = info["system"] in STORED_IS_MEMORIES and log.get("stored") is not None
    stored = [note_text(d) for d in log.get("stored") or []] if use_stored else []
    retrieved = [note_text(r) for r in log.get("retrieved") or []]
    written = [note_text(w) for w in log.get("written") or []]
    found = match_notes(stored + retrieved + written, pair, judge, ep["episode_id"], log["condition"])
    on = lambda texts: [found.get(t) if t else [] for t in texts]  # noqa: E731
    stored_m, retrieved_m, written_m = on(stored), on(retrieved), on(written)

    rec["retrieved_n"] = len(retrieved)
    retrieved_ids = _ids(retrieved_m)
    rec["expected_retrieved"] = None if retrieved_ids is None else probe["expected_memory"] in retrieved_ids
    if use_stored:
        rec["stored_n"] = len(stored)
        stored_ids = _ids(stored_m)
        rec["expected_stored"] = None if stored_ids is None else probe["expected_memory"] in stored_ids

    tagged = log.get("tagged") or []
    problems, checks = [], []
    base = {"condition": log["condition"], "episode_id": ep["episode_id"], "pair_id": pair["pair_id"]}
    for i, note in enumerate(retrieved_m):
        tag = tagged[i].get("tag") if i < len(tagged) and isinstance(tagged[i], dict) else None
        for x in note or []:
            if info["layer"] is None:
                if x["id"] in relevant and x["keeps_limit"] is False:
                    problems.append(("scope_lost", x["id"]))
                continue
            cmp = compare_tag(tag, gold[x["id"]])
            if len(note) == 1:
                checks.append({**base, "memory_id": x["id"], "source": "read_back" if info["layer"] == "write" else "read_tagger",
                               "gold_scope": gold[x["id"]]["scope"], "pred_scope": (tag or {}).get("scope"), **cmp})
            if x["id"] in relevant and not cmp["all_ok"]:
                lost = info["layer"] == "read" and x["keeps_limit"] is False
                problems.append(("scope_lost" if lost else "tagging", x["id"]))

    if info["layer"] == "write":
        for w, note in zip(log.get("written") or [], written_m):
            if note and len(note) == 1:
                g = gold[note[0]["id"]]
                checks.append({**base, "memory_id": note[0]["id"], "source": "write_tagger", "gold_scope": g["scope"],
                               "pred_scope": (w.get("tag") or {}).get("scope"), **compare_tag(w.get("tag"), g)})
        hit = {x["id"] for note in written_m if note for x in note}
        rec["write_found"], rec["write_total"] = len(hit & set(gold)), len(gold)  # write-time tagger's recall of gold memories
        rec["tags_kept"] = sum(bool(t.get("tag")) for t in tagged if isinstance(t, dict))  # tags that survived storage
        rec["tags_total"] = len(tagged)
    return sorted(set(problems)), checks


def _stage(rec, info, problems):
    if rec["correct"] is None:
        return None
    if rec["correct"]:
        return "correct"
    if info["role"] == "floor":
        return "no_memory"
    if info["system"] is None:
        return "reasoning"
    if rec["expected_retrieved"] is None:
        return "unknown"
    if not rec["expected_retrieved"]:
        return "extraction" if rec["expected_stored"] is False else "retrieval"
    kinds = {kind for kind, _ in problems}
    return "scope_lost" if "scope_lost" in kinds else "tagging" if "tagging" in kinds else "reasoning"
