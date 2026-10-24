"""Step 7 tables: aggregate scored records into the README metrics. Every function returns a list of row dicts,
which report.py writes as CSV and as Markdown."""
from collections import Counter, defaultdict

from agent.conditions import CONDITION_INFO, SYSTEMS
from scoring.records import CATEGORIES, STAGES
from scoring.stats import cohen_kappa, mcnemar_exact, wilson

CONFLICT_TYPES = ("project_override", "single_task_override", "conditional_scope", "same_scope_supersession", "same_scope_specificity")
SOURCES = {"write": "write_tagger", "read": "read_tagger"}  # the tags each scope layer is scored on


def has_scores(records, condition):
    return any(r["condition"] == condition and r["status"] == "ok" and r["correct"] is not None for r in records)


def order(records):
    """Conditions in registry order (floor, control, then each system's baseline and treatments), unknown ones last."""
    names = list(dict.fromkeys(r["condition"] for r in records))
    return [c for c in CONDITION_INFO if c in names] + sorted(c for c in names if c not in CONDITION_INFO)


def scored(records, condition=None):
    return [r for r in records if r["status"] == "ok" and r["correct"] is not None and condition in (None, r["condition"])]


def rate(k, n):
    return k / n if n else None


def _role(records, c):
    return next((r["role"] for r in records if r["condition"] == c), None)


def _pairs(rs):
    """(pairs with both probes scored, pairs with both probes correct)."""
    by = defaultdict(dict)
    for r in rs:
        by[r["pair_id"]][r["label"]] = r["correct"]
    both = [v for v in by.values() if len(v) == 2]
    return len(both), sum(all(v.values()) for v in both)


def adherence(records):
    """Correction adherence: episode level, in scope (probe A, under-application shows here), out of scope (probe B,
    over-application shows here) and pair level (both halves of a mirrored pair right, the README's definition)."""
    rows = []
    for c in order(records):
        rs = scored(records, c)
        k, n = sum(r["correct"] for r in rs), len(rs)
        a, b = [r for r in rs if r["in_scope"]], [r for r in rs if not r["in_scope"]]
        pn, pk = _pairs(rs)
        lo, hi = wilson(k, n)
        plo, phi = wilson(pk, pn)
        rows.append({
            "condition": c, "role": _role(records, c), "episodes": n, "correct": k, "adherence": rate(k, n), "ci_low": lo, "ci_high": hi,
            "in_scope_correct": sum(r["correct"] for r in a), "in_scope_n": len(a), "in_scope": rate(sum(r["correct"] for r in a), len(a)),
            "out_of_scope_correct": sum(r["correct"] for r in b), "out_of_scope_n": len(b), "out_of_scope": rate(sum(r["correct"] for r in b), len(b)),
            "pairs_both_correct": pk, "pairs": pn, "pair_adherence": rate(pk, pn), "pair_ci_low": plo, "pair_ci_high": phi,
            "errors": sum(r["condition"] == c and r["status"] == "error" for r in records),
            "unscored": sum(r["condition"] == c and r["status"] == "ok" and r["correct"] is None for r in records),
        })
    return rows


def adherence_by_type(records):
    rows = []
    for c in order(records):
        for t in CONFLICT_TYPES:
            rs = [r for r in scored(records, c) if r["conflict_type"] == t]
            pn, pk = _pairs(rs)
            k = sum(r["correct"] for r in rs)
            rows.append({"condition": c, "conflict_type": t, "correct": k, "episodes": len(rs), "adherence": rate(k, len(rs)),
                         "pairs_both_correct": pk, "pairs": pn})
    return rows


def retention(records):
    """Unrelated-memory retention: the share of answers that still follow the pair's unrelated standing preference."""
    rows = []
    for c in order(records):
        rs = [r for r in records if r["condition"] == c and r["status"] == "ok" and r["retention"] is not None]
        k = sum(r["retention"] for r in rs)
        lo, hi = wilson(k, len(rs))
        row = {"condition": c, "role": _role(records, c), "kept": k, "judged": len(rs), "retention": rate(k, len(rs)), "ci_low": lo, "ci_high": hi}
        for t in CONFLICT_TYPES:
            ts = [r for r in rs if r["conflict_type"] == t]
            row[t] = rate(sum(r["retention"] for r in ts), len(ts))
        rows.append(row)
    return rows


