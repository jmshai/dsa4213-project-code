from types import SimpleNamespace

import pytest

from common import llm


@pytest.fixture(autouse=True)
def tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("BUDGET_USD", "1.00")
    monkeypatch.setattr(llm, "_prices", {"m/x": (1e-6, 2e-6)})


@pytest.fixture
def fake_client():
    """Build a stand-in for an OpenAI client whose chat.completions.create is `create`."""
    return lambda create: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
