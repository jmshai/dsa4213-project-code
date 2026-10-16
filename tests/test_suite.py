"""Diversity floor for the real suite, so the pairs cannot drift back to one template."""
import re
from collections import Counter

import pytest

from episodes.loader import load_pairs

PAIRS = load_pairs()
NEGATIVE = re.compile(r"\b(never|don't|do not|avoid|stop using)\b", re.I)
HEDGED = re.compile(r"\b(usually|typically|most of the time|tend to|generally|normally)\b", re.I)


def turn_index(session_text, memory_text):
    """1-based turn number in which the memory text starts."""
    offset = session_text.index(memory_text)
    return len(re.findall(r"^(?:User|Assistant):", session_text[: offset + 1], re.M))


def sessions_by_id(pair):
    return {s["session_id"]: s for s in pair["sessions"]}


def test_twenty_pairs_four_per_conflict_type():
    assert len(PAIRS) == 20
    assert set(Counter(p["conflict_type"] for p in PAIRS).values()) == {4}


def test_memories_appear_in_varied_turns():
    positions = Counter(turn_index(sessions_by_id(p)[m["session_id"]]["text"], m["text"]) for p in PAIRS for m in p["memories"])
    assert len(positions) >= 5, positions
    assert max(positions.values()) <= 0.4 * sum(positions.values()), positions


def test_session_lengths_vary():
    lengths = Counter(len(re.findall(r"^(?:User|Assistant):", s["text"], re.M)) for p in PAIRS for s in p["sessions"])
    assert len(lengths) >= 4, lengths


def test_scoped_memory_often_precedes_standing_in_override_pairs():
    override = [p for p in PAIRS if p["conflict_type"] in ("project_override", "single_task_override", "conditional_scope")]
    reversed_ = 0
    for p in override:
        order = {s["session_id"]: s["order"] for s in p["sessions"]}
        standing = [order[m["session_id"]] for m in p["memories"] if m["role"] == "standing"]
        scoped = [order[m["session_id"]] for m in p["memories"] if m["role"] == "scoped"]
        reversed_ += max(scoped) < min(standing)
    assert len(override) == 12 and reversed_ >= 5, reversed_


def test_supersession_standing_memory_not_always_first():
    ss = [p for p in PAIRS if p["conflict_type"] == "same_scope_supersession"]
    later = 0
    for p in ss:
        order = {s["session_id"]: s["order"] for s in p["sessions"]}
        standing = [order[m["session_id"]] for m in p["memories"] if m["gold"]["scope"] == "standing" and m["role"] != "unrelated"]
        later += min(standing) > 1
    assert later >= 2


def test_phrasing_varies():
    competing = [m["text"] for p in PAIRS for m in p["memories"] if m["role"] != "unrelated"]
    assert sum("prefer" in t.lower() for t in competing) <= 0.4 * len(competing)
    assert sum(bool(NEGATIVE.search(t)) for t in competing) >= 3
    assert sum(bool(HEDGED.search(t)) for t in competing) >= 3


def test_unrelated_memories_are_not_all_introduced_alike():
    lead = 0
    for p in PAIRS:
        for m in p["memories"]:
            if m["role"] != "unrelated":
                continue
            before = sessions_by_id(p)[m["session_id"]]["text"].split(m["text"])[0][-12:]
            lead += m["text"].lower().startswith("always") or bool(re.search(r"also,\s*$", before, re.I))
    assert lead <= 5, lead


def test_retention_checks_vary():
    firsts = Counter(" ".join(rc["check"].lower().split()[:3]) for p in PAIRS for rc in p["retention_checks"])
    assert max(firsts.values()) <= 6, firsts


def test_non_developer_domains():
    kinds = Counter(p.get("domain_kind") for p in PAIRS)
    assert kinds["general"] >= 6 and None not in kinds, kinds


def test_new_combinations_are_covered():
    assert any(p["conflict_type"] == "single_task_override" and p["probes"]["B"]["deciding_rule"] == 2 for p in PAIRS), "no three-scope pair"
    assert any(
        p["conflict_type"] == "same_scope_specificity" and any(m["gold"]["scope"] == "project" and m["gold"]["condition"] for m in p["memories"])
        for p in PAIRS
    ), "no project-scoped specificity pair"


def test_memory_spans_have_no_reason_clauses():
    assert [p["pair_id"] for p in PAIRS if any("because" in m["text"].lower() for m in p["memories"])] == []


STANDING_CUE = re.compile(
    r"\b(always|in general|from now on|by default|whenever|every|never|stick to|standardize|usually|default|go with|"
    r"most of the time|everywhere|anything|any code)\b", re.I)


def test_unrelated_memories_carry_an_explicit_standing_cue():
    """A bare instruction would label as single_task under the guide's default, so retention would not be justified."""
    bare = []
    for p in PAIRS:
        for m in p["memories"]:
            if m["role"] == "unrelated":
                line = next(l for l in sessions_by_id(p)[m["session_id"]]["text"].split("\n") if m["text"] in l)
                if not STANDING_CUE.search(line):
                    bare.append((p["pair_id"], m["text"]))
    assert bare == []


def test_task_boundary_cues_vary():
    forms = {" ".join(p["probes"]["A"]["text"].lower().split()[:2]) for p in PAIRS if p["conflict_type"] == "single_task_override"}
    assert len(forms) >= 3, forms


def test_corrections_are_not_all_phrased_alike():
    openings = []
    for p in PAIRS:
        if p["conflict_type"] != "same_scope_supersession":
            continue
        later = max((m for m in p["memories"] if m["gold"]["scope"] == "project"),
                    key=lambda m: next(s["order"] for s in p["sessions"] if s["session_id"] == m["session_id"]))
        openings.append(later["text"].split()[0].lower())
    assert openings.count("actually,") <= 2, openings


def test_conditional_memory_is_sometimes_the_later_one():
    later = 0
    for p in PAIRS:
        if p["conflict_type"] != "same_scope_specificity":
            continue
        order = {s["session_id"]: s["order"] for s in p["sessions"]}
        cond = next(m for m in p["memories"] if m["gold"]["condition"] and m["role"] != "unrelated")
        plain = next(m for m in p["memories"] if not m["gold"]["condition"] and m["role"] != "unrelated")
        later += order[cond["session_id"]] > order[plain["session_id"]]
    assert later >= 1
