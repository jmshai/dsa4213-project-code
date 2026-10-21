"""Mem0 as shipped: default extraction prompts and search. Only the LLM endpoint (OpenRouter) and the embedder (local) are configured."""
import os
import re

os.environ.setdefault("MEM0_TELEMETRY", "False")  # must be set before mem0 is imported

from mem0 import Memory  # noqa: E402

from baselines.base import RetrievedMemory, to_messages
from common import llm
from common.config import CONFIG, ROOT

TOP_K = CONFIG["retrieval"]["top_k"]


class Mem0Adapter:
    def __init__(self, namespace):
        self.namespace = namespace
        cfg, m = llm.CONFIG, CONFIG["mem0"]
        qdrant = ROOT / m["qdrant_path"]
        self.memory = Memory.from_config({
            "llm": {"provider": "openai", "config": {"model": cfg["model"], "temperature": cfg["temperature"], "max_tokens": cfg["max_tokens"]}},
            "embedder": {"provider": "huggingface", "config": {"model": m["embedder_model"], "embedding_dims": m["embedding_dims"]}},
            "vector_store": {"provider": "qdrant", "config": {
                "path": f"{qdrant}/{re.sub(r'[^A-Za-z0-9_.-]', '_', namespace)}",
                "embedding_model_dims": m["embedding_dims"]}},
            "history_db_path": f"{qdrant}/history.db",
        })
        llm.instrument_client(self.memory.llm.client, component="mem0")

    def write(self, session_text, metadata=None):
        self.memory.add(to_messages(session_text), user_id=self.namespace, metadata=metadata)

    def stored(self):
        res = self.memory.get_all(filters={"user_id": self.namespace}, top_k=1000)
        return res["results"] if isinstance(res, dict) else res

    def retrieve(self, query):
        res = self.memory.search(query, top_k=TOP_K, filters={"user_id": self.namespace})
        hits = res["results"] if isinstance(res, dict) else res
        return [RetrievedMemory(text=h["memory"], score=h.get("score"), raw=h) for h in hits]

    def reset(self):
        self.memory.delete_all(user_id=self.namespace)
