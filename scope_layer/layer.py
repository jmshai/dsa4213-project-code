"""The two scope-layer conditions on top of one memory adapter.

Write-time: the tagger reads the full session, then each instruction is stored with its tag as metadata, so the tag
follows the memory through the system's own rewriting. Read-time: sessions are stored as shipped and the tagger labels
whatever comes back. Either way the agent gets the same rendered block (scope_layer.tags.render).
"""
from scope_layer import read_time, write_time
from scope_layer.tags import TaggedMemory, from_metadata, to_metadata


def write_session(adapter, session_text):
    """Write-time: tag the session's instructions, store each one with its tag. Returns the TaggedMemory list for the log."""
    tagged = write_time.tag_session(session_text)
    for m in tagged:
        adapter.write(f"User: {m.text}", metadata=to_metadata(m.tag))
    return tagged


def tag_from_stored(hits):
    """Write-time: read each retrieved memory's tag back from the metadata stored with it."""
    return [TaggedMemory(h.text, from_metadata(h.raw), h.raw) for h in hits]


def tag_after_retrieval(hits):
    """Read-time: label retrieved memories from their text alone."""
    return read_time.tag_retrieved(hits)
