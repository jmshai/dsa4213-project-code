# DSA4213 Project -- Agent Memory: What is used and What isn't?

A study of whether agents act on the correct memory when a scoped instruction and a standing preference both apply to the same situation.

## Overview

Memory systems are typically evaluated on retrieval (whether the correct memory was returned). This project evaluates the next stage: whether the agent converts retrieved memory into the correct action.

**Hypothesis:** Explicit scope representation and scope-aware conflict resolution improve adherence to scoped instructions while preserving standing preferences outside their scope. Some failures are expected to occur even when the correct memory is retrieved.

**Example.** Standing preference: "For datasets over 1M rows, I prefer Polars." Scoped instruction: "For Project X, use pandas because my teammate only knows pandas."


| Probe                                    | Correct action                             |
| ---------------------------------------- | ------------------------------------------ |
| Deduplicate a 5M-row table for Project X | pandas (scoped instruction applies)        |
| Deduplicate a 5M-row table for Project Y | Polars (scoped instruction does not apply) |


Each such pair is a mirrored pair. A system that fails the first probe under-applies the scoped memory. A system that fails the second over-applies it.

## Contents

1. [Prerequisites](#step-0-prerequisites)
2. [Set up the environment](#step-1-set-up-the-environment)
3. [Install the baseline memory systems](#step-2-install-the-baseline-memory-systems)
4. [Scope model and labelling rules](#scope-model-and-labelling-rules)
5. [Build the episode suite](#step-3-build-the-episode-suite)
6. [Implement the scope-tagged memory layer](#step-4-implement-the-scope-tagged-memory-layer)
7. [Configure the experimental conditions](#step-5-configure-the-experimental-conditions-build-the-evals)
8. [Run the episodes and log outputs](#step-6-run-the-episodes-and-log-outputs-build-logs)
9. [Score the results](#step-7-score-the-results)
10. [Run the vendor claim check](#step-8-run-the-vendor-claim-check)
11. [Optional: Jev resolver comparison](#step-9-optional-jev-resolver-comparison)
12. [Report the results](#step-10-report-the-results)
13. [Limitations](#limitations)
14. [References](#references)

## Proposed Repository Structure

```
.
├── README.md
├── episodes/              # 40-episode suite (20 mirrored pairs)
│   ├── labelling_guide.md # scope labelling rules shared by annotators and taggers
│   ├── schema.json
│   ├── validate.py        # schema and gold-label consistency checks
│   ├── annotate.py        # blind labelling export and agreement
│   ├── loader.py
│   └── pairs/
├── config.toml            # fixed model and sampling settings
├── common/                # OpenRouter client and cost ledger
├── scripts/               # spend report, smoke tests
├── baselines/
│   ├── supermemory/       # Supermemory adapter
│   └── mem0/              # Mem0 adapter
├── scope_layer/
│   ├── tagger.py          # LLM tagger shared by both versions
│   ├── write_time.py      # tags memories during extraction
│   ├── read_time.py       # tags memories after retrieval
│   ├── layer.py           # stores and reads back write-time tags
│   └── tags.py            # tag type, resolution rules and the prompt block
├── agent/                 # agent that converts memory into an action
│   ├── conditions.py      # the conditions of Step 5
│   └── runner.py          # runs episodes and writes the logs
├── runs/                  # raw logs per episode per condition, judge cache, cost ledger (committed, so scoring.score can rescore without API calls)
├── scoring/
│   ├── judge.py           # LLM judge: which action an answer takes, retention checks, note-to-memory matching
│   ├── records.py         # one scored record per log: category, failure stage, tag checks
│   ├── tables.py          # the Step 7 metrics, intervals and paired tests
│   ├── report.py          # writes reports/
│   ├── review.py          # human check of the judge
│   └── score.py           # entry point: uv run python -m scoring.score
├── longmemeval_check/     # MemoryBench subset run
└── reports/               # Step 7 output: summary.md, examples.md, tables/, figures/
```

## Step 0: Prerequisites

- Python environment and package manager of choice
- API access for the LLM used as the agent
- Access to the Supermemory and Mem0 open repositories
- A copy of LongMemEval and access to MemoryBench
- Jev access (optional; the Jev comparison is conditional on access)

## Step 1: Set up the environment

1. Clone this repository.
2. Run `uv sync` to create the environment and install dependencies.
3. Run `cp .env.example .env` and fill in `OPENROUTER_API_KEY` and `SUPERMEMORY_API_KEY`. Do not commit keys.
4. The agent model, temperature, seed and reasoning setting are fixed in `config.toml` and are identical across all conditions, so differences are attributable to the memory condition. The prompt template is `agent/prompt.md`.
5. All LLM calls go through OpenRouter via `common/llm.py`, which appends every call's tokens and cost to `runs/ledger.jsonl`. Run `uv run python -m scripts.spend` to see spend by component and condition next to OpenRouter's own figure for the key.
6. The team shares a $15 budget. `BUDGET_USD` (default 12) is a code-level cap, checked against the local ledger before each call and against the key's total usage at the start of a run. The ledger is per machine, so also set a credit limit of about $12 on the key in the OpenRouter dashboard.

## Step 2: Install the baseline memory systems

1. Mem0 (`mem0ai`) and Supermemory (`supermemory`, hosted API) are installed by `uv sync`.
2. Run `uv run python -m scripts.smoke_baselines [mem0|supermemory]` to confirm each system can store and retrieve a test memory. It prints the hits and the cost the run added to the ledger. A passing Mem0 run (2026-10-20) looked like this:

   ```
   [mem0] 1 hits, ledger +$0.00125
      score=0.5191357230308997  'User prefers using Polars instead of pandas for handling large tables'
   ```

   The script writes a two-line session ("For large tables I always use Polars instead of pandas.") and retrieves with a query that shares no words with it ("Which dataframe library should I use to deduplicate a big table?"). The $0.00125 is Mem0's own extraction call, billed through OpenRouter. Mem0 rewrites the session with an LLM, so the stored wording changes from run to run ("prefers", "always uses"). Mem0 also prints warnings that spaCy and fastembed are not installed, so its BM25 keyword search is off.
3. The adapters in `baselines/` expose the same interface (`baselines/base.py`):
   - `write(session_text)`: ingest a session into the memory system
   - `retrieve(query)`: return the memories surfaced for a probe, each with its text, score and the raw metadata the system returned
   - `reset()`: delete the namespace
   Each adapter takes a `namespace` (episode id plus condition) so episodes cannot see each other's memories.
4. Both systems run as shipped, with their default extraction and search. The only configuration is the LLM endpoint (Mem0 calls the `config.toml` model through OpenRouter) and the embedder (Mem0 uses a local sentence-transformers model). Mem0's internal LLM calls are logged to the ledger. Supermemory's hosted processing is billed by Supermemory, so the ledger records its requests at $0.
5. These are the baseline conditions.

## Scope model and labelling rules

Steps 3 and 4 both depend on these rules. Define them before authoring any episode. The same rules go into `episodes/labelling_guide.md`, which the human annotators and the two scope-layer taggers all use.

### Memory tag

Each memory carries three fields:

| Field | Values |
| --- | --- |
| `scope` | `standing`, `project` or `single_task` |
| `key` | The project id for `project`, the task id for `single_task`, null for `standing` |
| `condition` | An optional predicate such as `rows > 1M`, otherwise null |

The key is what separates Project X from Project Y. Without it, a `project` tag cannot tell the resolver whether the memory applies to a probe.

### Scope definitions and cues

- `standing` applies to every future task unless a narrower memory overrides it. Typical cues: "always", "in general", "I prefer", "from now on", with no project or task named.
- `project` applies to every task that carries that project's key. Typical cues: an explicit project name ("for Project X"), or an instruction given while the session's declared active project is X.
- `single_task` applies only to the task in which it was stated. Typical cues: "this time", "for this one", "just for now".
- A condition is labelled separately from scope. "For datasets over 1M rows, I prefer Polars" is `standing` with `condition: rows > 1M`.

When a memory has no cue, assign the narrowest scope the session context supports: `single_task` if a task is active, otherwise `project` if a project is active, otherwise `standing`. This default is a design choice. Defaulting to `standing` would over-apply scoped instructions to other projects. Defaulting narrow under-applies them. Each failure maps onto one half of a mirrored pair, so the default shifts which half fails more often. Limitations records this.

### Task boundary

Every session and every probe in an episode carries a `task_id`. A probe counts as the same task as a `single_task` memory only if it shares the `task_id` of the session where the memory was stated (for example, "continue the dedupe job from earlier"). Without this rule no later probe could fall inside a `single_task` memory's scope, and that conflict type could not form a valid mirrored pair.

### Gold labels

Two team members label every memory independently, working from this section, before any system runs. They adjudicate disagreements by discussion and record the agreement rate. A memory that stays ambiguous after discussion gets rewritten or dropped from the suite, so every gold label is certain.

### System tagging

The write-time and read-time taggers use this section as their prompt and output the same `{scope, key, condition}` schema. They differ only in input:

- The write-time tagger sees the full session text at extraction.
- The read-time tagger sees only the retrieved memory text and whatever metadata the baseline returns.

If a baseline rewrites a memory and drops its scope cue, read-time tagging cannot recover it. That loss is the effect the write-time versus read-time ablation measures.

### Conflict resolution

When retrieved memories conflict, these rules apply in order, stopping at the first one that leaves a single memory. The scope-layer conditions put the rules in the agent prompt and the agent applies them. `episodes/validate.py` walks them over the gold tags:

1. **Applicability.** Keep a memory only if its key matches the probe and its condition holds. Memories with different keys never conflict.
2. **Narrowest scope.** `single_task` beats `project`, and `project` beats `standing`.
3. **More specific condition.** Within one scope, a memory with a condition that holds beats an unconditional one. "Polars for > 1M rows" beats an unconditional "pandas" when the table has 5M rows.
4. **Later memory.** Within one scope and one level of specificity, the later memory supersedes the earlier one. A same-scope restatement is treated as a correction.
5. **Unresolved.** If memories still conflict, no memory wins. The scoring step counts this as a failed action.

The suite contains no genuine ties, so rule 5 fires only when a tagger error or noisy retrieval produces one.

## Step 3: Build the episode suite

The suite contains 40 episodes arranged as 20 mirrored pairs, one JSON file per pair in `episodes/pairs/`. The format is `episodes/schema.json`. Load them with `episodes.loader.episodes()`, which yields the 40 episodes.

1. Each pair file holds:
   - Two or three sessions (standing preference, scoped instruction, and an optional later session for same-scope conflicts such as "Project X: switch to Polars"), each with order, `task_id` and active project
   - Every memory with its gold `{scope, key, condition}`, the decision it bears on and the action it calls for
   - Probe A (inside the scope) and probe B (outside the scope; mirrored), each with the expected action, the memory that should win and the pipeline rule that decides it
   - One or more unrelated standing preferences, with retention checks
2. Systems see only session text and probe text. Project, task and fact values (`active_project`, `task_id`, `facts`) are gold-only, so every scope signal is written into the text itself.
3. The suite has four pairs for each of five conflict types: project override, single-task override, conditional project scope, same-scope supersession, and same-scope specificity. The last two exercise rules 4 and 3 of the conflict resolution pipeline. Variants inside those types cover a task memory that beats a project memory that beats a standing one (three scopes at once), a conditional memory inside one project, and sessions in which the standing memory comes last. `tests/test_suite.py` keeps the suite varied in memory position, session length, phrasing, domain and chronology.
4. `uv run python -m episodes.validate` checks the schema and that each memory is a verbatim quote of its session. It also checks that every scope signal appears in the text, that probes A and B differ by at most 8 words, and that a walk of the five resolution rules over the gold tags reproduces every probe's expected memory and rule. Every probe has exactly one correct action, and genuine ties are excluded.
5. Gold labels follow [Scope model and labelling rules](#scope-model-and-labelling-rules) and `episodes/labelling_guide.md`. The drafted labels are the author's intent. Two annotators then label independently, without seeing them:
   - `uv run python -m episodes.annotate export labels/` writes a blank CSV per annotator.
   - `uv run python -m episodes.annotate agree labels/annotator_a.csv labels/annotator_b.csv --draft` reports per-field agreement and the disagreements.
   - The annotators settle disagreements between themselves. The adjudicated labels replace the drafted `gold` fields, and the tagging accuracy in Step 7 is scored against them.

## Step 4: Implement the scope-tagged memory layer

Each memory is tagged with `{scope, key, condition}` as defined in [Scope model and labelling rules](#scope-model-and-labelling-rules).

1. **Tagger.** `scope_layer/tagger.py` calls the agent model with `episodes/labelling_guide.md` as its instructions. It sees session text or retrieved text only, never gold fields. Task ids are gold-only, so it leaves the key null for `single_task`.
2. **Write-time version.** Tag memories during extraction, while the original conversation is still available. Each extracted instruction is stored as its own memory with the tag as metadata (`write(text, metadata=...)` on both adapters), so the tag survives the system's rewriting.
3. **Read-time version.** Tag memories after they have been retrieved by Supermemory or Mem0.
4. **Prompt block.** `scope_layer/tags.py` renders the labelled memories and the conflict resolution rules into the prompt's `{memories}` slot, oldest first when the system returns times. The agent chooses the memory itself, so no code decides for it, and `agent/prompt.md` is the same in every condition.

Interpretation of the two versions: if write-time tagging succeeds where read-time tagging fails, scope information was not sufficiently preserved or retrieved for downstream action selection.

## Step 5: Configure the experimental conditions (build the evals) 


| Condition                  | Name in `agent/conditions.py`                  | The agent's `{memories}` slot holds                                              | Purpose                                                                                                                                                  |
| -------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No memory                  | `no_memory`                                    | `(none)`                                                                         | Floor                                                                                                                                                    |
| Full transcript in context | `full_transcript`                              | every session, in order                                                          | Control. If the agent fails here, the failure is in reasoning. If it succeeds here and a memory system fails, extraction or retrieval is dropping scope. |
| Supermemory (as shipped)   | `supermemory`                                  | what Supermemory retrieves for the probe                                         | Baseline                                                                                                                                                 |
| Mem0 (as shipped)          | `mem0`                                         | what Mem0 retrieves for the probe                                                | Baseline                                                                                                                                                 |
| Scope layer, write-time    | `scope_write_mem0`, `scope_write_supermemory` | retrieved memories with the tags stored at write time, plus the resolution rules | Treatment                                                                                                                                                |
| Scope layer, read-time     | `scope_read_mem0`, `scope_read_supermemory`   | retrieved memories tagged after retrieval, plus the resolution rules             | Treatment                                                                                                                                                |


Every condition runs all 40 episodes. The scope layer runs on both memory systems, so each treatment is compared with the baseline it is built on: eight conditions, 320 runs. `CONDITION_INFO` in `agent/conditions.py` records each condition's role, system and layer for scoring.

What keeps the comparison fair:

1. The model, its settings (`config.toml`) and `agent/prompt.md` are the same in every condition. Only the `{memories}` text differs. The prompt is frozen: changing it means rerunning every condition.
2. Only session text and probe text reach a memory system, a tagger or the agent. `tests/test_conditions.py` replaces every gold field of an episode with a sentinel string and fails if the sentinel crosses any of those boundaries, for every condition.
3. Each run writes to a fresh namespace (episode id, condition and a random suffix). A run killed before cleanup cannot leave memories behind for a rerun to retrieve, and a cleanup that fails is recorded in the log as `cleanup_error` instead of hiding the error that stopped the run.

Run them:

1. One pair first, a few cents: `uv run python -m agent.runner --conditions all --episodes po-01a po-01b`
2. Then every condition on every episode: `uv run python -m agent.runner --conditions all`. A stopped run resumes where it left off. On a Mac, start it as `caffeinate -i uv run python -m agent.runner --conditions all` so the laptop does not sleep.

## Step 6: Run the episodes and log outputs (build logs) 

For each episode and each condition, log:

1. What was extracted and stored.
2. What was retrieved for the probe.
3. The tags, the resolution decision, and the pipeline rule that produced it (scope-layer conditions only).
4. The agent's selected action.
5. Token counts and cost.

Logging both retrieval and action allows each failure to be traced to extraction, retrieval, or the agent's reasoning.

1. Run `uv run python -m agent.runner --conditions no_memory mem0 scope_write_mem0 --episodes po-01a po-01b`. Leave out `--episodes` for all 40. `--list` prints the condition names.
2. Each episode and condition writes `runs/logs/<condition>/<episode_id>.json` with the stored memories, the retrieved memories, the tags, the prompt, the agent's response and the tokens and cost by component. The `gold_ref` block is for scoring only.
3. The agent's chosen memory is read from its action, since the agent applies the rules itself.
4. A log without an error is skipped on rerun, and `--force` reruns it. A provider rate limit (HTTP 429) is retried with a wait.

## Step 7: Score the results


| Metric                     | Computation                                                                                                                       |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Correction adherence       | Agent applies the scoped memory inside its scope and the standing preference outside it, across both halves of each mirrored pair |
| Unrelated-memory retention | Unrelated standing preferences remain intact after corrections                                                                    |
| Retrieval vs. action       | 2x2 table of retrieved right/wrong against acted right/wrong. The key cell is retrieved right, acted wrong.                       |
| Tagging accuracy           | Scope, key and condition from the layer, each compared with the Step 3 hand labels and scored per field                                                               |
| Cost                       | Tokens and dollars per episode per condition                                                                                      |


Report correction adherence against unrelated-memory retention, broken down by conflict type. Include representative successes and failures alongside aggregate numbers.

Run it after Step 6:

1. `uv run python -m scoring.score --dry-run` counts the judge calls needed and estimates their cost. It makes no calls.
2. `uv run python -m scoring.score` judges what is not cached yet and writes `reports/`: `summary.md` (every table below, with definitions and caveats), `examples.md` (representative successes and failures, chosen by rule), `episode_scores.csv` (one row per condition and episode), `tables/*.csv` and `figures/*.png`.
3. `uv run python -m scoring.review` picks 40 answers for a person to label (`reports/review/judge_review.md` and `.csv`). Fill in the CSV and rerun step 2: the human labels replace the judge's for those episodes, and `summary.md` reports how often the judge agreed.
4. Once the gold labels are adjudicated (Step 3), rerun step 2 with `--gold-status adjudicated`. Only scoring reruns. No agent calls are made.

How each number is computed:

- **Which action the agent took.** An LLM judge (`scoring/judge.py`, model set in `config.toml [judge]`) reads the request and the answer and says which of the competing memories' actions the answer actually uses, or `none`, or `mixed`. It sees the options in alphabetical order and never the expected action. Verdicts are cached in `runs/judge_cache.jsonl`, so rescoring is free. The chosen action maps back to a memory, which classifies a wrong answer as over-applied (a memory outside its scope), under-applied (a broader or less specific memory), superseded (an earlier memory of the same scope) or hedged (rule 5, no memory wins).
- **Correction adherence.** An episode is right when the judged action is the expected one. Reported per episode with a 95% Wilson interval, for probe A (in scope, where misses are under-application) and probe B (out of scope, where misses are over-application), and per pair (both halves right, so a fixed default scores nothing).
- **Unrelated-memory retention.** The judge's verdict on the pair's retention check.
- **Retrieval vs. action.** Retrieved right means the memory that should win is among the retrieved notes, matched word for word or, for rewritten notes, by the judge. No memory counts as retrieved wrong, the full transcript as retrieved right. Each wrong answer is also placed at the first stage that failed: extraction (Mem0 did not keep the winning memory), retrieval, scope lost (a competing memory reached the agent without its project, task or condition), tagging (a wrong or missing tag on a competing memory) or reasoning.
- **Tagging accuracy.** Per field against the gold labels: scope exactly; key for project memories (every word of the gold project name must appear) and standing ones (no key), not for single-task ones, since task ids are gold-only; condition strictly (variable, operator, value) and leniently (operator and value). Write-time tags are scored as the tagger produced them and again after storage. Read-time tags are scored as given to the retrieved memories.
- **Cost.** Each log's usage block. Supermemory bills its own processing, so it shows as $0.
- **Comparisons.** Exact McNemar tests on paired episodes for each treatment against its baseline, write-time against read-time, and the controls.

## Step 8: Run the vendor claim check

1. Select the LongMemEval knowledge-update and preference subsets (about 50 questions).
2. Run them through MemoryBench for the baseline systems.
3. Compare observed accuracy with published vendor claims.
4. Report discrepancies as observed. Vendor figures are a reference point, not ground truth.

## Step 9: Optional Jev resolver comparison

This step is conditional on access to Jev.

1. Run an LLM-based resolver and a Jev-based resolver on the same episodes.
2. Use Jev confidence scores to decide when the agent should ask the user instead of selecting an action.
3. Test whether the confidence scores are calibrated (for example, by comparing stated confidence with observed accuracy).

## Step 10: Report the results

The study is considered successful if it:

1. Shows whether a gap exists between successful retrieval and correct action.
2. Shows whether the scope-tagged layer improves correction adherence without reducing unrelated-memory retention.
3. Locates failures at extraction, retrieval, or agent reasoning.

Deliverables:

- Aggregate metrics per condition and conflict type
- The retrieval-vs-action 2x2 per condition
- Write-time versus read-time ablation results
- Tagging accuracy
- Cost comparison
- Vendor claim check results
- Selected episode-level examples

## Limitations

- Depends on third-party open systems (Supermemory and Mem0). Results may not generalize to closed-source memory systems.
- Vendor numbers are a reference point, not ground truth.
- The 40-episode suite is a constructed test, not a live deployment. Findings are bound to the sandbox scenarios.
- The narrow-scope default for uncued memories and the labelling guide are design choices. Results depend on them, and a different default would shift failures between the under-apply and over-apply halves of each pair.

## References

- Wu, D., Wang, H., Yu, W., Zhang, Y., Chang, K.-W., &amp; Yu, D. (2025). LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory. ICLR 2025. arXiv:2410.10813.
- Maharana, A., Lee, D.-H., Tulyakov, S., Bansal, M., Barbieri, F., &amp; Fang, Y. (2024). Evaluating Very Long-Term Conversational Memory of LLM Agents. ACL 2024, pp. 13851-13870.
- Pakhomov, E., Nijkamp, E., &amp; Xiong, C. (2025). ConvoMem Benchmark: Why Your First 150 Conversations Don't Need RAG. arXiv:2511.10523.
- Chhikara, P., Khant, D., Aryan, S., Singh, T., &amp; Yadav, D. (2025). Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory. arXiv:2504.19413.
- Daga, S., Sreedhar, S., &amp; Shah, D. (2025). Supermemory is the New State-of-the-Art in Agent Memory. Supermemory Research.
- Supermemory. (2025). MemoryBench: open-source framework for benchmarking memory providers.
- TypeSafe AI. (2026, September 15). Jev: System One model announcement.