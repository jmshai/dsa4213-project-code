import copy
import json
from pathlib import Path

import pytest

from episodes import annotate
from episodes.validate import check_pair, holds

PAIR = json.loads((Path(__file__).parent.parent / "episodes/pairs/po-01.json").read_text())


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
