from types import SimpleNamespace

import pytest

from common import ledger, llm


def resp(cost=0.25, model="m/x"):
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50,
                            completion_tokens_details=SimpleNamespace(reasoning_tokens=7))
    if cost is not None:
        usage.cost = cost
    return SimpleNamespace(usage=usage, model=model)


def test_totals_and_grouping():
    ledger.append(component="agent", condition="c1", cost_usd=0.1, prompt_tokens=10, completion_tokens=5)
    ledger.append(component="agent", condition="c2", cost_usd=0.2)
    ledger.append(component="mem0", condition="c1", cost_usd=0.3)
    assert ledger.total() == pytest.approx(0.6)
    assert ledger.totals_by("component")["agent"]["cost_usd"] == pytest.approx(0.3)
    assert ledger.totals_by("condition")["c1"]["calls"] == 2


def test_record_usage_uses_reported_cost_and_context():
    with llm.context(episode="e1", condition="mem0"):
        assert llm.record_usage(resp(0.25), component="mem0") == 0.25
    row = ledger.rows()[0]
    assert (row["episode"], row["condition"], row["reasoning_tokens"], row["cost_usd"]) == ("e1", "mem0", 7, 0.25)


def test_append_outside_llm_inherits_context():
    with llm.context(episode="e1", condition="supermemory"):
        ledger.append(component="supermemory", cost_usd=0.0)
    row = ledger.rows()[0]
    assert (row["episode"], row["condition"]) == ("e1", "supermemory")


def test_missing_cost_falls_back_to_listed_price():
    assert llm.record_usage(resp(None), component="agent") == pytest.approx(100e-6 + 50 * 2e-6)
    assert "computed" in ledger.rows()[0]["note"]


def test_missing_cost_and_price_raises_and_logs_nothing():
    with pytest.raises(RuntimeError):
        llm.record_usage(resp(None, model="unknown/model"), component="agent")
    assert ledger.rows() == []


def test_budget_guard_trips_at_cap():
    llm.check_budget()
    ledger.append(component="agent", cost_usd=1.0)
    with pytest.raises(llm.BudgetExceeded):
        llm.check_budget()


def test_chat_logs_cost_from_real_response_type(monkeypatch, fake_client):
    from openai.types.chat import ChatCompletion

    raw = {"id": "1", "object": "chat.completion", "created": 0, "model": "m/x",
           "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "hi"}}],
           "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.0042,
                     "completion_tokens_details": {"reasoning_tokens": 0}}}
    sent = {}

    def create(**kw):
        sent.update(kw)
        return ChatCompletion.model_validate(raw)

    stub = fake_client(create)
    monkeypatch.setattr(llm, "client", lambda: stub)
    llm.chat([{"role": "user", "content": "x"}], component="agent", episode="e1")
    assert ledger.rows()[0]["cost_usd"] == 0.0042
    assert sent["extra_body"]["usage"] == {"include": True} and sent["temperature"] == 0
