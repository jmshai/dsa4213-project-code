from types import SimpleNamespace

import pytest

from baselines.base import to_messages
from common import ledger, llm


def test_to_messages_splits_roles_and_continuations():
    text = "User: hi\nthere\nAssistant: hello\n\nUser: bye"
    assert to_messages(text) == [
        {"role": "user", "content": "hi\nthere"}, {"role": "assistant", "content": "hello"}, {"role": "user", "content": "bye"}]


def test_to_messages_falls_back_to_single_user_message():
    assert to_messages("just text") == [{"role": "user", "content": "just text"}]


def test_instrument_client_injects_usage_and_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_PATH", str(tmp_path / "l.jsonl"))
    seen = {}

    def create(**kw):
        seen.update(kw)
        usage = SimpleNamespace(prompt_tokens=3, completion_tokens=2, cost=0.01,
                                completion_tokens_details=SimpleNamespace(reasoning_tokens=0))
        return SimpleNamespace(usage=usage, model="m/x")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    llm.instrument_client(client, component="mem0")
    client.chat.completions.create(model="m/x", messages=[])
    assert seen["extra_body"]["usage"] == {"include": True}
    assert seen["extra_body"]["reasoning"] == {"enabled": False}
    assert ledger.rows()[0]["component"] == "mem0"


def test_instrument_client_blocks_over_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_PATH", str(tmp_path / "l.jsonl"))
    monkeypatch.setenv("BUDGET_USD", "0.5")
    ledger.append(component="agent", cost_usd=0.5)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: pytest.fail("called"))))
    llm.instrument_client(client, component="mem0")
    with pytest.raises(llm.BudgetExceeded):
        client.chat.completions.create(model="m/x", messages=[])
