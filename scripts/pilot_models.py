"""Pick the agent model: run a few probes under the full-transcript condition on candidate models and print the answers.

    uv run python -m scripts.pilot_models [pair_id ...]

Read the answers yourself (scoring is Step 7). Confirm that reasoning_tokens is 0, because hidden reasoning is billed as output.
Costs about $0.01 per model for two pairs. Needs OPENROUTER_API_KEY.
"""
import sys
from pathlib import Path

from common import llm
from episodes.loader import episodes

CANDIDATES = ["deepseek/deepseek-v4.1-flash", "qwen/qwen3.8-flash", "google/gemini-2.5-flash-lite"]
TEMPLATE = (Path(__file__).parent.parent / "agent/prompt.md").read_text()


def main(pair_ids):
    llm.start_run()
    for ep in episodes():
        if ep["pair"]["pair_id"] not in (pair_ids or ["po-01", "sp-01"]):
            continue
        transcript = "\n\n".join(s["text"] for s in sorted(ep["pair"]["sessions"], key=lambda s: s["order"]))
        prompt = TEMPLATE.format(memories=transcript, probe=ep["probe"]["text"])
        print(f"\n=== {ep['episode_id']}  expected: {ep['probe']['expected_action']}")
        for model in CANDIDATES:
            r = llm.chat([{"role": "user", "content": prompt}], component="pilot", episode=ep["episode_id"], condition="full_transcript", model=model)
            u = r.usage
            print(f"--- {model}  out={u.completion_tokens} reasoning={llm.reasoning_tokens(u)}\n{(r.choices[0].message.content or '')[:300]}")


if __name__ == "__main__":
    main(sys.argv[1:])
