# Project guide for teammates (and your Claude)

`README.md` is the study plan (Steps 0-10). This file says what already exists for Steps 1-3 and how to build on it. Roles: Steps 1-3 @thunder_chin, Steps 4 and 6 @ed3ard, Steps 5 and 7 @nicngck, Steps 8 and 10 @iveryshai. Step 9 has no owner.

## Setup

```
uv sync
cp .env.example .env     # fill in OPENROUTER_API_KEY and SUPERMEMORY_API_KEY
uv run pytest            # 66 tests, no network
uv run python -m episodes.validate   # expect: 20/20 pairs valid
```

The team shares a $15 OpenRouter budget. Set a credit limit of about $12 on your key in the OpenRouter dashboard. The `BUDGET_USD` guard in code only sees spend logged on your own machine.

## What exists

| Path | What it is |
| --- | --- |
| `config.toml` | The fixed agent model, temperature, seed and reasoning setting. Identical for every condition. Change it only before a scored run. |
| `common/llm.py` | The only way to call an LLM. `chat()` sends the call, logs it and enforces the budget. Wrap work in `with llm.context(episode=..., condition=...)` to label the cost. |
| `common/ledger.py` | Append-only `runs/ledger.jsonl`, one line per call (tokens, reasoning tokens, `cost_usd`). Field list is in the docstring. Step 6 cost logs should read this. |
| `baselines/base.py` | The adapter interface: `write(session_text)`, `retrieve(query) -> list[RetrievedMemory]`, `reset()`. `RetrievedMemory.raw` holds whatever metadata the system returned, which read-time tagging can use. |
| `baselines/mem0/`, `baselines/supermemory/` | Both systems as shipped. Construct with a `namespace` (episode id plus condition) so episodes never share memories. |
| `agent/prompt.md` | Draft agent prompt with `{memories}` and `{probe}` slots. Fix it before any scored run. |
| `scope_layer/` | Step 4. `tagger.py` labels memories as `{scope, key, condition}` with the Step 3 labelling guide as its prompt. `write_time.py` tags a full session, `read_time.py` tags retrieved memories, `layer.py` stores write-time tags as metadata and reads them back, and `tags.py` renders the labelled memories plus the resolution rules into the agent prompt's `{memories}` slot. The agent makes the final choice. There is no code resolver. |
| `agent/` | Step 6. `agent.py` builds the prompt and calls the model. `conditions.py` holds minimal versions of the Step 5 conditions (Step 5 may replace them). `runner.py` runs episodes and writes `runs/logs/<condition>/<episode_id>.json`. |
| `episodes/` | The suite: `schema.json`, `labelling_guide.md`, `validate.py`, `annotate.py`, `loader.py`, and 20 pair files in `pairs/`. |
| `scripts/` | `spend.py` (ledger vs OpenRouter's usage), `smoke_baselines.py`, `pilot_models.py`. |

## Using the episodes

```python
from episodes.loader import episodes
for ep in episodes():          # 40 episodes, A and B probe of each pair
    ep["episode_id"]           # "po-01a"
    ep["pair"]["sessions"]     # write these to the memory system, in "order"
    ep["probe"]["text"]        # retrieve and act on this
    ep["probe"]["expected_action"]
```

Systems and the agent may use only the session `text` and the probe `text`. Everything else is gold: `active_project`, `task_id`, `facts`, `decision`, `in_scope`, `expected_*`, `deciding_rule` and `gold`. Every scope signal is written into the text itself. If your code passes a gold field to a system, the results are invalid.

## By role

- **@ed3ard (Steps 4 and 6).**
  - Run episodes with `uv run python -m agent.runner --conditions no_memory mem0 scope_write_mem0 --episodes po-01a po-01b` (omit `--episodes` for all 40, `--list` shows the condition names). A log with no error is skipped on rerun, `--force` reruns it. Provider 429s are retried with backoff. Logs are in `runs/logs/` (gitignored). The `gold_ref` block in each log is for scoring only.
  - Design choice: the scope layer does not decide for the agent. It labels memories and puts the README resolution rules in the prompt, and the agent picks the memory. So there is no `resolver.py`, and the "resolution decision and rule" is read from the agent's chosen action via each memory's `action`, not logged by code.
  - Taggers output `{scope, key, condition}` per memory. The write-time tagger sees full session text. The read-time tagger sees only retrieved text. Task ids are gold-only, so taggers leave the key null for `single_task`. Score `key` for `single_task` as not applicable.
  - The write-time condition stores each extracted instruction as its own memory with the tag as metadata (`write(text, metadata=...)` on both adapters). The tagger's extracted spans are not always word-for-word the gold `text`, so matching them to gold needs fuzzy matching.
- **@nicngck (Steps 5 and 7).**
  - Each memory has an `action`, so you can map the agent's chosen action back to a `memory_id`. That separates under-applying, over-applying and picking a superseded memory.
  - Retention checks are in each pair's `retention_checks`. They are descriptions to judge by reading the answer, not code.
  - Tagging accuracy is scored per field against `gold`, once the gold labels are adjudicated.
- **@iveryshai (Steps 8 and 10).** Nothing in Steps 1-3 touches MemoryBench. The Step 8 check is the most expensive run (large haystacks through Mem0). Budget for it before starting.

## Rules that matter

- Call LLMs only through `common/llm.py`. A call with no cost data raises instead of logging $0.
- Do not edit a pair's `gold`, `expected_*` or `deciding_rule` without rerunning `episodes.validate`. Keep memory `text` as a verbatim quote of its session.
- Never commit `.env`, `runs/` or `.qdrant/` (all gitignored). `.claude/` stays untracked.
- Mem0's embedder runs locally and Qdrant is on disk, so neither spends credits. Supermemory is billed by Supermemory, so the ledger records its calls at $0.

## Not done yet

- Both smoke tests pass (`python -m scripts.smoke_baselines`), including Supermemory's status polling against the live API. Qwen is sometimes rate-limited upstream (HTTP 429), which makes runs slow. The runner retries.
- The model pilot is done and `qwen/qwen3.8-flash` is frozen in `config.toml`. DeepSeek ignored `reasoning: {"enabled": false}` on 3 of 8 episodes and returned empty text, so it was dropped. In the full-transcript control Qwen missed all four single-task B probes (`st-01b` to `st-04b`) even though each probe says it is a new task. Treat that as a finding about the agent, not a suite bug.
- Gold labels are drafts. Two annotators still need to label blind (`python -m episodes.annotate export`, then `agree --draft`) and adjudicate before tagging accuracy means anything.
- Agents drafted 19 of the 20 pairs. Codex and Antigravity reviewed them, and the pairs were revised and reviewed once more by Codex. A human should still read all 20 for naturalness. `tests/test_suite.py` enforces the structural variety (memory position, session length, phrasing, chronology, domains).
- Known gaps in the suite: thresholds are tested far from their boundaries (no equality cases), the supersession and three-scope pairs are all developer scenarios, and memories are still fairly conspicuous directives. The no-memory shortcut rate per pair is unmeasured until Step 6.
