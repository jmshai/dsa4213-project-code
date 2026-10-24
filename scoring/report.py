"""Step 7 report: write the scored records and tables.

    reports/summary.md           every metric as Markdown tables, with the definitions and caveats
    reports/examples.md          representative successes and failures, with what was retrieved and how it was tagged
    reports/episode_scores.csv   one row per condition and episode: judged action, category, stage, retention, cost
    reports/tables/*.csv         each summary table, for charts in the final report
    reports/figures/*.png        adherence against retention, adherence by conflict type, failure stages
"""
import csv
import json
from pathlib import Path

from scoring import figures, tables as T
from scoring.records import STAGES, condition_info

EPISODE_COLUMNS = (
    "condition", "episode_id", "pair_id", "conflict_type", "label", "in_scope", "deciding_rule", "expected_action", "action",
    "action_source", "correct", "category", "stage", "retention", "retention_source", "expected_stored", "expected_retrieved",
    "scope_problems", "keyword_action", "judge_action", "judge_retention", "write_found", "write_total", "tags_kept", "tags_total",
    "stored_n", "retrieved_n", "cost_usd", "prompt_tokens", "completion_tokens", "status", "error", "probe_changed",
    "first_line", "action_evidence", "retention_evidence")
SOURCE_NAMES = {"judge": "the LLM judge", "keyword": "the first-line keyword", "human": "your review"}
TYPE_NAMES = {"project_override": "Project override", "single_task_override": "Single-task override",
              "conditional_scope": "Conditional scope", "same_scope_supersession": "Same-scope supersession",
              "same_scope_specificity": "Same-scope specificity"}


def write_csv(path, rows, columns=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(columns or dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(r.get(k)) for k in columns})


def _cell(v):
    if isinstance(v, float):
        return round(v, 4)
    return json.dumps(v) if isinstance(v, (dict, list)) else v


def pct(x):
    return "–" if x is None else f"{100 * x:.0f}%"


def ci(lo, hi):
    return "" if lo is None else f" ({100 * lo:.0f}–{100 * hi:.0f})"


def frac(k, n):
    return "–" if not n else f"{k}/{n}"


def usd(x, digits=4):
    return "–" if x is None else f"${x:.{digits}f}"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in row) + " |" for row in rows]
    return "\n".join(out)


def build_tables(records, checks):
    return {"adherence": T.adherence(records), "adherence_by_type": T.adherence_by_type(records), "retention": T.retention(records),
            "retrieval_vs_action": T.retrieval_vs_action(records), "failure_stages": T.stages(records),
            "error_categories": T.categories(records), "tagging_accuracy": T.tagging(checks, records),
            "scope_confusion": T.scope_confusion(checks), "cost": T.cost(records), "significance": T.significance(records),
            "pair_matrix": T.pair_matrix(records), "judge_agreement": T.judge_agreement(records)}


def write_all(out, records, checks, logs, eps, meta):
    """Write every output under `out`. Returns {name: path}."""
    out = Path(out)
    tabs = build_tables(records, checks)
    paths = {"episode_scores": out / "episode_scores.csv"}
    write_csv(paths["episode_scores"], records, EPISODE_COLUMNS)
    write_csv(out / "tag_checks.csv", checks)
    for name, rows in tabs.items():
        if rows:
            write_csv(out / "tables" / f"{name}.csv", rows)
    figs = _figures(out / "figures", tabs, records)
    paths["summary"] = out / "summary.md"
    paths["summary"].write_text(summary_md(tabs, records, meta, figs))
    paths["examples"] = out / "examples.md"
    paths["examples"].write_text(examples_md(records, logs, eps))
    return paths | {f"figure:{k}": v for k, v in figs.items()}