def retrieval_vs_action(records):
    """The README 2x2: was the memory that should win retrieved, and did the agent act right. No memory counts as
    retrieved wrong and the full transcript as retrieved right, since every memory is in its context."""
    rows = []
    for c in order(records):
        rs = [r for r in scored(records, c) if r["expected_retrieved"] is not None]
        cell = Counter((r["expected_retrieved"], r["correct"]) for r in rs)
        rr_aw, rr_ar, rw_aw, rw_ar = cell[(True, False)], cell[(True, True)], cell[(False, False)], cell[(False, True)]
        rows.append({"condition": c, "episodes": len(rs), "retrieved_right_acted_right": rr_ar, "retrieved_right_acted_wrong": rr_aw,
                     "retrieved_wrong_acted_right": rw_ar, "retrieved_wrong_acted_wrong": rw_aw,
                     "wrong_given_retrieved_right": rate(rr_aw, rr_aw + rr_ar), "failures_with_retrieval_right": rate(rr_aw, rr_aw + rw_aw)})
    return rows


def stages(records):
    rows = []
    for c in order(records):
        rs = scored(records, c)
        n = Counter(r["stage"] for r in rs)
        rows.append({"condition": c, "episodes": len(rs), **{s: n[s] for s in STAGES}})
    return rows


def categories(records):
    """What the wrong answers did. Over-application can only happen out of scope; it is the B-half failure."""
    rows = []
    for c in order(records):
        rs = scored(records, c)
        n = Counter(r["category"] for r in rs)
        b = [r for r in rs if not r["in_scope"]]
        a = [r for r in rs if r["in_scope"]]
        rows.append({"condition": c, "episodes": len(rs), **{k: n[k] for k in CATEGORIES},
                     "over_apply_rate_out_of_scope": rate(sum(r["category"] == "over_apply" for r in b), len(b)),
                     "under_apply_rate_in_scope": rate(sum(r["category"] == "under_apply" for r in a), len(a))})
    return rows


def tagging(checks, records):
    """Tagging accuracy per field against the gold labels. Write-time layers are scored on the tagger's own output
    (and, separately, on the tags read back after storage); read-time layers on the tags given to retrieved memories."""
    rows = []
    for c in order(records):
        for source in ("write_tagger", "read_back", "read_tagger"):
            cs = [x for x in checks if x["condition"] == c and x["source"] == source]
            if not cs:
                continue
            keyed = [x for x in cs if x["key_ok"] is not None]
            row = {"condition": c, "source": source, "tags": len(cs), "untagged": sum(not x["tagged"] for x in cs),
                   "scope": rate(sum(x["scope_ok"] for x in cs), len(cs)),
                   "key": rate(sum(bool(x["key_ok"]) for x in keyed), len(keyed)), "key_n": len(keyed),
                   "condition_strict": rate(sum(x["condition_ok"] for x in cs), len(cs)),
                   "condition_lenient": rate(sum(x["condition_lenient_ok"] for x in cs), len(cs)),
                   "all_fields": rate(sum(x["all_ok"] for x in cs), len(cs)), "write_recall": None, "tag_survival": None}
            if source == "write_tagger":
                rs = [r for r in records if r["condition"] == c and r["write_total"]]
                row["write_recall"] = rate(sum(r["write_found"] for r in rs), sum(r["write_total"] for r in rs))
                ts = [r for r in records if r["condition"] == c and r["tags_total"]]
                row["tag_survival"] = rate(sum(r["tags_kept"] for r in ts), sum(r["tags_total"] for r in ts))
            rows.append(row)
    return rows


def scope_confusion(checks):
    n = Counter((x["condition"], x["source"], x["gold_scope"], x["pred_scope"] or "none") for x in checks)
    return [{"condition": c, "source": s, "gold_scope": g, "predicted_scope": p, "count": k} for (c, s, g, p), k in sorted(n.items())]


