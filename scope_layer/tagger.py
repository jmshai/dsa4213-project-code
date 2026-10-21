"""The LLM tagger shared by the write-time and read-time versions.

It uses the labelling guide as its instructions and the fixed agent model from config.toml, through common/llm.py.
Its input is session text or retrieved memory text only, never gold fields.
"""
import json

from common import llm
from common.config import ROOT

GUIDE = (ROOT / "episodes/labelling_guide.md").read_text().split("## Writing episodes")[0]  # the rest is for episode authors

OUTPUT_NOTE = """
You work only from the text you are given. You cannot know task ids, so for single_task leave "key" null.
For project, "key" is the project name exactly as written. For standing, "key" is null.
Reply with JSON only, no other text."""


def system_prompt(task):
    return GUIDE + OUTPUT_NOTE + "\n\n" + task


def call(task, user_text, *, component="tagger"):
    resp = llm.chat(
        [{"role": "system", "content": system_prompt(task)}, {"role": "user", "content": user_text}],
        component=component,
    )
    return resp.choices[0].message.content or ""


def parse_json(text):
    """Pull the first JSON object out of a reply, tolerating code fences and surrounding prose."""
    start = text.find("{")
    if start < 0:
        raise ValueError(f"no JSON object in tagger reply: {text[:200]!r}")
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]  # first complete object; ignores anything after it
    except json.JSONDecodeError as e:
        raise ValueError(f"unparseable tagger reply: {e}: {text[:300]!r}") from e
