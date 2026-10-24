"""Step 7 judge: an LLM reads what the agent and the memory systems produced and labels it for scoring.

    Judge.answer  which candidate action the agent's answer takes, and whether each retention check passes
    Judge.notes   which gold memories each stored, retrieved or written note records, and whether the note keeps the
                  memory's limit (the project, task or condition it is limited to)

The judge runs only at scoring time, through common/llm.py (ledger component "judge"), with config.toml [judge].
It sees gold because labelling against gold is its job, but it is never told which action is expected, the options
are listed in alphabetical order, and nothing it writes goes back into a condition.

Replies are cached in runs/judge_cache.jsonl, keyed by the prompt version, the judge model and the exact input. A
rescore never pays twice, and a log that was rerun is judged again because its answer changed.
"""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import openai

from common import llm
from common.config import CONFIG, ROOT
from scope_layer.tagger import parse_json

VERSION = "judge-v1"  # bump when a prompt or parser changes, so verdicts from the old version are not reused
CACHE_PATH = ROOT / "runs/judge_cache.jsonl"
SETTINGS = {"model": llm.CONFIG["model"], "temperature": 0, "seed": llm.CONFIG["seed"], "max_tokens": 700, **CONFIG.get("judge", {})}
RATE_LIMIT_WAITS_S = (20, 40, 80, 160)
OUTPUT_TOKENS_ESTIMATE = 250

SYSTEM = ("You label answers and notes for a research study on how AI assistants use memory. "
          "Report what the text in front of you actually does or says. Never decide what the user should have been given.")

RETRY_NOTE = "Your reply could not be read. Reply again with the JSON object only, in exactly the shape given, with no other text."

ANSWER_INSTRUCTIONS = """Question 1. The request involves one choice: {decision}. Which one of these options does the answer actually use?
{options}
Look at the main thing the user asked for (the code, draft, list, commands or reference) and judge by what it does: its code, commands, format, wording or stated choice. An option the answer only mentions, compares or rejects does not count. Where an option is a length or a count, count it yourself in the main deliverable. If the answer uses none of the options, the action is "none". If it uses more than one, or leaves the choice to the user, the action is "mixed".

Question 2. For each check below, does the answer pass it? Use true or false. Use null only if the answer contains nothing the check could apply to.
{checks}

Reply with JSON only, in this shape:
{{"action_evidence": "<short quote from the answer>", "action": "<one option exactly as written, or none, or mixed>", "checks": [{{"id": "C1", "evidence": "<short quote>", "passed": true}}]}}"""

NOTES_INSTRUCTIONS = """For each note, list the statements whose instruction or preference the note records. A note may record none of them (for example when it only records a reason, a fact or a question), or several if it merges them.
For each statement a note records, also say whether the note keeps the statement's limit: the project it is limited to, the task it is limited to, or the condition under which it applies. If the statement has no such limit, keeps_limit is true.

Reply with JSON only, in this shape, with one entry per note:
{"notes": [{"index": 1, "matches": [{"id": "m1", "keeps_limit": true}]}, {"index": 2, "matches": []}]}"""


class Cache:
    """Append-only JSONL of judge results, one line per call. The last line for a key wins."""

    def __init__(self, path=CACHE_PATH):
        self.path = Path(path)
        self._rows = None

    def _load(self):
        if self._rows is None:
            self._rows = {}
            if self.path.exists():
                for line in self.path.read_text().splitlines():
                    if line.strip():
                        row = json.loads(line)
                        self._rows[row["key"]] = row
        return self._rows

    def get(self, key):
        return self._load().get(key)

    def rows(self):
        return list(self._load().values())

    def put(self, row):
        self._load()[row["key"]] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")


