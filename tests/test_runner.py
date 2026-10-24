import json
import sys
import types

import pytest

from agent import agent, conditions, runner
from baselines.base import RetrievedMemory
from common import ledger, llm
from episodes.loader import episodes
from scope_layer import layer, read_time, write_time
from scope_layer.tags import Tag, TaggedMemory, from_metadata, render, to_metadata

EPS = {e["episode_id"]: e for e in episodes()}


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path / "logs")
    return tmp_path / "logs"


@pytest.fixture
def fake_agent(monkeypatch):
    seen = []

    def act(prompt):
        seen.append(prompt)
        ledger.append(component="agent", cost_usd=0.01, prompt_tokens=5, completion_tokens=2)
        return "pandas\nBecause the memory says so.", "m/x"
    monkeypatch.setattr(agent, "act", act)
    return seen


def test_tag_metadata_round_trip_drops_nulls():
    tag = Tag("project", "Project Marlin", None)
    assert to_metadata(tag) == {"scope": "project", "key": "Project Marlin"}
    assert from_metadata({"metadata": to_metadata(tag)}) == tag
    assert from_metadata({"metadata": to_metadata(Tag("standing", None, "rows > 1000000"))}) == Tag("standing", None, "rows > 1000000")
    assert from_metadata({}) is None and to_metadata(None) is None


def test_render_orders_by_supermemory_nested_time():
    mk = lambda text, t: TaggedMemory(text, Tag("standing"), {"system": {"created_at": t}})
    text = render([mk("second", "2026-02-01"), mk("first", "2026-01-01")])
    assert text.index("1. first") < text.index("2. second")


def test_write_time_layer_stores_each_instruction_with_its_tag(monkeypatch):
    monkeypatch.setattr(write_time, "tag_session", lambda text: [
        TaggedMemory("For Project Marlin, use pandas.", Tag("project", "Project Marlin")), TaggedMemory("Use type hints.", None)])
    writes = []

    class Fake:
        def write(self, text, metadata=None):
            writes.append((text, metadata))
    layer.write_session(Fake(), "session")
    assert writes == [("User: For Project Marlin, use pandas.", {"scope": "project", "key": "Project Marlin"}), ("User: Use type hints.", None)]


def test_write_time_layer_reads_tags_back_from_hits():
    hits = [RetrievedMemory("rewritten", raw={"metadata": {"scope": "project", "key": "Project Marlin"}}), RetrievedMemory("plain")]
    out = layer.tag_from_stored(hits)
    assert out[0].tag == Tag("project", "Project Marlin") and out[1].tag is None


def test_prompt_slots_survive_braces_in_memories():
    p = agent.build_prompt("- use {x} here", "probe {y}")
    assert "use {x} here" in p and "probe {y}" in p and "{memories}" not in p and "{probe}" not in p


@pytest.mark.parametrize("name", ["no_memory", "full_transcript"])
def test_control_conditions_never_leak_gold(name, logs, fake_agent):
    ep = EPS["po-01a"]
    log = runner.run_episode(ep, name)
    prompt = fake_agent[0]
    gold_strings = [ep["probe"]["task_id"], ep["probe"]["expected_memory"], "deciding_rule", "expected_action", "in_scope"]
    assert not any(g in prompt for g in gold_strings)
    assert ep["probe"]["text"] in prompt
    assert log["error"] is None and log["usage"]["by_component"]["agent"]["calls"] == 1
    assert log["gold_ref"]["expected_action"] == "pandas" and log["gold_ref"]["action_first_mentioned"] == "pandas"


@pytest.mark.parametrize("line,want", [
    ("Use Polars for this task, over pandas.", "polars"),
    ("**Tool choice: pandas (per Project Marlin), despite Polars normally winning.**", "pandas"),
    ("Approach: sort then drop duplicates.", None),
    ("I will use pandasql for this.", None),
])
def test_action_hint_takes_the_first_mentioned_whole_word(line, want):
    ep = EPS["po-01a"]
    assert runner._action_hint(ep["pair"], ep["probe"], line + "\nmore") == want


def test_full_transcript_has_sessions_in_order():
    block = conditions.full_transcript(EPS["po-01a"])["memories"]
    assert block.index("Project Marlin, use pandas") < block.index("over 1M rows")


def test_errors_are_logged_not_raised_and_not_counted_as_done(logs, monkeypatch):
    monkeypatch.setitem(conditions.CONDITIONS, "boom", lambda ep: 1 / 0)
    log = runner.run_episode(EPS["po-01a"], "boom")
    assert log["error"]["type"] == "ZeroDivisionError" and "agent" not in log
    path = runner.log_path("boom", "po-01a")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(log))
    assert not runner._done(path)


def _rate_limit_error():
    import httpx
    import openai
    req = httpx.Request("POST", "http://x")
    return openai.RateLimitError("429", response=httpx.Response(429, request=req), body=None)


