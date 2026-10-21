"""Supermemory as shipped, through its hosted API. Billing is Supermemory's own, so the ledger records requests and sizes at $0 (not OpenRouter spend)."""
import os
import re
import time

from supermemory import Supermemory

from baselines.base import RetrievedMemory
from common import ledger
from common.config import CONFIG

TOP_K = CONFIG["retrieval"]["top_k"]
POLL_TIMEOUT_S = 180


class SupermemoryAdapter:
    def __init__(self, namespace):
        self.namespace = re.sub(r"[^A-Za-z0-9_-]", "_", namespace)
        self.client = Supermemory(api_key=os.environ["SUPERMEMORY_API_KEY"])

    def _log(self, op, size):
        ledger.append(component="supermemory", cost_usd=0.0, note=f"{op} chars={size}; not OpenRouter spend")

    def write(self, session_text, metadata=None):
        extra = {"metadata": metadata} if metadata else {}
        ref = self.client.add(self.namespace, content=session_text, **extra)
        self._log("add", len(session_text))
        deadline = time.time() + POLL_TIMEOUT_S
        while time.time() < deadline:  # ingestion is asynchronous; retrieve() before it finishes would see nothing
            status = self.client.documents.get(self.namespace, ref.id).system.status
            if status == "done":
                return
            if status == "failed":
                raise RuntimeError(f"Supermemory failed to process document {ref.id}")
            time.sleep(2)
        raise TimeoutError(f"Supermemory document {ref.id} not done after {POLL_TIMEOUT_S}s")

    def retrieve(self, query):
        res = self.client.search(self.namespace, query=query, limit=TOP_K)
        self._log("search", len(query))
        return [RetrievedMemory(text=r.memory or r.chunk or "", score=r.similarity, raw=r.model_dump()) for r in res.results]

    def stored(self):
        res = self.client.list(self.namespace, "documents", limit=100)
        return [d.model_dump(mode="json") for d in res.documents]

    def reset(self):
        self.client.namespaces.delete(self.namespace)
