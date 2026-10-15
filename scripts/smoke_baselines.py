"""README Step 2.1-2.2: confirm each baseline can store and retrieve a test memory. Needs real API keys."""
import sys
import uuid

from baselines.mem0.adapter import Mem0Adapter
from baselines.supermemory.adapter import SupermemoryAdapter
from common import ledger, llm

SESSION = "User: For large tables I always use Polars instead of pandas.\nAssistant: Noted, I'll default to Polars for large tables."
QUERY = "Which dataframe library should I use to deduplicate a big table?"
ADAPTERS = {"mem0": Mem0Adapter, "supermemory": SupermemoryAdapter}


def main(names):
    llm.start_run()
    for name in names:
        before = ledger.total()
        a = ADAPTERS[name](f"smoke-{name}-{uuid.uuid4().hex[:6]}")
        try:
            a.write(SESSION)
            hits = a.retrieve(QUERY)
            print(f"[{name}] {len(hits)} hits, ledger +${ledger.total() - before:.5f}")
            for h in hits:
                print(f"   score={h.score}  {h.text[:100]!r}")
        finally:
            a.reset()


if __name__ == "__main__":
    main(sys.argv[1:] or list(ADAPTERS))
