"""Scope tags and the block that shows them to the agent.

The agent chooses the memory itself. The layer only labels memories and states the README resolution rules,
so every condition uses the same agent prompt and only the `{memories}` text differs.
"""
from dataclasses import dataclass, field
from typing import Any

SCOPES = ("standing", "project", "single_task")
TIME_KEYS = ("created_at", "createdAt")

RULES = """Each memory below is labelled with where it applies:
- scope "standing": applies to every task. "project": applies only to tasks of the named project. "single_task": applies only to the one task in which it was said.
- condition: the memory applies only when this condition holds for the current request.

When several memories answer the same question, choose between them in this order:
1. Ignore a memory that does not apply to the current request (a different project, a different task, or a condition that does not hold).
2. Prefer the narrowest scope: single_task over project over standing.
3. Within one scope, prefer a memory whose condition holds over an unconditional one.
4. If they still conflict, prefer the later memory (memories are listed oldest first when times are known).
Memories about different questions do not compete, so follow every one that applies."""


@dataclass
class Tag:
    scope: str
    key: str | None = None
    condition: str | None = None


@dataclass
class TaggedMemory:
    text: str
    tag: Tag | None  # None when the tagger output for this memory was unusable
    raw: dict[str, Any] = field(default_factory=dict)


def parse_tag(d):
    """Build a Tag from a tagger's JSON object, or return None if it is unusable."""
    if not isinstance(d, dict) or d.get("scope") not in SCOPES:
        return None
    key, cond = d.get("key"), d.get("condition")
    if d["scope"] == "standing":
        key = None
    return Tag(d["scope"], key or None, cond or None)


def _label(tag):
    if tag is None:
        return "scope: unknown"
    parts = [f"scope: {tag.scope}"]
    if tag.scope == "project":
        parts.append(f"project: {tag.key}")
    elif tag.scope == "single_task":
        parts.append("only the task where it was said")
    parts.append(f"condition: {tag.condition or 'none'}")
    return ", ".join(parts)


def to_metadata(tag):
    """The tag as flat string metadata for a memory system. None fields are left out, since not every system stores nulls."""
    if tag is None:
        return None
    return {k: v for k, v in (("scope", tag.scope), ("key", tag.key), ("condition", tag.condition)) if v}


def from_metadata(raw):
    """Read a tag back from a retrieved memory's raw dict, or None if it carries none."""
    return parse_tag(raw.get("metadata"))


def _time(m):
    t = next((m.raw[k] for k in TIME_KEYS if m.raw.get(k)), None)
    return t or (m.raw.get("system") or {}).get("created_at")  # Supermemory nests it


def render(tagged):
    """The text that fills the agent prompt's {memories} slot in the scope-layer conditions."""
    if all(_time(m) for m in tagged):
        tagged = sorted(tagged, key=_time)
    lines = [f"{i}. {m.text}  [{_label(m.tag)}]" for i, m in enumerate(tagged, 1)]
    return RULES + "\n\n" + "\n".join(lines)
