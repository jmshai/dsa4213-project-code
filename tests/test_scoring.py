"""Step 7 scoring, offline: synthetic run logs and a stand-in judge, no API calls."""
import csv
import json
import re

import pytest

from agent import runner
from agent.conditions import CONDITION_INFO
from episodes.loader import episodes
from scoring import judge as J, records as R, report, review, score, tables as T
from scoring.stats import cohen_kappa, mcnemar_exact, wilson
from scoring.textmatch import norm, verbatim_matches

EPS = {e["episode_id"]: e for e in episodes()}
SCOPE_CUE = re.compile(r"^(actually, |update: |change of plan: )?((for|on) (the )?project \w+( thesis)?,? |this time, |just for this one, |for this one, )", re.I)


# ---- synthetic logs ------------------------------------------------------------------------------------------------

def rewrite(text, drop_scope=False):
    """A Mem0-style paraphrase that never quotes the memory word for word."""
    t = SCOPE_CUE.sub("", text) if drop_scope else text
    return "User " + re.sub(r"\buse\b", "wants", t[0].lower() + t[1:]).rstrip(".")


def make_log(ep, condition, *, action=None, retained=True, drop_scope=False, store_expected=True, retrieve_expected=True,
             wrong_tags=False, error=None):
    pair, probe = ep["pair"], ep["probe"]
    action = action or probe["expected_action"]
    response = f"{action} it is.\nHere is the code. {'RETAINED' if retained else 'nothing else'}"
    log = {"episode_id": ep["episode_id"], "condition": condition, "probe": probe["text"], "error": None, "attempts": 1,
           "memories": "", "stored": None, "retrieved": [], "tagged": None, "written": None, "namespace": None, "prompt": "",
           "agent": {"model": "m/x", "response": response, "first_line": response.splitlines()[0]},
           "usage": {"total_cost_usd": 0.002, "by_component": {"agent": {"calls": 1, "prompt_tokens": 400, "completion_tokens": 150,
                                                                         "reasoning_tokens": 0, "cost_usd": 0.002}}},
           "gold_ref": runner._gold_ref(ep, response)}
    if error:
        log["error"] = {"type": error, "message": "boom", "traceback": ""}
        del log["agent"]
        return log
    info = CONDITION_INFO[condition]
    if not info["system"]:
        return log
    order = {s["session_id"]: s["order"] for s in pair["sessions"]}
    notes = []
    for m in pair["memories"]:
        if m["memory_id"] == probe["expected_memory"] and not store_expected:
            continue
        lose = drop_scope and m["role"] == "scoped" and info["layer"] != "write"
        notes.append((m, {"memory": rewrite(m["text"], lose), "created_at": f"2026-01-0{order[m['session_id']]}T00:00:0{len(notes)}"}))
    log["stored"] = [n for _, n in notes]
    hits = [(m, n) for m, n in notes if retrieve_expected or m["memory_id"] != probe["expected_memory"]]
    log["retrieved"] = [{"text": n["memory"], "score": 0.5, "raw": n} for _, n in hits]

    def tag(m):
        g = dict(m["gold"])
        if g["scope"] == "single_task":
            g["key"] = None
        if wrong_tags and m["role"] == "scoped":
            g = {"scope": "standing", "key": None, "condition": None}
        return g
    if info["layer"]:
        log["tagged"] = [{"text": n["memory"], "tag": tag(m)} for m, n in hits]
    if info["layer"] == "write":
        log["written"] = [{"text": m["text"], "tag": tag(m)} for m in pair["memories"]]
    return log