def cost(records):
    rows = []
    components = sorted({k for r in records for k in r["cost_by_component"]})
    for c in order(records):
        rs = [r for r in records if r["condition"] == c]
        n = len(rs)
        rows.append({"condition": c, "logs": n, "total_usd": sum(r["cost_usd"] or 0 for r in rs),
                     "mean_usd_per_episode": rate(sum(r["cost_usd"] or 0 for r in rs), n),
                     "mean_prompt_tokens": rate(sum(r["prompt_tokens"] for r in rs), n),
                     "mean_completion_tokens": rate(sum(r["completion_tokens"] for r in rs), n),
                     **{f"mean_usd_{k}": rate(sum(r["cost_by_component"].get(k, 0) for r in rs), n) for k in components}})
    return rows


def comparisons(names):
    """The paired comparisons the hypotheses need, among the conditions present."""
    out = [("full_transcript", "no_memory")]
    for s in SYSTEMS:
        out += [(f"scope_write_{s}", s), (f"scope_read_{s}", s), (f"scope_write_{s}", f"scope_read_{s}"), (s, "full_transcript")]
    return [(x, y) for x, y in out if x in names and y in names]


def significance(records):
    """Exact McNemar tests on the episodes both conditions scored. The A and B probes of a pair are not independent,
    so treat p-values as a guide at this sample size, not a verdict."""
    rows = []
    for metric, field, ok in (("adherence", "correct", scored), ("retention", "retention", None)):
        for x, y in comparisons(order(records)):
            def values(c):
                rs = ok(records, c) if ok else [r for r in records if r["condition"] == c and r["status"] == "ok" and r[field] is not None]
                return {r["episode_id"]: r[field] for r in rs}
            vx, vy = values(x), values(y)
            common = sorted(set(vx) & set(vy))
            if not common:
                continue
            b = sum(vx[e] and not vy[e] for e in common)
            c = sum(vy[e] and not vx[e] for e in common)
            rows.append({"metric": metric, "condition": x, "baseline": y, "episodes": len(common),
                         "condition_rate": rate(sum(vx[e] for e in common), len(common)), "baseline_rate": rate(sum(vy[e] for e in common), len(common)),
                         "only_condition_right": b, "only_baseline_right": c, "p_value": mcnemar_exact(b, c)})
    return rows


def pair_matrix(records):
    """One row per pair: which halves each condition got right ("AB" both, "A-" only in scope, "-B" only out of scope)."""
    names = order(records)
    cell = {(r["condition"], r["pair_id"], r["label"]): r["correct"] for r in scored(records)}
    pairs = sorted({(r["pair_id"], r["conflict_type"]) for r in records})
    rows = []
    for pid, ctype in pairs:
        row = {"pair_id": pid, "conflict_type": ctype}
        for c in names:
            a, b = cell.get((c, pid, "A")), cell.get((c, pid, "B"))
            row[c] = "?" if a is None or b is None else ("A" if a else "-") + ("B" if b else "-")
        rows.append(row)
    return rows


def judge_agreement(records):
    """How far to trust the judge: against the first-line keyword hint, and against the human review where it exists."""
    rows = []
    kw = [r for r in records if r["judge_action"] and r["keyword_action"]]
    rows.append({"check": "action: judge vs first-line keyword", "items": len(kw), "agree": sum(r["judge_action"] == r["keyword_action"] for r in kw),
                 "agreement": rate(sum(r["judge_action"] == r["keyword_action"] for r in kw), len(kw)), "kappa": cohen_kappa([(r["judge_action"], r["keyword_action"]) for r in kw])})
    for name, field, judged, source in (("action", "action", "judge_action", "action_source"), ("retention", "retention", "judge_retention", "retention_source")):
        hs = [r for r in records if r[source] == "human" and r[judged] is not None]
        pairs = [(r[judged], r[field]) for r in hs]
        rows.append({"check": f"{name}: judge vs human review", "items": len(hs), "agree": sum(a == b for a, b in pairs),
                     "agreement": rate(sum(a == b for a, b in pairs), len(pairs)), "kappa": cohen_kappa(pairs)})
    return rows
