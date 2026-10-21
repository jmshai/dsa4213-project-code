"""Minimal versions of the README Step 5 conditions, enough for the Step 6 runner. Step 5 may replace them.

Each condition is a function (episode) -> dict with the memories text for the agent prompt plus what to log:
    memories   text for the prompt's {memories} slot
    stored     what the memory system held after the sessions were written (None if there is no system)
    retrieved  [{text, score, raw}] returned for the probe
    tagged     [{text, tag}] after tagging, scope-layer conditions only
    written    [{text, tag}] the write-time tagger extracted, write-time condition only
Only session text and probe text reach a system. Gold fields stay out of this module.
"""
import dataclasses
import importlib

from scope_layer import layer
from scope_layer.tags import render

SYSTEMS = {"mem0": ("baselines.mem0.adapter", "Mem0Adapter"), "supermemory": ("baselines.supermemory.adapter", "SupermemoryAdapter")}


def _sessions(ep):
    return sorted(ep["pair"]["sessions"], key=lambda s: s["order"])


def _plain(texts):
    return "\n".join(f"- {t}" for t in texts) or "(none)"


def _tagged_dicts(tagged):
    return [{"text": m.text, "tag": dataclasses.asdict(m.tag) if m.tag else None} for m in tagged]


def no_memory(ep):
    return {"memories": "(none)", "stored": None, "retrieved": [], "tagged": None, "written": None}


def full_transcript(ep):
    convo = "\n\n".join(f"Conversation {i}:\n{s['text']}" for i, s in enumerate(_sessions(ep), 1))
    return {"memories": convo, "stored": None, "retrieved": [], "tagged": None, "written": None}


def memory_system(system, mode, name):
    """mode: "plain" (baseline), "write" (write-time scope layer) or "read" (read-time scope layer)."""
    def run(ep):
        module, cls = SYSTEMS[system]
        adapter = getattr(importlib.import_module(module), cls)(f"{ep['episode_id']}-{name}")
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
            adapter.reset()
        retrieved = [{"text": h.text, "score": h.score, "raw": h.raw} for h in hits]
        if mode == "plain":
            return {"memories": _plain(h.text for h in hits), "stored": stored, "retrieved": retrieved, "tagged": None, "written": None}
        tagged = layer.tag_from_stored(hits) if mode == "write" else layer.tag_after_retrieval(hits)
        return {"memories": render(tagged), "stored": stored, "retrieved": retrieved,
                "tagged": _tagged_dicts(tagged), "written": _tagged_dicts(written) if mode == "write" else None}
    return run


CONDITIONS = {
    "no_memory": no_memory,
    "full_transcript": full_transcript,
    **{name: memory_system(system, mode, name) for system in SYSTEMS for mode, name in (
        ("plain", system), ("write", f"scope_write_{system}"), ("read", f"scope_read_{system}"))},
}