def fake_reply(messages):
    """Stand-in judge: the option named in the answer's first line; checks pass when the answer says RETAINED;
    notes match the statement they share most words with."""
    user = messages[1]["content"]
    if "<answer>" in user:
        answer = user.split("<answer>\n", 1)[1].split("\n</answer>", 1)[0]
        options = re.findall(r'^- "(.+)"$', user, re.M)
        first = answer.splitlines()[0].lower()
        found = [o for o in options if o.lower() in first]
        n_checks = len(re.findall(r"^C\d+: ", user, re.M))
        return json.dumps({"action_evidence": answer.splitlines()[0], "action": max(found, key=len) if found else "none",
                           "checks": [{"id": f"C{i}", "evidence": "", "passed": "RETAINED" in answer} for i in range(1, n_checks + 1)]})
    statements = re.findall(r"^\[(m\d+)\] (.+)$", user, re.M)
    notes = re.findall(r"^(\d+)\. (.+)$", user.split("A memory system saved the notes below.\n", 1)[1], re.M)
    words = lambda t: set(re.findall(r"[a-z0-9]+", t.lower())) - {"the", "a", "for", "on", "user", "wants", "use"}  # noqa: E731
    out = []
    core = lambda s: words(SCOPE_CUE.sub("", s))  # noqa: E731 - what the statement asks for, without its scope cue
    for i, text in notes:
        best = max(statements, key=lambda s: len(core(s[1]) & words(text)) / max(1, len(core(s[1]))))
        share = len(core(best[1]) & words(text)) / max(1, len(core(best[1])))
        keeps = not SCOPE_CUE.match(best[1]) or "project" in text.lower() or "this" in text.lower()
        out.append({"index": int(i), "matches": [{"id": best[0], "keeps_limit": keeps}] if share >= 0.5 else []})
    return json.dumps({"notes": out})


@pytest.fixture
def fake_judge(monkeypatch):
    sent = []

    def chat(self, messages, episode, condition):
        sent.append(messages)
        self.calls += 1
        return fake_reply(messages), 0.0001
    monkeypatch.setattr(J.Judge, "_chat", chat)
    return sent


@pytest.fixture
def judge(tmp_path, fake_judge):
    return J.Judge(J.Cache(tmp_path / "cache.jsonl"))


def scored(ep_id, condition, judge, **kw):
    return R.score_log(make_log(EPS[ep_id], condition, **kw), EPS[ep_id], judge)


# ---- statistics and matching ---------------------------------------------------------------------------------------

def test_wilson_mcnemar_kappa():
    lo, hi = wilson(20, 40)
    assert round(lo, 3) == 0.352 and round(hi, 3) == 0.648 and wilson(0, 0) == (None, None)
    assert wilson(0, 10)[0] == 0 and wilson(10, 10)[1] == pytest.approx(1)
    assert mcnemar_exact(0, 0) == 1 and mcnemar_exact(5, 0) == pytest.approx(0.0625) and mcnemar_exact(3, 3) == 1
    assert cohen_kappa([("a", "a"), ("b", "b")]) == 1 and cohen_kappa([("a", "a")]) is None
    assert cohen_kappa([("a", "b"), ("b", "a")]) == -1


def test_verbatim_matching():
    mems = EPS["ss-01a"]["pair"]["memories"]
    assert norm("User:  For Project Lantern,  use FastAPI. ") == "for project lantern, use fastapi"
    assert verbatim_matches("User: For Project Lantern, use FastAPI.", mems) == [{"id": "m2", "keeps_limit": True}]
    assert verbatim_matches("for Project Lantern, switch to Django", mems) == [{"id": "m3", "keeps_limit": None}]
    session = EPS["ss-01a"]["pair"]["sessions"][2]["text"]
    assert {x["id"] for x in verbatim_matches(session, mems)} == {"m1", "m4"}
    assert verbatim_matches("Lantern uses Django now", mems) == []  # a rewrite goes to the judge


def test_pick_option_prefers_the_longest_option():
    opts = ["economy", "premium economy"]
    assert J.pick_option("Premium economy", opts) == "premium economy"
    assert J.pick_option("economy.", opts) == "economy"
    assert J.pick_option("They booked premium economy class", opts) == "premium economy"
    assert J.pick_option("MIXED", opts) == "mixed" and J.pick_option("none", opts) == "none"
    with pytest.raises(ValueError):
        J.pick_option("business", opts)


