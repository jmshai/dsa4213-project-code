"""README Step 5: the experimental conditions.

| condition                 | what fills the prompt's {memories} slot                                   | role      |
| ------------------------- | ------------------------------------------------------------------------- | --------- |
| no_memory                 | "(none)"                                                                  | floor     |
| full_transcript           | every session, in order                                                   | control   |
| mem0, supermemory         | what the system retrieves for the probe, as shipped                       | baseline  |
| scope_write_<system>      | retrieved memories with the tags stored at write time, plus the rules     | treatment |
| scope_read_<system>       | retrieved memories tagged after retrieval, plus the rules                 | treatment |

The README's six conditions are the first five rows with the scope layer on one system. Both systems are registered so
each treatment can be compared with the baseline it is built on. CONDITION_INFO records each condition's role, system
and layer for the Step 7 scorer.

Each condition is a function (episode) -> dict with the memories text for the agent prompt plus what to log:
    memories   text for the prompt's {memories} slot
    stored     what the memory system held after the sessions were written (None if there is no system)
    retrieved  [{text, score, raw}] returned for the probe
    tagged     [{text, tag}] after tagging, scope-layer conditions only, in the same order as `retrieved`
    written    [{text, tag}] the write-time tagger extracted, write-time conditions only
    namespace  the memory-system namespace this run used (None if there is no system)
    cleanup_error  why deleting that namespace failed, or None

Only session text and probe text reach a system or a tagger. Gold fields stay out of this module.
Every run writes to a fresh namespace (episode id, condition and a random suffix). A run that is killed before reset()
then leaves its memories in a namespace no later run reads, so a rerun cannot pick them up. For the same reason a
failed reset() is recorded as cleanup_error rather than raised: it can neither hide the error that stopped a run nor
throw away a run that worked.
"""
import dataclasses
import importlib
import uuid

from scope_layer import layer
from scope_layer.tags import render

SYSTEMS = {"mem0": ("baselines.mem0.adapter", "Mem0Adapter"), "supermemory": ("baselines.supermemory.adapter", "SupermemoryAdapter")}
MODES = (("plain", "{system}"), ("write", "scope_write_{system}"), ("read", "scope_read_{system}"))


def _sessions(ep):
    return sorted(ep["pair"]["sessions"], key=lambda s: s["order"])


def _plain(texts):
    return "\n".join(f"- {t}" for t in texts) or "(none)"


def _tagged_dicts(tagged):
    return [{"text": m.text, "tag": dataclasses.asdict(m.tag) if m.tag else None} for m in tagged]


def no_memory(ep):
    return {"memories": "(none)", "stored": None, "retrieved": [], "tagged": None, "written": None, "namespace": None,
            "cleanup_error": None}


def full_transcript(ep):
    convo = "\n\n".join(f"Conversation {i}:\n{s['text']}" for i, s in enumerate(_sessions(ep), 1))
    return {"memories": convo, "stored": None, "retrieved": [], "tagged": None, "written": None, "namespace": None,
            "cleanup_error": None}


def memory_system(system, mode, name):
    """mode: "plain" (baseline), "write" (write-time scope layer) or "read" (read-time scope layer)."""
    def run(ep):
        module, cls = SYSTEMS[system]
        namespace = f"{ep['episode_id']}-{name}-{uuid.uuid4().hex[:6]}"
        adapter = getattr(importlib.import_module(module), cls)(namespace)
        cleanup_error = None
        try:
            written = []
            for s in _sessions(ep):
                if mode == "write":
                    written += layer.write_session(adapter, s["text"])
                else:
                    adapter.write(s["text"])
            stored = adapter.stored()
            hits = adapter.retrieve(ep["probe"]["text"])
        finally:
            try:
                adapter.reset()
            except Exception as e:  # noqa: BLE001 - see the module docstring: cleanup must never mask the real error
                cleanup_error = f"{type(e).__name__}: {e}"[:300]
        retrieved = [{"text": h.text, "score": h.score, "raw": h.raw} for h in hits]
        if mode == "plain":
            return {"memories": _plain(h.text for h in hits), "stored": stored, "retrieved": retrieved,
                    "tagged": None, "written": None, "namespace": namespace, "cleanup_error": cleanup_error}
        tagged = layer.tag_from_stored(hits) if mode == "write" else layer.tag_after_retrieval(hits)
        return {"memories": render(tagged), "stored": stored, "retrieved": retrieved, "tagged": _tagged_dicts(tagged),
                "written": _tagged_dicts(written) if mode == "write" else None, "namespace": namespace,
                "cleanup_error": cleanup_error}
    return run


CONDITIONS = {"no_memory": no_memory, "full_transcript": full_transcript}
CONDITION_INFO = {"no_memory": {"role": "floor", "system": None, "layer": None},
                  "full_transcript": {"role": "control", "system": None, "layer": None}}
for _system in SYSTEMS:
    for _mode, _pattern in MODES:
        _name = _pattern.format(system=_system)
        CONDITIONS[_name] = memory_system(_system, _mode, _name)
        CONDITION_INFO[_name] = {"role": "baseline" if _mode == "plain" else "treatment", "system": _system,
                                 "layer": None if _mode == "plain" else _mode}
