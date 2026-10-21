"""Read-time tagging: label memories after the baseline has retrieved them.

The tagger sees only each memory's text. If the baseline rewrote a memory and dropped its scope cue, the tag cannot recover it.
"""
from scope_layer import tagger
from scope_layer.tags import TaggedMemory, parse_tag

TASK = """Below is a numbered list of memories saved about a user. Label each one.
Reply as {"tags": [{"index": 1, "scope": "...", "key": ..., "condition": ...}, ...]} with one entry per memory."""


def tag_retrieved(memories):
    """Label RetrievedMemory objects. Returns a TaggedMemory for each, in the same order."""
    if not memories:
        return []
    listing = "\n".join(f"{i}. {m.text}" for i, m in enumerate(memories, 1))
    reply = tagger.parse_json(tagger.call(TASK, listing))
    by_index = {t.get("index"): t for t in reply.get("tags", []) if isinstance(t, dict)}
    return [TaggedMemory(m.text, parse_tag(by_index.get(i)), m.raw) for i, m in enumerate(memories, 1)]