def test_rate_limit_is_retried_then_succeeds(logs, fake_agent, monkeypatch):
    waits = []
    monkeypatch.setattr(runner.time, "sleep", waits.append)
    calls = {"n": 0}

    def flaky(ep):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error()
        return {"memories": "(none)", "stored": None, "retrieved": [], "tagged": None, "written": None}
    monkeypatch.setitem(conditions.CONDITIONS, "flaky", flaky)
    log = runner.run_episode(EPS["po-01a"], "flaky")
    assert log["error"] is None and log["attempts"] == 3 and waits == [20, 40] and "agent" in log


def test_rate_limit_gives_up_after_last_attempt(logs, monkeypatch):
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    monkeypatch.setitem(conditions.CONDITIONS, "limited", lambda ep: (_ for _ in ()).throw(_rate_limit_error()))
    log = runner.run_episode(EPS["po-01a"], "limited")
    assert log["error"]["type"] == "RateLimitError" and log["attempts"] == len(runner.RATE_LIMIT_WAITS_S) + 1


def test_other_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr(runner.time, "sleep", lambda s: pytest.fail("slept"))
    monkeypatch.setitem(conditions.CONDITIONS, "boom2", lambda ep: 1 / 0)
    assert runner.run_episode(EPS["po-01a"], "boom2")["attempts"] == 1


def test_budget_exceeded_stops_the_run(monkeypatch):
    def over(ep):
        raise llm.BudgetExceeded("cap")
    monkeypatch.setitem(conditions.CONDITIONS, "over", over)
    with pytest.raises(llm.BudgetExceeded):
        runner.run_episode(EPS["po-01a"], "over")


def test_main_writes_logs_and_resumes(logs, fake_agent, monkeypatch, capsys):
    monkeypatch.setattr(llm, "start_run", lambda: None)
    assert runner.main(["--conditions", "no_memory", "--episodes", "po-01a", "po-01b"]) == 0
    data = json.loads(runner.log_path("no_memory", "po-01b").read_text())
    assert data["condition"] == "no_memory" and data["agent"]["first_line"] == "pandas" and data["usage"]["total_cost_usd"] == 0.01
    assert len(fake_agent) == 2
    runner.main(["--conditions", "no_memory", "--episodes", "po-01a", "po-01b"])
    assert len(fake_agent) == 2 and "skip" in capsys.readouterr().out
    runner.main(["--conditions", "no_memory", "--episodes", "po-01a", "--force"])
    assert len(fake_agent) == 3


def test_conditions_all_runs_every_registered_condition(logs, fake_agent, monkeypatch):
    monkeypatch.setattr(llm, "start_run", lambda: None)
    monkeypatch.setattr(runner, "CONDITIONS", {"x": conditions.no_memory, "y": conditions.full_transcript})
    assert runner.main(["--conditions", "all", "--episodes", "po-01a"]) == 0
    assert runner.log_path("x", "po-01a").exists() and runner.log_path("y", "po-01a").exists() and len(fake_agent) == 2


def test_every_condition_is_registered():
    assert set(conditions.CONDITIONS) == {"no_memory", "full_transcript", "mem0", "supermemory",
                                          "scope_write_mem0", "scope_read_mem0", "scope_write_supermemory", "scope_read_supermemory"}


def test_read_time_condition_with_fake_adapter(monkeypatch):
    made = []

    class FakeAdapter:
        def __init__(self, ns):
            self.ns, self.writes, self.reset_called = ns, [], False
            made.append(self)

        def write(self, text, metadata=None):
            self.writes.append((text, metadata))

        def stored(self):
            return [{"memory": "x"}]

        def retrieve(self, q):
            return [RetrievedMemory("Marlin uses pandas", 0.9, {"created_at": "2026-01-01"})]

        def reset(self):
            self.reset_called = True

    module = types.ModuleType("fake_adapter_module")
    module.FakeAdapter = FakeAdapter
    monkeypatch.setitem(sys.modules, "fake_adapter_module", module)
    monkeypatch.setitem(conditions.SYSTEMS, "fake", ("fake_adapter_module", "FakeAdapter"))
    monkeypatch.setattr(read_time, "tag_retrieved", lambda hits: [TaggedMemory(h.text, Tag("project", "Project Marlin"), h.raw) for h in hits])
    out = conditions.memory_system("fake", "read", "scope_read_fake")(EPS["po-01a"])
    assert "project: Project Marlin" in out["memories"] and out["tagged"][0]["tag"]["scope"] == "project"
    a = made[0]
    assert a.ns.startswith("po-01a-scope_read_fake-") and out["namespace"] == a.ns
    assert len(a.writes) == 2 and all(m is None for _, m in a.writes) and a.reset_called