def test_parse_answer_and_notes_tolerate_noise():
    reply = '```json\n{"action_evidence": "import polars", "action": "Polars", "checks": [{"id": "c1", "passed": "true"}]}\n```'
    out = J.parse_answer(reply, ["pandas", "polars"], 2)
    assert out["action"] == "polars" and out["checks"] == [True, None]
    notes = J.parse_notes('{"notes": [{"index": 2, "matches": [{"id": "m9"}, {"id": "m1", "keeps_limit": false}, "m2"]}]}', 2, {"m1", "m2"})
    assert notes == [None, [{"id": "m1", "keeps_limit": False}, {"id": "m2", "keeps_limit": None}]]
    with pytest.raises(ValueError):
        J.parse_notes('{"tags": []}', 1, {"m1"})


def test_tag_comparison_normalises_keys_and_conditions():
    project = {"scope": "project", "key": "Project Lumen", "condition": None}
    assert R.compare_tag({"scope": "project", "key": "Project Lumen thesis", "condition": None}, project)["all_ok"]
    assert not R.compare_tag({"scope": "project", "key": "Project Sable", "condition": None}, project)["key_ok"]
    assert R.condition_ok("rows > 1M", "rows > 1000000") == (True, True)
    assert R.condition_ok("dataset_rows > 1,000,000", "rows > 1000000") == (False, True)
    assert R.condition_ok("size_mb >= 100", "size_mb > 100") == (False, False)
    assert R.condition_ok("audience = Board", "audience == board") == (True, True)
    single = {"scope": "single_task", "key": "t-1", "condition": None}
    assert R.compare_tag({"scope": "single_task", "key": None, "condition": None}, single)["key_ok"] is None
    assert R.compare_tag(None, single)["all_ok"] is False


def test_every_competing_action_gets_a_category():
    for ep in EPS.values():
        pair, probe = ep["pair"], ep["probe"]
        cats = {a: R.classify(pair, probe, a) for a in R.candidates(pair, probe)}
        assert cats[probe["expected_action"]] == "correct"
        wrong = [c for a, c in cats.items() if a != probe["expected_action"]]
        assert wrong and set(wrong) <= {"over_apply", "under_apply", "superseded"}
        assert ("over_apply" in wrong) == (not probe["in_scope"]) or pair["conflict_type"] == "single_task_override"
    assert R.classify(EPS["ss-01a"]["pair"], EPS["ss-01a"]["probe"], "fastapi") == "superseded"
    assert R.classify(EPS["po-01a"]["pair"], EPS["po-01a"]["probe"], "mixed") == "hedged"


# ---- one log -------------------------------------------------------------------------------------------------------

def test_controls(judge):
    rec, checks = scored("po-01a", "no_memory", judge, action="polars")
    assert rec["category"] == "default" and rec["stage"] == "no_memory" and rec["expected_retrieved"] is False and not checks
    rec, _ = scored("po-01b", "full_transcript", judge, action="pandas", retained=False)
    assert rec["category"] == "over_apply" and rec["stage"] == "reasoning" and rec["expected_retrieved"] is True
    assert rec["retention"] is False and rec["action_source"] == "judge"


def test_memory_condition_stages(judge):
    assert scored("po-01a", "mem0", judge)[0]["stage"] == "correct"
    assert scored("po-01a", "mem0", judge, action="polars")[0]["stage"] == "reasoning"
    rec = scored("po-01b", "mem0", judge, action="pandas", drop_scope=True)[0]
    assert rec["stage"] == "scope_lost" and "scope_lost:m2" in rec["scope_problems"]
    rec = scored("po-01a", "mem0", judge, action="polars", store_expected=False)[0]
    assert rec["stage"] == "extraction" and rec["expected_stored"] is False
    assert scored("po-01a", "mem0", judge, action="polars", retrieve_expected=False)[0]["stage"] == "retrieval"
    rec = scored("po-01a", "supermemory", judge, action="polars", store_expected=False)[0]
    assert rec["stage"] == "retrieval" and rec["expected_stored"] is None  # Supermemory's stored list is documents


