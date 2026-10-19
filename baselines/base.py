import re
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RetrievedMemory:
    text: str
    score: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)  # whatever metadata the system returned; read-time tagging uses it


class MemoryAdapter(Protocol):
    """Thin wrapper around one memory system. `namespace` isolates one episode under one condition."""

    def write(self, session_text: str) -> None: ...
    def retrieve(self, query: str) -> list[RetrievedMemory]: ...
    def reset(self) -> None: ...


def to_messages(session_text: str) -> list[dict[str, str]]:
    """Split "User: ..." / "Assistant: ..." transcript lines into chat messages. Untagged lines continue the previous turn."""
    messages = []
    for line in session_text.splitlines():
        m = re.match(r"(User|Assistant):\s*(.*)", line)
        if m:
            messages.append({"role": m[1].lower(), "content": m[2]})
        elif line.strip() and messages:
            messages[-1]["content"] += "\n" + line
    return messages or [{"role": "user", "content": session_text}]
