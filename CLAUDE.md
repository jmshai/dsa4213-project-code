# Project guide for teammates (and your Claude)

`README.md` is the study plan (Steps 0-10). This file says what already exists for Steps 1-3 and how to build on it. Roles: Steps 1-3 @thunder_chin, Steps 4 and 6 @ed3ard, Steps 5 and 7 @nicngck, Steps 8 and 10 @iveryshai. Step 9 has no owner.

## Setup

```
uv sync
cp .env.example .env     # fill in OPENROUTER_API_KEY and SUPERMEMORY_API_KEY
uv run pytest            # 101 tests, no network
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
| `agent/` | Steps 5 and 6. `conditions.py` holds the eight Step 5 conditions and `CONDITION_INFO` (role, system, layer); each run uses a fresh namespace. `agent.py` builds the prompt and calls the model. `runner.py` runs episodes (`--conditions all` for every condition) and writes `runs/logs/<condition>/<episode_id>.json`. |
| `scoring/` | Step 7. `uv run python -m scoring.score` turns the logs into `reports/`. `judge.py` is the LLM judge (which action an answer takes, retention checks, which gold memory a stored or retrieved note records), cached in `runs/judge_cache.jsonl`. `records.py` scores one log (category, failure stage, tag checks), `tables.py` aggregates, `report.py` writes, `review.py` exports a sample for a person to check the judge. |
| `reports/` | Step 7 output, committed: `summary.md`, `examples.md`, `episode_scores.csv`, `tables/`, `figures/`, `review/`. |
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
  - Conditions: `uv run python -m agent.runner --conditions all` runs all eight on all 40 episodes (320 logs). `tests/test_conditions.py` checks that no gold field reaches a system, a tagger or the agent in any condition.
  - Scoring: `uv run python -m scoring.score --dry-run`, then `uv run python -m scoring.score`. The judge never sees the expected action; the action it picks maps back to a `memory_id`, which separates under-applying, over-applying and picking a superseded memory. Retention checks are judged the same way.
  - Check the judge with `uv run python -m scoring.review`: label the exported CSV, rerun `scoring.score`, and the human labels override the judge and show up as agreement in `summary.md`.
  - Tagging accuracy is scored per field against `gold`. Until the labels are adjudicated it uses the drafts; rerun `scoring.score --gold-status adjudicated` afterwards (no agent calls).
- **@iveryshai (Steps 8 and 10).** Nothing in Steps 1-3 touches MemoryBench. The Step 8 check is the most expensive run (large haystacks through Mem0). Budget for it before starting.

## Rules that matter

- Call LLMs only through `common/llm.py`. A call with no cost data raises instead of logging $0.
- Do not edit a pair's `gold`, `expected_*` or `deciding_rule` without rerunning `episodes.validate`. Keep memory `text` as a verbatim quote of its session.
- Never commit `.env`, `runs/` or `.qdrant/` (all gitignored). `.claude/` stays untracked.
- Mem0's embedder runs locally and Qdrant is on disk, so neither spends credits. Supermemory is billed by Supermemory, so the ledger records its calls at $0.

## Not done yet

- Both smoke tests pass (`python -m scripts.smoke_baselines`), including Supermemory's status polling against the live API. Qwen is sometimes rate-limited upstream (HTTP 429), which makes runs slow. The runner retries.
- The model pilot is done and `qwen/qwen3.8-flash` is frozen in `config.toml`. DeepSeek ignored `reasoning: {"enabled": false}` on 3 of 8 episodes and returned empty text, so it was dropped. In the full-transcript control Qwen missed all four single-task B probes (`st-01b` to `st-04b`) even though each probe says it is a new task. Treat that as a finding about the agent, not a suite bug.
- Steps 5 and 7 code is in place and tested offline with synthetic logs. The scored run of all eight conditions, the judge's human check (`scoring.review`) and the committed `reports/` are still to come.
- Gold labels are drafts. Two annotators still need to label blind (`python -m episodes.annotate export`, then `agree --draft`) and adjudicate before tagging accuracy means anything.
- Agents drafted 19 of the 20 pairs. Codex and Antigravity reviewed them, and the pairs were revised and reviewed once more by Codex. A human should still read all 20 for naturalness. `tests/test_suite.py` enforces the structural variety (memory position, session length, phrasing, chronology, domains).
- Known gaps in the suite: thresholds are tested far from their boundaries (no equality cases), the supersession and three-scope pairs are all developer scenarios, and memories are still fairly conspicuous directives. The no-memory shortcut rate per pair is unmeasured until Step 6.
