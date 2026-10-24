"""Step 5: the conditions are fair. Only session text and probe text cross into a memory system, a tagger or the agent."""
import copy
import sys
import types

import pytest

from agent import agent, conditions, runner
from baselines.base import RetrievedMemory
from episodes.loader import episodes
from scope_layer import read_time, write_time
from scope_layer.tags import Tag, TaggedMemory

EPS = {e["episode_id"]: e for e in episodes()}
LEAK = "GOLDLEAK"


def poisoned(ep):
    """A copy of the episode with every gold-only field replaced by a sentinel. Session and probe text are untouched."""
    ep = copy.deepcopy(ep)
    pair = ep["pair"]
    pair["conflict_type"] = pair["domain"] = f"{LEAK}-pair"
    for s in pair["sessions"]:
        s["task_id"], s["active_project"] = f"{LEAK}-task", f"{LEAK}-project"
    for m in pair["memories"]:  # memory text too: a condition must read the sessions, never the gold memory list
        m.update({k: f"{LEAK}-{k}" for k in ("text", "role", "decision", "action")})
        m["gold"] = {"scope": f"{LEAK}-scope", "key": f"{LEAK}-key", "condition": f"{LEAK}-condition"}
    for rc in pair["retention_checks"]:
        rc["check"] = f"{LEAK}-check"
    for probe in pair["probes"].values():  # ep["probe"] is one of these
        probe.update({k: f"{LEAK}-{k}" for k in ("task_id", "active_project", "decision", "expected_action", "expected_memory")})
        probe["facts"] = {"leak_var": {"value": f"{LEAK}-value", "text": f"{LEAK}-fact"}}
    ep["label"] = f"{LEAK}-label"
    return ep


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    """Swap every system, tagger and the agent for recorders. Returns the list of everything that crossed a boundary."""
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path / "logs")
    seen = []

    class Recorder:
        def __init__(self, namespace):
            self.namespace, self.notes = namespace, []
            seen.append(("namespace", namespace))

        def write(self, text, metadata=None):
            seen.append(("write", text))
            seen.append(("metadata", repr(metadata)))
            self.notes.append((text, metadata))

        def stored(self):
            return [{"memory": t} for t, _ in self.notes]

        def retrieve(self, query):
            seen.append(("query", query))
            return [RetrievedMemory(t, 0.5, {"metadata": md or {}, "created_at": f"2026-01-0{i}"}) for i, (t, md) in enumerate(self.notes, 1)]

        def reset(self):
            seen.append(("reset", self.namespace))

    module = types.ModuleType("recording_adapter")
    module.Recorder = Recorder
    monkeypatch.setitem(sys.modules, "recording_adapter", module)
    for system in conditions.SYSTEMS:
        monkeypatch.setitem(conditions.SYSTEMS, system, ("recording_adapter", "Recorder"))

    def tag_session(text):
        seen.append(("write_tagger", text))
        return [TaggedMemory(text.splitlines()[0][6:60], Tag("project", "Project X", "rows > 1000000"))]

    def tag_retrieved(hits):
        seen.append(("read_tagger", "\n".join(h.text for h in hits)))
        return [TaggedMemory(h.text, Tag("standing"), h.raw) for h in hits]

    def act(prompt):
        seen.append(("agent", prompt))
        return "pandas\nok", "m/x"

    monkeypatch.setattr(write_time, "tag_session", tag_session)
    monkeypatch.setattr(read_time, "tag_retrieved", tag_retrieved)
    monkeypatch.setattr(agent, "act", act)
    return seen


@pytest.mark.parametrize("name", list(conditions.CONDITIONS))
def test_no_gold_field_crosses_any_boundary(name, boundary):
    ep = poisoned(EPS["po-01a"])
    log = runner.run_episode(ep, name)
    assert log["error"] is None, log["error"]
    leaked = [(kind, text) for kind, text in boundary if LEAK in text]
    assert not leaked, leaked
    prompt = next(text for kind, text in boundary if kind == "agent")
    assert ep["probe"]["text"] in prompt


@pytest.mark.parametrize("name", [n for n, info in conditions.CONDITION_INFO.items() if info["system"]])
def test_systems_get_only_session_text_and_the_probe(name, boundary):
    ep = EPS["po-01a"]
    runner.run_episode(ep, name)
    sessions = [s["text"] for s in sorted(ep["pair"]["sessions"], key=lambda s: s["order"])]
    writes = [text for kind, text in boundary if kind == "write"]
    if conditions.CONDITION_INFO[name]["layer"] == "write":
        assert [text for kind, text in boundary if kind == "write_tagger"] == sessions
        assert all(w.startswith("User: ") and w[6:] in s for w, s in zip(writes, sessions))
    else:
        assert writes == sessions
    assert [text for kind, text in boundary if kind == "query"] == [ep["probe"]["text"]]
    assert sum(kind == "reset" for kind, _ in boundary) == 1


def test_each_run_uses_a_fresh_namespace(boundary):
    runner.run_episode(EPS["po-01a"], "mem0")
    runner.run_episode(EPS["po-01a"], "mem0")
    first, second = [text for kind, text in boundary if kind == "namespace"]
    assert first != second and first.startswith("po-01a-mem0-") and second.startswith("po-01a-mem0-")


def test_condition_info_covers_the_readme_design():
    info = conditions.CONDITION_INFO
    assert set(info) == set(conditions.CONDITIONS)
    assert info["no_memory"]["role"] == "floor" and info["full_transcript"]["role"] == "control"
    for system in conditions.SYSTEMS:
        assert info[system] == {"role": "baseline", "system": system, "layer": None}
        assert info[f"scope_write_{system}"] == {"role": "treatment", "system": system, "layer": "write"}
        assert info[f"scope_read_{system}"] == {"role": "treatment", "system": system, "layer": "read"}


def test_controls_have_no_system_fields():
    for name in ("no_memory", "full_transcript"):
        out = conditions.CONDITIONS[name](EPS["po-01a"])
        assert out["stored"] is None and out["retrieved"] == [] and out["namespace"] is None


class _Flaky:
    """An adapter whose reset always fails, and whose write fails when told to."""
    fail_write = False

    def __init__(self, namespace):
        self.notes = []

    def write(self, text, metadata=None):
        if _Flaky.fail_write:
            raise ValueError("write refused")
        self.notes.append(text)

    def stored(self):
        return [{"memory": t} for t in self.notes]

    def retrieve(self, query):
        return [RetrievedMemory(t, 0.5, {}) for t in self.notes]

    def reset(self):
        raise RuntimeError("401 Unauthorized")


@pytest.fixture
def flaky(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path / "logs")
    module = types.ModuleType("flaky_adapter")
    module.Flaky = _Flaky
    monkeypatch.setitem(sys.modules, "flaky_adapter", module)
    monkeypatch.setitem(conditions.SYSTEMS, "mem0", ("flaky_adapter", "Flaky"))
    monkeypatch.setattr(agent, "act", lambda prompt: ("pandas\nok", "m/x"))
    monkeypatch.setattr(_Flaky, "fail_write", False)
    return _Flaky


def test_a_failed_cleanup_never_hides_the_real_error(flaky):
    flaky.fail_write = True
    log = runner.run_episode(EPS["po-01a"], "mem0")
    assert log["error"]["type"] == "ValueError" and "write refused" in log["error"]["message"]


def test_a_failed_cleanup_does_not_throw_away_a_run_that_worked(flaky):
    log = runner.run_episode(EPS["po-01a"], "mem0")
    assert log["error"] is None and log["agent"]["response"].startswith("pandas")
    assert log["cleanup_error"].startswith("RuntimeError: 401")
