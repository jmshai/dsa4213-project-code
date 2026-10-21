"""Write-time tagging: extract and label the user's instructions from a full session, before any memory system rewrites them."""
from scope_layer import tagger
from scope_layer.tags import TaggedMemory, parse_tag

TASK = """Below is one conversation between a user and an assistant. Find every instruction or preference the user states and label it.
Copy each instruction's "text" word for word from the conversation.
Reply as {"memories": [{"text": "...", "scope": "...", "key": ..., "condition": ...}, ...]}."""


def tag_session(session_text):
    """Extract and label the instructions in one session. Returns TaggedMemory objects in the order stated."""
    reply = tagger.parse_json(tagger.call(TASK, session_text))
    return [TaggedMemory(m["text"], parse_tag(m)) for m in reply.get("memories", []) if isinstance(m, dict) and m.get("text")]
