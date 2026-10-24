"""Deterministic matching of memory-system notes to gold memories, used before asking the judge.

A note that quotes a gold memory word for word (a Supermemory document or chunk, a write-time span) is matched here
for free. Only rewritten notes (Mem0's extractions, for example) go to the LLM judge.
"""
import difflib
import re

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def norm(text):
    """Lowercase, unify quotes and whitespace, drop a leading "User:" and the outer punctuation."""
    t = re.sub(r"\s+", " ", (text or "").translate(_QUOTES).lower()).strip()
    t = re.sub(r"^(user|assistant): ", "", t)
    return t.strip(" .,;:!")


def verbatim_matches(text, memories):
    """Gold memories a note quotes word for word, as [{"id", "keeps_limit"}]. Empty when no match is certain.

    Whole memory inside the note: matched, and the note keeps the memory's limit because it keeps all of its words.
    Most of exactly one memory (a span that dropped a word or two): matched, limit unknown.
    """
    t = norm(text)
    if not t:
        return []
    gold = [(m["memory_id"], norm(m["text"])) for m in memories]
    whole = [mid for mid, g in gold if g and g in t]
    if whole:
        return [{"id": mid, "keeps_limit": True} for mid in whole]
    part = [mid for mid, g in gold if t in g and len(t) >= 0.6 * len(g)]
    if len(part) == 1:
        return [{"id": part[0], "keeps_limit": None}]
    close = sorted(((difflib.SequenceMatcher(None, t, g).ratio(), mid) for mid, g in gold), reverse=True)
    if close and close[0][0] >= 0.9 and (len(close) == 1 or close[1][0] < 0.75):
        return [{"id": close[0][1], "keeps_limit": None}]
    return []


def note_text(item):
    """The text of a stored or retrieved item, whatever shape the system returned it in."""
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    for k in ("text", "memory", "content", "chunk", "summary", "title"):
        if isinstance(item.get(k), str) and item[k].strip():
            return item[k]
    return ""