def test_scope_layer_tags_are_checked(judge):
    rec, checks = scored("po-01b", "scope_write_mem0", judge, action="pandas", wrong_tags=True)
    assert rec["stage"] == "tagging"
    by_source = {c["source"] for c in checks}
    assert by_source == {"write_tagger", "read_back"}
    m2 = [c for c in checks if c["memory_id"] == "m2" and c["source"] == "write_tagger"]
    assert m2 and not m2[0]["scope_ok"] and m2[0]["pred_scope"] == "standing"
    assert rec["write_found"] == rec["write_total"] == 3 and rec["tags_kept"] == rec["tags_total"] == 3
    rec, checks = scored("st-01a", "scope_read_mem0", judge)
    assert rec["stage"] == "correct" and {c["source"] for c in checks} == {"read_tagger"}
    assert all(c["all_ok"] for c in checks)  # single_task keys are not scored, so a null key is fine


def test_errors_are_kept_out_of_the_rates(judge):
    rec, checks = R.score_log(make_log(EPS["po-01a"], "mem0", error="RateLimitError"), EPS["po-01a"], judge)
    assert rec["status"] == "error" and rec["correct"] is None and not checks
    assert T.adherence([rec])[0]["episodes"] == 0 and T.adherence([rec])[0]["errors"] == 1


# ---- the judge -----------------------------------------------------------------------------------------------------

def test_judge_is_never_told_the_expected_action(judge, fake_judge):
    for ep_id in ("po-01a", "po-01b"):
        scored(ep_id, "no_memory", judge, action="pandas")
    a, b = (m[1]["content"] for m in fake_judge)
    assert '- "pandas"\n- "polars"' in a  # alphabetical, whatever the expected action is
    assert a.replace("Marlin", "X") == b.replace("Tern", "X")
    assert "expected" not in a.lower() and "m2" not in a


def test_judge_caches_plans_and_falls_back(tmp_path, fake_judge, monkeypatch):
    cache = J.Cache(tmp_path / "c.jsonl")
    log = make_log(EPS["po-01a"], "mem0")
    plan = J.Judge(cache, mode="plan")
    R.score_log(log, EPS["po-01a"], plan)
    assert [k for k, _ in plan.planned] == ["answer", "notes"] and not fake_judge
    live = J.Judge(cache)
    R.score_log(log, EPS["po-01a"], live)
    assert live.calls == 2
    again = J.Judge(J.Cache(tmp_path / "c.jsonl"))  # a fresh process reads the file
    rec, _ = R.score_log(log, EPS["po-01a"], again)
    assert again.calls == 0 and rec["action_source"] == "judge"
    rec, _ = R.score_log(make_log(EPS["po-01b"], "no_memory"), EPS["po-01b"], J.Judge(cache, mode="offline"))
    assert rec["action_source"] == "keyword" and rec["action"] == "polars"

    monkeypatch.setattr(J.Judge, "_chat", lambda self, m, e, c: ("not json", None))
    bad = J.Judge(J.Cache(tmp_path / "bad.jsonl"))
    rec, _ = R.score_log(make_log(EPS["po-01b"], "no_memory"), EPS["po-01b"], bad)
    assert bad.errors and rec["action_source"] == "keyword" and not (tmp_path / "bad.jsonl").exists()


# ---- the command line and the report -------------------------------------------------------------------------------

def write_logs(folder, specs):
    for (condition, ep_id), kw in specs.items():
        path = folder / condition / f"{ep_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(make_log(EPS[ep_id], condition, **kw)))


SPECS = {
    ("no_memory", "po-01a"): {"action": "polars"}, ("no_memory", "po-01b"): {},
    ("no_memory", "ss-01a"): {"action": "falcon", "retained": False}, ("no_memory", "ss-01b"): {"retained": False},
    ("mem0", "po-01a"): {}, ("mem0", "po-01b"): {"action": "pandas", "drop_scope": True},
    ("mem0", "ss-01a"): {"action": "fastapi"}, ("mem0", "ss-01b"): {},
    ("scope_write_mem0", "po-01a"): {}, ("scope_write_mem0", "po-01b"): {},
    ("scope_write_mem0", "ss-01a"): {}, ("scope_write_mem0", "ss-01b"): {"error": "RateLimitError"},
    ("scope_read_mem0", "po-01a"): {}, ("scope_read_mem0", "po-01b"): {"action": "pandas", "wrong_tags": True},
    ("scope_read_mem0", "ss-01a"): {}, ("scope_read_mem0", "ss-01b"): {},
    ("supermemory", "po-01a"): {"error": "AuthenticationError"}, ("supermemory", "po-01b"): {"error": "AuthenticationError"},
}


