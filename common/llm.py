"""The single OpenRouter client. Every LLM call in the project goes through chat() or record_usage().

Each call is appended to the cost ledger. A call whose cost cannot be determined raises instead of
being logged as free, so the budget guard cannot be bypassed by a silent zero.
"""
import contextlib
import contextvars
import os
import tomllib
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from common import ledger

load_dotenv()
BASE_URL = "https://openrouter.ai/api/v1"
CONFIG = tomllib.loads((Path(__file__).parent.parent / "config.toml").read_text())["llm"]
_context = contextvars.ContextVar("llm_context", default={})
_prices = {}


class BudgetExceeded(RuntimeError):
    pass


@contextlib.contextmanager
def context(**fields):
    """Attribute every call in the block to an episode and condition, e.g. context(episode="tool-01a", condition="mem0")."""
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def budget():
    return float(os.environ.get("BUDGET_USD", 12))


def check_budget():
    spent = ledger.total()
    if spent >= budget():
        raise BudgetExceeded(f"ledger shows ${spent:.4f} spent, cap is ${budget():.2f}")


def key_usage():
    """OpenRouter's own figures for the key: {"usage": USD spent, "limit": USD cap or None}."""
    r = httpx.get(f"{BASE_URL}/key", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()["data"]


def start_run():
    """Call once at the start of a run. Covers spend by teammates sharing the key, which the local ledger cannot see."""
    check_budget()
    used = key_usage()["usage"]
    if used >= budget():
        raise BudgetExceeded(f"OpenRouter key usage is ${used:.4f}, cap is ${budget():.2f}")


def _headers():
    return {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}


def client():
    return OpenAI(base_url=BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])


def extra_body(reasoning_enabled=None):
    """Body fields OpenRouter needs: usage accounting on, reasoning switched per config."""
    enabled = CONFIG["reasoning_enabled"] if reasoning_enabled is None else reasoning_enabled
    return {"usage": {"include": True}, "reasoning": {"enabled": enabled}}


def _price(model):
    if not _prices:
        r = httpx.get(f"{BASE_URL}/models", timeout=30)
        r.raise_for_status()
        for m in r.json()["data"]:
            _prices[m["id"]] = (float(m["pricing"]["prompt"]), float(m["pricing"]["completion"]))
    return _prices.get(model)


def record_usage(resp, *, component, episode=None, condition=None, note=None):
    """Log one completed OpenRouter response to the ledger and return the cost in USD."""
    ctx = _context.get()
    usage = resp.usage
    prompt, completion = usage.prompt_tokens, usage.completion_tokens
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = (getattr(details, "reasoning_tokens", 0) or 0) if details else 0
    cost = getattr(usage, "cost", None)
    if cost is None:
        price = _price(resp.model)
        if price is None:
            raise RuntimeError(f"no usage.cost in the response and no listed price for {resp.model}")
        cost = prompt * price[0] + completion * price[1]
        note = f"{note + '; ' if note else ''}cost computed from listed prices"
    ledger.append(
        component=component, episode=episode or ctx.get("episode"), condition=condition or ctx.get("condition"),
        model=resp.model, prompt_tokens=prompt, completion_tokens=completion, reasoning_tokens=reasoning,
        cost_usd=float(cost), note=note,
    )
    return float(cost)


def chat(messages, *, component, episode=None, condition=None, model=None, **overrides):
    """One chat completion with the fixed settings from config.toml. Returns the response object."""
    check_budget()
    params = {k: CONFIG[k] for k in ("temperature", "seed", "max_tokens")}
    params.update(overrides)
    resp = client().chat.completions.create(
        model=model or CONFIG["model"], messages=messages, extra_body=extra_body(), **params
    )
    record_usage(resp, component=component, episode=episode, condition=condition)
    return resp