def _figures(folder, tabs, records):
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("matplotlib is not installed, so no figures (uv add matplotlib). The numbers are all in summary.md.")
        return {}
    folder.mkdir(parents=True, exist_ok=True)
    made = {
        "adherence_vs_retention": figures.adherence_vs_retention(tabs["adherence"], tabs["retention"], condition_info, folder / "adherence_vs_retention.png"),
        "adherence_by_type": figures.adherence_heatmap(tabs["adherence_by_type"], [c for c in T.order(records) if T.has_scores(records, c)],
                                                       folder / "adherence_by_type.png"),
        "failure_stages": figures.failure_stages(tabs["failure_stages"], folder / "failure_stages.png"),
    }
    return {k: v for k, v in made.items() if v}


def _fig(figs, name, alt):
    return f"\n![{alt}](figures/{Path(figs[name]).name})\n" if name in figs else ""


def summary_md(tabs, records, meta, figs):
    s = [f"# Step 7 results\n",
         f"Scored {meta['scored_at']} from {meta['logs']} run logs in `{meta['log_dir']}`. Agent model `{meta['agent_model']}`. "
         f"Judge model `{meta['judge_model']}` (prompt `{meta['judge_version']}`). Gold labels: **{meta['gold_status']}**.",
         f"Run errors (not scored): {sum(r['status'] == 'error' for r in records)}. Answers with no judged action: "
         f"{sum(r['status'] == 'ok' and r['correct'] is None for r in records)}. Judge spend so far on this machine: {usd(meta.get('judge_usd'))}."]
    if meta.get("probe_changed"):
        s.append(f"\n**Warning:** {meta['probe_changed']} logs were run on probe text that no longer matches `episodes/pairs/`. Rerun them.")
    if meta.get("gold_status") == "draft":
        s.append("\nTagging accuracy uses the drafted gold labels. Rerun this after the annotators adjudicate them (README Step 3).")

    s.append("\n## 1. Correction adherence\n")
    s.append(md_table(["Condition", "Role", "Episodes right (95% CI)", "In scope (A)", "Out of scope (B)", "Pairs, both right (95% CI)"],
                      [[r["condition"], r["role"], f"{frac(r['correct'], r['episodes'])} = {pct(r['adherence'])}{ci(r['ci_low'], r['ci_high'])}",
                        frac(r["in_scope_correct"], r["in_scope_n"]), frac(r["out_of_scope_correct"], r["out_of_scope_n"]),
                        f"{frac(r['pairs_both_correct'], r['pairs'])} = {pct(r['pair_adherence'])}{ci(r['pair_ci_low'], r['pair_ci_high'])}"]
                       if r["episodes"] else [r["condition"], r["role"], f"not scored ({r['errors']} run errors)", "–", "–", "–"]
                       for r in tabs["adherence"]]))
    if any(not r["episodes"] for r in tabs["adherence"]):
        s.append("\nA condition marked not scored has no successful run yet. Fix what stopped it and rerun `agent.runner`: "
                 "finished episodes are skipped. Its other tables are left out until then.")
    s.append("\nProbe A sits inside the scoped memory's scope, so a miss there is under-application. Probe B sits outside it, so a "
             "miss is over-application. A pair counts only when both halves are right, so an agent that always picks the same "
             "memory, the newest one or the standing one, scores no pairs.")

    scored_names = [c for c in T.order(records) if T.has_scores(records, c)]
    keep = lambda rows: [r for r in rows if r["condition"] in scored_names]  # noqa: E731
    s.append("\n## 2. Adherence by conflict type\n")
    by = {(r["condition"], r["conflict_type"]): r for r in tabs["adherence_by_type"]}
    s.append(md_table(["Condition", *TYPE_NAMES.values()],
                      [[c, *(f"{frac(by[(c, t)]['correct'], by[(c, t)]['episodes'])}" for t in TYPE_NAMES)] for c in scored_names]))
    s.append("\nEpisodes right of episodes scored. Same-scope supersession and same-scope specificity test the two rules that "
             "settle conflicts inside one scope (rules 4 and 3), which is the lecturer's question about same-scope conflicts.")
    s.append(_fig(figs, "adherence_by_type", "Adherence by conflict type"))

    s.append("\n## 3. Unrelated-memory retention\n")
    s.append(md_table(["Condition", "Answers that kept the unrelated preference (95% CI)", *TYPE_NAMES.values()],
                      [[r["condition"], f"{frac(r['kept'], r['judged'])} = {pct(r['retention'])}{ci(r['ci_low'], r['ci_high'])}",
                        *(pct(r[t]) for t in TYPE_NAMES)] for r in keep(tabs["retention"])]))
    s.append("\nEach pair has an unrelated standing preference and a check the answer can be read against (`retention_checks`). "
             "The no-memory row is how often the agent does it anyway.")
    s.append(_fig(figs, "adherence_vs_retention", "Correction adherence against unrelated-memory retention"))

    s.append("\n## 4. Retrieval vs action\n")
    s.append(md_table(["Condition", "Retrieved right, acted right", "**Retrieved right, acted wrong**", "Retrieved wrong, acted right",
                       "Retrieved wrong, acted wrong", "Wrong when retrieval was right"],
                      [[r["condition"], r["retrieved_right_acted_right"], f"**{r['retrieved_right_acted_wrong']}**", r["retrieved_wrong_acted_right"],
                        r["retrieved_wrong_acted_wrong"], pct(r["wrong_given_retrieved_right"])] for r in keep(tabs["retrieval_vs_action"])]))
    s.append("\nRetrieved right means the memory that should win was among the retrieved notes, matched word for word or by the "
             "judge. No memory counts as retrieved wrong and the full transcript as retrieved right. The bold column is the gap "
             "the project is about: the right memory was in front of the agent and it still acted wrong.")

    s.append("\n## 5. Where failures happen\n")
    s.append(md_table(["Condition", "Episodes", *[x.replace("_", " ") for x in STAGES if x != "unknown"], "unknown"],
                      [[r["condition"], r["episodes"], *(r[x] for x in STAGES if x != "unknown"), r["unknown"]] for r in keep(tabs["failure_stages"])]))
    s.append("\nEach wrong answer is counted once, at the first stage that failed. Extraction: Mem0 did not keep the memory that "
             "should win. Retrieval: it was not retrieved. Scope lost: a competing memory reached the agent without its project, "
             "task or condition. Tagging: the scope layer's tag on a competing memory was wrong or missing. Reasoning: the agent "
             "had everything it needed. Supermemory lists documents rather than the memories it extracts, so its extraction "
             "losses show up as retrieval.")
    s.append(_fig(figs, "failure_stages", "Failure stages per condition"))
    s.append("\nWhat the wrong answers did:\n")
    s.append(md_table(["Condition", "Over-applied", "Under-applied", "Superseded memory", "Other action", "Hedged", "Default (no memory)",
                       "Over-apply rate, probe B", "Under-apply rate, probe A"],
                      [[r["condition"], r["over_apply"], r["under_apply"], r["superseded"], r["other_action"], r["hedged"], r["default"],
                        pct(r["over_apply_rate_out_of_scope"]), pct(r["under_apply_rate_in_scope"])] for r in keep(tabs["error_categories"])]))
    s.append("\nThe no-memory floor saw no memory, so its wrong picks count as its default choice rather than as a misapplied memory.")

    s.append("\n## 6. Tagging accuracy\n")
    if tabs["tagging_accuracy"]:
        s.append(md_table(["Condition", "Tags from", "Tags", "Scope", "Key", "Condition (strict / lenient)", "All fields",
                           "Write-time recall", "Tags kept after storage"],
                          [[r["condition"], r["source"].replace("_", " "), r["tags"], pct(r["scope"]), f"{pct(r['key'])} of {r['key_n']}",
                            f"{pct(r['condition_strict'])} / {pct(r['condition_lenient'])}", pct(r["all_fields"]),
                            pct(r["write_recall"]), pct(r["tag_survival"])] for r in tabs["tagging_accuracy"]]))
        s.append("\nEach tag is compared with the gold label of the one memory its note records (notes that merge several "
                 "memories are left out). Key is scored for project memories (every word of the gold project name must appear) "
                 "and standing ones (no key); single-task keys are task ids, which are gold-only, so they are not scored. "
                 "Condition is strict when variable, operator and value all match, lenient when operator and value match. "
                 "Write-time recall is the share of gold memories the write-time tagger extracted at all. "
                 "\"Read back\" rows are the write-time tags after the memory system stored and returned them.")
        s.append("\nScope confusion (gold scope → tagged scope):\n")
        s.append(md_table(["Condition", "Tags from", "Gold", "Tagged", "Count"],
                          [[r["condition"], r["source"].replace("_", " "), r["gold_scope"], r["predicted_scope"], r["count"]]
                           for r in tabs["scope_confusion"] if r["gold_scope"] != r["predicted_scope"]] or [["–", "", "", "", "no confusions"]]))
    else:
        s.append("No scope-layer logs were scored.")

    s.append("\n## 7. Cost\n")
    comps = sorted({k[len("mean_usd_"):] for r in tabs["cost"] for k in r if k.startswith("mean_usd_") and k != "mean_usd_per_episode"})
    s.append(md_table(["Condition", "Logs", "Total", "Per episode", "Prompt tokens / episode", "Completion tokens / episode",
                       *[f"{c} / episode" for c in comps]],
                      [[r["condition"], r["logs"], usd(r["total_usd"]), usd(r["mean_usd_per_episode"], 5), f"{r['mean_prompt_tokens'] or 0:,.0f}",
                        f"{r['mean_completion_tokens'] or 0:,.0f}", *(usd(r.get(f"mean_usd_{c}"), 5) for c in comps)] for r in tabs["cost"]]))
    s.append("\nOpenRouter spend recorded in each log, failed attempts included. Supermemory bills its own processing, so its "
             "calls are $0 here. Judge spend is separate (above).")

    s.append("\n## 8. Paired comparisons\n")
    s.append(md_table(["Metric", "Condition", "vs", "Episodes", "Rate", "vs rate", "Only condition right", "Only baseline right", "p (exact McNemar)"],
                      [[r["metric"], r["condition"], r["baseline"], r["episodes"], pct(r["condition_rate"]), pct(r["baseline_rate"]),
                        r["only_condition_right"], r["only_baseline_right"], f"{r['p_value']:.3f}"] for r in tabs["significance"]]
                      or [["–"] * 9]))
    s.append("\nThe test uses only the episodes where exactly one of the two conditions was right. With 40 episodes and the A "
             "and B probes of a pair not independent, read p-values as a guide, and report the counts with them.")

    s.append("\n## 9. Pair by pair\n")
    names = scored_names
    s.append(md_table(["Pair", "Conflict type", *names], [[r["pair_id"], TYPE_NAMES.get(r["conflict_type"], r["conflict_type"]),
                                                          *(f"`{r[c]}`" for c in names)] for r in tabs["pair_matrix"]]))
    s.append("\n`AB` both probes right, `A-` only the in-scope probe, `-B` only the out-of-scope probe, `--` neither, `?` not scored. "
             "In the no-memory column a single right half shows the agent's default for that decision.")

    s.append("\n## 10. How far to trust the judge\n")
    s.append(md_table(["Check", "Items", "Agree", "Agreement", "Cohen's kappa"],
                      [[r["check"], r["items"], r["agree"], pct(r["agreement"]), "–" if r["kappa"] is None else f"{r['kappa']:.2f}"]
                       for r in tabs["judge_agreement"]]))
    s.append("\nThe first-line keyword is the rough check from Step 6 and is often wrong when an answer names both options, so "
             "disagreement with it is expected. The human review is the real check: `uv run python -m scoring.review`, fill in "
             "`reports/review/judge_review.csv`, then rerun `scoring.score`. Human labels replace the judge's for those episodes.")

    s.append("\n## Caveats\n")
    s.append("\n".join(f"- {c}" for c in (
        "40 episodes per condition gives wide intervals; differences under about 20 points are within noise.",
        "One run per condition. The agent runs at temperature 0, but Mem0's and Supermemory's extraction varies between runs.",
        "The plain baselines show the agent memories in retrieval order with no dates, so the agent cannot apply \"the later one wins\" there.",
        "The scope-layer conditions add both the tags and the list of resolution rules to the prompt, so their gain cannot be split between the two.",
        f"The judge is `{meta['judge_model']}`; check it against the human review before quoting the numbers.",
    )))
    return "\n".join(s) + "\n"


