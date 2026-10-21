"""The agent: one call to the fixed model with agent/prompt.md. Identical for every condition."""
from common import llm
from common.config import ROOT

PROMPT = (ROOT / "agent/prompt.md").read_text()


def build_prompt(memories, probe):
    # str.replace, not str.format: memory text may contain braces
    return PROMPT.replace("{memories}", memories).replace("{probe}", probe)


def act(prompt):
    """Return (response text, model id). The ledger row is labelled by the caller's llm.context()."""
    resp = llm.chat([{"role": "user", "content": prompt}], component="agent")
    return resp.choices[0].message.content or "", resp.model
