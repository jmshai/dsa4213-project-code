"""Mem0 as shipped: default extraction prompts and search. Only the LLM endpoint (OpenRouter) and the embedder (local) are configured."""
import os
import re
import tomllib
from pathlib import Path

os.environ.setdefault("MEM0_TELEMETRY", "False")  # must be set before mem0 is imported

from mem0 import Memory  # noqa: E402

from baselines.base import RetrievedMemory, to_messages
from common import llm

_CFG = tomllib.loads((Path(__file__).parents[2] / "config.toml").read_text())
TOP_K = 10


class Mem0Adapter:
    def __init__(self, namespace):
        self.namespace = namespace
        cfg, m = _CFG["llm"], _CFG["mem0"]
        self.memory = Memory.from_config({
            "llm": {"provider": "openai", "config": {"model": cfg["model"], "temperature": cfg["temperature"], "max_tokens": cfg["max_tokens"]}},
            "embedder": {"provider": "huggingface", "config": {"model": m["embedder_model"], "embedding_dims": m["embedding_dims"]}},
            "vector_store": {"provider": "qdrant", "config": {
                "path": f"{m['qdrant_path']}/{re.sub(r'[^A-Za-z0-9_.-]', '_', namespace)}",
                "embedding_model_dims": m["embedding_dims"]}},
            "history_db_path": f"{m['qdrant_path']}/history.db",
        })
        llm.instrument_client(self.memory.llm.client, component="mem0")

    def write(self, session_text):
        self.memory.add(to_messages(session_text), user_id=self.namespace)

    def retrieve(self, query):
        res = self.memory.search(query, top_k=TOP_K, filters={"user_id": self.namespace})
        hits = res["results"] if isinstance(res, dict) else res
        return [RetrievedMemory(text=h["memory"], score=h.get("score"), raw=h) for h in hits]

    def reset(self):
        self.memory.delete_all(user_id=self.namespace)