def _short(text, n=220):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def examples_md(records, logs, eps, per_condition=3):
    """For each condition: a few failures from different stages, retrieved-right-acted-wrong first, and one success."""
    by_key = {(log["condition"], log["episode_id"]): log for log in logs}
    s = ["# Representative successes and failures\n",
         "Chosen by rule, not by hand: for each condition, wrong answers from different failure stages (cases where the right "
         "memory was retrieved come first), then one right answer on an in-scope probe. Episode ids sort ties.\n"]
    for c in T.order(records):
        rs = T.scored(records, c)
        if not rs:
            continue
        wrong = sorted((r for r in rs if not r["correct"]),
                       key=lambda r: (not r["expected_retrieved"], STAGES.index(r["stage"]) if r["stage"] in STAGES else 99, r["episode_id"]))
        picked, stages_seen = [], set()
        for r in wrong:
            if r["stage"] not in stages_seen:
                picked.append(r)
                stages_seen.add(r["stage"])
            if len(picked) == per_condition:
                break
        right = sorted((r for r in rs if r["correct"] and r["in_scope"]), key=lambda r: (-r["deciding_rule"], r["episode_id"]))
        picked += right[:1]
        s.append(f"\n## {c}\n")
        for r in picked:
            s.append(_example(r, by_key.get((c, r["episode_id"])), eps[r["episode_id"]]))
    return "\n".join(s) + "\n"