@pytest.fixture
def run(tmp_path, fake_judge, monkeypatch):
    monkeypatch.setattr(score.llm, "start_run", lambda: None)
    write_logs(tmp_path / "logs", SPECS)
    args = ["--logs", str(tmp_path / "logs"), "--out", str(tmp_path / "reports"), "--cache", str(tmp_path / "cache.jsonl")]
    return tmp_path, args


def test_score_cli_writes_the_report_and_reuses_the_cache(run, fake_judge, capsys):
    tmp, args = run
    assert score.main(args + ["--dry-run"]) == 0 and not fake_judge
    assert "need" in capsys.readouterr().out
    assert score.main(args) == 0
    calls = len(fake_judge)
    assert calls > 0
    with open(tmp / "reports/episode_scores.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(SPECS)
    summary = (tmp / "reports/summary.md").read_text()
    for heading in ("Correction adherence", "Retrieval vs action", "Where failures happen", "Tagging accuracy", "Cost", "Paired comparisons"):
        assert heading in summary
    assert (tmp / "reports/examples.md").exists() and (tmp / "reports/tables/adherence.csv").exists()
    by = {(r["condition"], r["episode_id"]): r for r in rows}
    assert by[("mem0", "po-01b")]["stage"] == "scope_lost" and by[("scope_read_mem0", "po-01b")]["stage"] == "tagging"
    assert by[("scope_write_mem0", "ss-01b")]["status"] == "error"
    adherence = {r["condition"]: r for r in T.adherence([{**r, "correct": r["correct"] == "True" if r["correct"] else None,
                                                           "in_scope": r["in_scope"] == "True", "role": ""} for r in rows])}
    assert adherence["no_memory"]["pairs_both_correct"] == 0 and adherence["scope_write_mem0"]["pairs"] == 1
    assert "not scored (2 run errors)" in summary and "| adherence | scope_write_supermemory" not in summary
    assert "| supermemory |" not in summary.split("## 2.")[1].split("## 7.")[0]  # left out of the tables until it has scores
    cats = {r["condition"]: r for r in T.categories([{**r, "correct": r["correct"] == "True" if r["correct"] else None,
                                                      "in_scope": r["in_scope"] == "True"} for r in rows])}
    assert cats["no_memory"]["default"] == 2 and cats["no_memory"]["over_apply"] == 0
    assert score.main(args) == 0 and len(fake_judge) == calls  # everything cached
    assert score.main(args + ["--dry-run"]) == 0 and "cached" in capsys.readouterr().out


def test_review_labels_override_the_judge(run):
    tmp, args = run
    score.main(args)
    records, logs, eps = score.score_offline(tmp / "logs", tmp / "cache.jsonl")
    picked = review.sample(records, 6, seed=1)
    assert len(picked) == 6 and len({r["condition"] for r in picked}) > 1
    review.write_review(picked, logs, eps, tmp / "reports/review")
    path = tmp / "reports/review/judge_review.csv"
    with path.open() as f:
        rows = list(csv.DictReader(f))
    rows[0]["human_action"], rows[0]["human_retention"] = "none", "no"
    rows[1]["human_action"] = rows[1]["judge_action"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, review.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    labels = review.read_labels(path, eps)
    assert len(labels) == 2
    score.main(args)
    with open(tmp / "reports/episode_scores.csv") as f:
        out = {f"{r['condition']}/{r['episode_id']}": r for r in csv.DictReader(f)}
    first = out[rows[0]["item"]]
    assert first["action"] == "none" and first["action_source"] == "human" and first["retention"] == "False"
    assert "judge vs human review" in (tmp / "reports/summary.md").read_text()


def test_figures_render(run):
    pytest.importorskip("matplotlib")
    tmp, args = run
    score.main(args)
    for name in ("adherence_vs_retention", "adherence_by_type", "failure_stages"):
        assert (tmp / f"reports/figures/{name}.png").stat().st_size > 10_000