def cache_key(kind, payload):
    blob = json.dumps({"kind": kind, "version": VERSION, "model": SETTINGS["model"], "payload": payload}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def answer_messages(payload):
    options = "\n".join(f'- "{o}"' for o in payload["options"])
    checks = "\n".join(f"C{i}: {c}" for i, c in enumerate(payload["checks"], 1)) or "(no checks; reply with an empty list)"
    user = (f"The user's request:\n<request>\n{payload['request']}\n</request>\n\n"
            f"The assistant's answer:\n<answer>\n{payload['answer']}\n</answer>\n\n"
            + ANSWER_INSTRUCTIONS.format(decision=payload["decision"], options=options, checks=checks))
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def notes_messages(payload):
    statements = "\n".join(f"[{mid}] {text}" for mid, text in payload["statements"])
    notes = "\n".join(f"{i}. {text}" for i, text in enumerate(payload["notes"], 1))
    user = (f"A user made these statements in earlier conversations. Each has an ID.\n{statements}\n\n"
            f"A memory system saved the notes below.\n{notes}\n\n" + NOTES_INSTRUCTIONS)
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _norm_option(value):
    return re.sub(r"\s+", " ", str(value or "").lower()).strip(" .\"'`*")


def pick_option(value, options):
    """Map the judge's action to one option, "none" or "mixed". The longest option inside the reply wins, so
    "premium economy" is not read as "economy". Raises ValueError if nothing fits."""
    v = _norm_option(value)
    by_norm = {_norm_option(o): o for o in options}
    if v in by_norm:
        return by_norm[v]
    if v in ("none", "mixed"):
        return v
    inside = [o for n, o in by_norm.items() if n and n in v]
    if inside:
        return max(inside, key=len)
    raise ValueError(f"judge action {value!r} is not one of {sorted(options)}")


def _bool(value):
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    return True if v in ("true", "yes", "pass", "passed") else False if v in ("false", "no", "fail", "failed") else None


def parse_answer(reply, options, n_checks):
    d = parse_json(reply)
    checks = {}
    for c in d.get("checks") or []:
        m = re.fullmatch(r"c?(\d+)", str(c.get("id", "")).strip().lower()) if isinstance(c, dict) else None
        if m:
            checks[int(m[1])] = (_bool(c.get("passed")), str(c.get("evidence") or "")[:300])
    picked = [checks.get(i, (None, "")) for i in range(1, n_checks + 1)]
    return {"action": pick_option(d.get("action"), options), "action_evidence": str(d.get("action_evidence") or "")[:300],
            "checks": [p for p, _ in picked], "check_evidence": [e for _, e in picked]}


def parse_notes(reply, n_notes, ids):
    """One entry per note: a list of {"id", "keeps_limit"}, or None when the judge skipped that note."""
    d = parse_json(reply)
    if not isinstance(d.get("notes"), list):
        raise ValueError(f"no notes list in judge reply: {reply[:200]!r}")
    out = [None] * n_notes
    for note in d["notes"]:
        try:
            i = int(note.get("index"))
        except (AttributeError, TypeError, ValueError):
            continue
        if 1 <= i <= n_notes:
            matches = []
            for m in note.get("matches") or []:
                mid, keeps = (m.get("id"), _bool(m.get("keeps_limit"))) if isinstance(m, dict) else (m, None)
                if mid in ids and all(x["id"] != mid for x in matches):
                    matches.append({"id": mid, "keeps_limit": keeps})
            out[i - 1] = matches
    return out


def estimate_tokens(messages):
    return sum(len(m["content"]) for m in messages) // 4 + OUTPUT_TOKENS_ESTIMATE


class Judge:
    """mode "call" asks the model for anything not cached, "offline" only reads the cache, "plan" counts what a call
    run would send (in self.planned) without sending it."""

    def __init__(self, cache=None, mode="call"):
        self.cache = cache if cache is not None else Cache()
        self.mode = mode
        self.planned, self.errors, self.calls = [], [], 0

    def answer(self, *, request, answer, decision, options, checks, episode=None, condition=None):
        payload = {"request": request, "answer": answer, "decision": decision, "options": sorted(options), "checks": list(checks)}
        return self._ask("answer", payload, answer_messages(payload),
                         lambda r: parse_answer(r, payload["options"], len(payload["checks"])), episode, condition)

    def notes(self, *, statements, notes, episode=None, condition=None):
        if not notes:
            return []
        payload = {"statements": [list(s) for s in statements], "notes": list(notes)}
        ids = {mid for mid, _ in statements}
        return self._ask("notes", payload, notes_messages(payload), lambda r: parse_notes(r, len(notes), ids), episode, condition)

    def _ask(self, kind, payload, messages, parse, episode, condition):
        key = cache_key(kind, payload)
        row = self.cache.get(key)
        if row is not None:
            return row["result"]
        if self.mode == "plan":
            self.planned.append((kind, estimate_tokens(messages)))
            return None
        if self.mode != "call":
            return None
        try:
            reply, cost = self._chat(messages, episode, condition)
            try:
                result = parse(reply)
            except ValueError:
                retry = [*messages, {"role": "assistant", "content": reply}, {"role": "user", "content": RETRY_NOTE}]
                reply, cost2 = self._chat(retry, episode, condition)
                cost = None if cost is None or cost2 is None else cost + cost2
                result = parse(reply)
        except (ValueError, openai.APIError) as e:
            self.errors.append({"kind": kind, "episode": episode, "condition": condition, "error": f"{type(e).__name__}: {e}"[:300]})
            return None
        self.cache.put({"key": key, "kind": kind, "version": VERSION, "model": SETTINGS["model"], "episode": episode,
                        "condition": condition, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "reply": reply, "result": result, "cost_usd": cost})
        return result

    def _chat(self, messages, episode, condition):
        for wait in (*RATE_LIMIT_WAITS_S, None):
            try:
                with llm.context(episode=episode, condition=condition):
                    resp = llm.chat(messages, component="judge", model=SETTINGS["model"], temperature=SETTINGS["temperature"],
                                    seed=SETTINGS["seed"], max_tokens=SETTINGS["max_tokens"])
                self.calls += 1
                return resp.choices[0].message.content or "", getattr(resp.usage, "cost", None)
            except openai.RateLimitError:
                if wait is None:
                    raise
                print(f"  judge rate limited, waiting {wait}s", flush=True)
                time.sleep(wait)
