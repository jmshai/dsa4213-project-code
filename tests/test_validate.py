import copy

import pytest

from episodes import annotate
from episodes.loader import PAIRS_DIR, load_pair
from episodes.validate import check_pair, holds

PAIR = load_pair(PAIRS_DIR / "po-01.json")


def broken(mutate):
    p = copy.deepcopy(PAIR)
    mutate(p)
    return check_pair(p)


def test_worked_example_is_valid():
    assert check_pair(PAIR) == []


def test_expected_memory_must_match_gold_walk():
    errs = broken(lambda p: p["probes"]["A"].update(expected_memory="m1", expected_action="polars"))
    assert any("gold walk gives m2" in e for e in errs)


def test_probes_must_have_different_actions():
    def same(p):
        p["probes"]["B"].update(expected_action="pandas")
    assert any("different expected actions" in e for e in broken(same))


def test_signals_must_be_in_text():
    assert any("not in probe text" in e for e in broken(lambda p: p["probes"]["B"].update(text="Deduplicate the orders table.")))
    assert any("not in its text" in e for e in broken(lambda p: p["sessions"][1].update(active_project="Project Q")))


def test_memory_must_be_verbatim_in_session():
    assert any("verbatim" in e for e in broken(lambda p: p["memories"][0].update(text="I prefer Polars for big data.")))


def test_wrong_deciding_rule_for_conflict_type():
    def swap(p):
        p["conflict_type"] = "same_scope_supersession"
    assert any("needs deciding rules" in e for e in broken(swap))


def test_condition_evaluation():
    facts = {"rows": {"value": 5000000, "text": "5M"}, "audience": {"value": "exec", "text": "execs"}}
    assert holds("rows > 1000000", facts) and not holds("rows < 1000000", facts)
    assert holds("audience == exec", facts) and not holds("audience == customer", facts)
    assert not holds("size_mb > 1", facts)


def test_blind_export_leaks_no_gold_and_identical_labels_agree():
    rows = annotate.blind_rows([PAIR])
    assert all(r[f] == "" for r in rows for f in annotate.FIELDS)
    gold = annotate.gold_rows([PAIR])
    rates, diffs = annotate.agreement(gold, gold)
    assert diffs == [] and all(r == 1 for r in rates.values())
    other = copy.deepcopy(gold)
    other["po-01/m2"]["scope"] = "single_task"
    assert annotate.agreement(gold, other)[1] == [("po-01/m2", "scope", "project", "single_task")]


def three_scope_pair():
    """Standing, project and single_task memories together. B is a new task in the same project, so rule 2 picks the project memory."""
    mem = lambda i, sid, text, role, scope, key, action: {
        "memory_id": i, "session_id": sid, "text": text, "role": role, "decision": None if role == "unrelated" else "export_format",
        "action": None if role == "unrelated" else action, "gold": {"scope": scope, "key": key, "condition": None}}
    probe = lambda task, text, in_scope, action, memory: {
        "task_id": task, "active_project": "Project Atlas", "text": text, "facts": {}, "in_scope": in_scope,
        "decision": "export_format", "expected_action": action, "expected_memory": memory, "deciding_rule": 2}
    return {
        "pair_id": "st-99", "conflict_type": "single_task_override", "domain": "export format",
        "sessions": [
            {"session_id": "s1", "order": 1, "task_id": "t1", "active_project": None, "text": "User: I prefer exporting tables as parquet.\nAssistant: Noted."},
            {"session_id": "s2", "order": 2, "task_id": "t2", "active_project": "Project Atlas", "text": "User: On Project Atlas, export tables as csv.\nAssistant: Noted."},
            {"session_id": "s3", "order": 3, "task_id": "t3", "active_project": "Project Atlas", "text": "User: Back on Project Atlas.\nAssistant: Welcome back.\nUser: This time, export the weekly file as json.\nAssistant: Noted."},
        ],
        "memories": [
            mem("m1", "s1", "I prefer exporting tables as parquet.", "standing", "standing", None, "parquet"),
            mem("m2", "s2", "On Project Atlas, export tables as csv.", "scoped", "project", "Project Atlas", "csv"),
            mem("m3", "s3", "This time, export the weekly file as json.", "scoped", "single_task", "t3", "json"),
            mem("m4", "s1", "Noted.", "unrelated", "standing", None, None),
        ],
        "probes": {
            "A": probe("t3", "Continue the weekly export job from earlier for Project Atlas: write a function that saves the dataframe.", True, "json", "m3"),
            "B": probe("t4", "New task, weekly export job for Project Atlas: write a function that saves the dataframe.", False, "csv", "m2"),
        },
        "retention_checks": [{"memory_id": "m4", "check": "anything"}],
    }


def test_three_scope_variant_is_valid_and_resolves_by_rules_2_and_2():
    pair = three_scope_pair()
    assert check_pair(pair) == []


def test_three_scope_variant_not_allowed_for_other_types():
    pair = three_scope_pair()
    pair["conflict_type"] = "project_override"
    assert any("needs deciding rules" in e for e in check_pair(pair))


def test_probes_must_be_mirrored():
    def asymmetric(p):
        p["probes"]["B"]["text"] = "Please write a Python function, in any style you like, that removes duplicate rows from the 5M-row orders table for Project Y using the order_id column as the key."
    assert any("differ in" in e and "words" in e for e in broken(asymmetric))
