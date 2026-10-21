import json
from types import SimpleNamespace

import pytest

from baselines.base import RetrievedMemory
from common import llm
from scope_layer import read_time, tagger, write_time
from scope_layer.tags import RULES, Tag, TaggedMemory, parse_tag, render


@pytest.fixture
def reply(monkeypatch):
    """Make the tagger's LLM call return a fixed string, and record what it was sent."""
    sent = {}

    def install(content):
        def chat(messages, **kw):
            sent["messages"], sent["kw"] = messages, kw
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        monkeypatch.setattr(llm, "chat", chat)
        return sent
    return install


def test_parse_tag_clears_key_for_standing_and_rejects_bad_scope():
    assert parse_tag({"scope": "standing", "key": "X", "condition": "rows > 1000000"}) == Tag("standing", None, "rows > 1000000")
    assert parse_tag({"scope": "project", "key": "Project X"}) == Tag("project", "Project X", None)
    assert parse_tag({"scope": "global"}) is None
    assert parse_tag(None) is None


def test_parse_json_tolerates_fences():
    assert tagger.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert tagger.parse_json('{"a": 1}\n{"b": 2}') == {"a": 1}
    assert tagger.parse_json('Here: {"a": {"b": 2}} done {x}') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        tagger.parse_json("no json here")
    with pytest.raises(ValueError):
        tagger.parse_json('{"a": ')


def test_prompt_contains_guide_but_not_episode_authoring_notes():
    p = tagger.system_prompt("task")
    assert "single_task" in p and "Worked edge cases" in p
    assert "Writing episodes" not in p


def test_read_time_matches_tags_by_index_and_keeps_raw(reply):
    sent = reply(json.dumps({"tags": [
        {"index": 2, "scope": "project", "key": "Project Marlin", "condition": None},
        {"index": 1, "scope": "standing", "key": None, "condition": "rows > 1000000"}]}))
    mems = [RetrievedMemory("Uses Polars over 1M rows", raw={"id": "a"}), RetrievedMemory("Marlin uses pandas", raw={"id": "b"})]
    out = read_time.tag_retrieved(mems)
    assert [m.tag.scope for m in out] == ["standing", "project"]
    assert out[1].tag.key == "Project Marlin" and out[1].raw == {"id": "b"}
    assert "1. Uses Polars over 1M rows" in sent["messages"][1]["content"]
    assert sent["kw"]["component"] == "tagger"


def test_read_time_missing_entry_is_untagged_not_a_crash(reply):
    reply(json.dumps({"tags": [{"index": 1, "scope": "standing"}]}))
    out = read_time.tag_retrieved([RetrievedMemory("a"), RetrievedMemory("b")])
    assert out[0].tag is not None and out[1].tag is None


def test_read_time_empty_makes_no_call(reply):
    assert read_time.tag_retrieved([]) == []


def test_write_time_extracts_text_and_tags(reply):
    reply('{"memories": [{"text": "For Project Marlin, use pandas.", "scope": "project", "key": "Project Marlin", "condition": null}, {"text": "", "scope": "standing"}]}')
    out = write_time.tag_session("User: For Project Marlin, use pandas.")
    assert [(m.text, m.tag.scope) for m in out] == [("For Project Marlin, use pandas.", "project")]


def test_render_lists_rules_labels_and_orders_by_time_when_known():
    a = TaggedMemory("older", Tag("standing", None, "rows > 1000000"), {"created_at": "2026-01-01"})
    b = TaggedMemory("newer", Tag("project", "Project Marlin"), {"created_at": "2026-01-02"})
    text = render([b, a])
    assert text.startswith(RULES)
    assert text.index("older") < text.index("newer")
    assert "[scope: project, project: Project Marlin, condition: none]" in text
    assert "[scope: standing, condition: rows > 1000000]" in text


def test_render_keeps_order_without_times_and_marks_untagged():
    text = render([TaggedMemory("x", None), TaggedMemory("y", Tag("single_task"))])
    assert text.index("1. x") < text.index("2. y")
    assert "scope: unknown" in text and "only the task where it was said" in text