def _example(r, log, ep):
    pair, probe = ep["pair"], ep["probe"]
    mems = {m["memory_id"]: m for m in pair["memories"]}
    verdict = "right" if r["correct"] else f"wrong: {r['category'].replace('_', ' ')}, failed at {r['stage'].replace('_', ' ')}"
    chosen = mems.get(r["chosen_memory"])
    lines = [f"### {r['episode_id']} · {TYPE_NAMES.get(r['conflict_type'], r['conflict_type'])}, probe {r['label']} · {verdict}\n",
             f"- **Request:** {_short(probe['text'], 400)}",
             f"- **Should use:** {probe['expected_action']} ({probe['expected_memory']}: \"{mems[probe['expected_memory']]['text']}\")",
             f"- **Used:** {r['action']} (labelled by {SOURCE_NAMES.get(r['action_source'], r['action_source'])})"
             + (f"; that is what {chosen['memory_id']} asks for: \"{chosen['text']}\""
                if chosen and not r["correct"] and r["category"] != "default" else ""),
             f"- **Judge's evidence:** \"{_short(r['action_evidence'], 200)}\"" if r["action_evidence"] else "",
             f"- **Agent's first line:** {_short(r['first_line'], 200)}"]
    if log and log.get("retrieved"):
        tags = log.get("tagged") or []
        lines.append("- **Retrieved:**")
        for i, h in enumerate(log["retrieved"][:6]):
            tag = tags[i].get("tag") if i < len(tags) and isinstance(tags[i], dict) else None
            label = f" `[{tag.get('scope')}, key: {tag.get('key')}, condition: {tag.get('condition')}]`" if tag else (" `[untagged]`" if tags else "")
            lines.append(f"  {i + 1}. {_short(h.get('text'), 160)}{label}")
        if len(log["retrieved"]) > 6:
            lines.append(f"  … and {len(log['retrieved']) - 6} more")
    elif r["condition"] == "full_transcript":
        lines.append("- **Retrieved:** the full transcript")
    return "\n".join(x for x in lines if x) + "\n"
