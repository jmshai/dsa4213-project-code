# DSA4213 Project -- Agent Memory: What is used and What isn't?

A study of whether agents act on the correct memory when a scoped instruction and a standing preference both apply to the same situation.

## Overview

Memory systems are typically evaluated on retrieval (whether the correct memory was returned). This project evaluates the next stage: whether the agent converts retrieved memory into the correct action.

**Hypothesis:** Explicit scope representation and scope-aware conflict resolution improve adherence to scoped instructions while preserving standing preferences outside their scope. Some failures are expected to occur even when the correct memory is retrieved.

**Example.** Standing preference: "For datasets over 1M rows, I prefer Polars." Scoped instruction: "For Project X, use pandas because my teammate only knows pandas."

| Probe | Correct action |
|---|---|
| Deduplicate a 5M-row table for Project X | pandas (scoped instruction applies) |
| Deduplicate a 5M-row table for Project Y | Polars (scoped instruction does not apply) |

Each such pair is a mirrored pair. A system that fails the first probe under-applies the scoped memory. A system that fails the second over-applies it.

## Contents

1. [Prerequisites](#step-0-prerequisites)
2. [Set up the environment](#step-1-set-up-the-environment)
3. [Install the baseline memory systems](#step-2-install-the-baseline-memory-systems)
4. [Build the episode suite](#step-3-build-the-episode-suite)
5. [Implement the scope-tagged memory layer](#step-4-implement-the-scope-tagged-memory-layer)
6. [Configure the experimental conditions](#step-5-configure-the-experimental-conditions)
7. [Run the episodes and log outputs](#step-6-run-the-episodes-and-log-outputs)
8. [Score the results](#step-7-score-the-results)
9. [Run the vendor claim check](#step-8-run-the-vendor-claim-check)
10. [Optional: Jev resolver comparison](#step-9-optional-jev-resolver-comparison)
11. [Report the results](#step-10-report-the-results)
12. [Limitations](#limitations)
13. [References](#references)

## Proposed Repository Structure

```
.
├── README.md
├── episodes/              # 40-episode suite (20 mirrored pairs)
│   ├── schema.json
│   └── pairs/
├── baselines/
│   ├── supermemory/       # Supermemory adapter
│   └── mem0/              # Mem0 adapter
├── scope_layer/
│   ├── write_time.py      # tags memories during extraction
│   ├── read_time.py       # tags memories after retrieval
│   └── resolver.py        # scope-precedence conflict resolution
├── agent/                 # agent that converts memory into an action
├── runs/                  # raw logs per episode per condition
├── scoring/               # metrics and 2x2 analysis
├── longmemeval_check/     # MemoryBench subset run
└── reports/
```

## Step 0: Prerequisites

- Python environment and package manager of choice
- API access for the LLM used as the agent
- Access to the Supermemory and Mem0 open repositories
- A copy of LongMemEval and access to MemoryBench
- Jev access (optional; the Jev comparison is conditional on access)

## Step 1: Set up the environment

1. Clone this repository.
2. Create an isolated environment and install dependencies.
3. Store API keys in environment variables or a local `.env` file. Do not commit keys.
4. Fix the agent model, temperature, and prompt template. Use identical settings across all conditions so that differences are attributable to the memory condition.

## Step 2: Install the baseline memory systems

1. Install Supermemory from its repository and confirm it can store and retrieve a test memory.
2. Install Mem0 from its repository and confirm the same.
3. Build a thin adapter for each system exposing two functions:
   - `write(session_text)`: ingest a session into the memory system
   - `retrieve(query)`: return the memories surfaced for a probe
4. Run both systems as shipped, without modification. These are the baseline conditions.

## Step 3: Build the episode suite

The suite contains 40 episodes arranged as 20 mirrored pairs.

1. Define an episode schema containing:
   - Session 1 text (standing preference)
   - Session 2 text (scoped instruction)
   - Probe A (inside the scope)
   - Probe B (outside the scope; mirrored)
   - Expected action for each probe
   - Conflict type label
   - One or more unrelated standing preferences, for the retention metric
2. Author 20 scenarios. Each yields one in-scope probe and one out-of-scope probe.
3. Vary the conflict type across pairs (for example: tool choice, formatting, project-level versus single-task scope, conditional preferences such as "rows > 1M").
4. Label the correct action for every probe before running any system.
5. Hand-label the intended scope (standing, project, single task) and any condition for every memory. These labels are the reference for tagging accuracy.

## Step 4: Implement the scope-tagged memory layer

Each memory is tagged with a scope (`standing`, `project`, or `single_task`) and an optional condition (for example, `rows > 1M`).

1. **Resolver.** When retrieved memories conflict, resolve by scope precedence rather than recency or similarity. The narrower applicable scope governs; a standing preference governs when no narrower scope applies.
2. **Write-time version.** Tag memories during extraction, while the original conversation is still available.
3. **Read-time version.** Tag memories after they have been retrieved by Supermemory or Mem0.
4. Expose the output of each version in a common format so that the agent receives the same input structure in every condition.

Interpretation of the two versions: if write-time tagging succeeds where read-time tagging fails, scope information was not sufficiently preserved or retrieved for downstream action selection.

## Step 5: Configure the experimental conditions

| Condition | Purpose |
|---|---|
| No memory | Floor |
| Full transcript in context | Control. If the agent fails here, the failure is in reasoning. If it succeeds here and a memory system fails, extraction or retrieval is dropping scope. |
| Supermemory (as shipped) | Baseline |
| Mem0 (as shipped) | Baseline |
| Scope layer, write-time | Treatment |
| Scope layer, read-time | Treatment |

Every condition runs all 40 episodes.

## Step 6: Run the episodes and log outputs

For each episode and each condition, log:

1. What was extracted and stored.
2. What was retrieved for the probe.
3. The tags and resolution decision (scope-layer conditions only).
4. The agent's selected action.
5. Token counts and cost.

Logging both retrieval and action allows each failure to be traced to extraction, retrieval, or the agent's reasoning.

## Step 7: Score the results

| Metric | Computation |
|---|---|
| Correction adherence | Agent applies the scoped memory inside its scope and the standing preference outside it, across both halves of each mirrored pair |
| Unrelated-memory retention | Unrelated standing preferences remain intact after corrections |
| Retrieval vs. action | 2x2 table of retrieved right/wrong against acted right/wrong. The key cell is retrieved right, acted wrong. |
| Tagging accuracy | Scope tags from the layer compared with the hand labels from Step 3 |
| Cost | Tokens and dollars per episode per condition |

Report correction adherence against unrelated-memory retention, broken down by conflict type. Include representative successes and failures alongside aggregate numbers.

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

## References

- Wu, D., Wang, H., Yu, W., Zhang, Y., Chang, K.-W., & Yu, D. (2025). LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory. ICLR 2025. arXiv:2410.10813.
- Maharana, A., Lee, D.-H., Tulyakov, S., Bansal, M., Barbieri, F., & Fang, Y. (2024). Evaluating Very Long-Term Conversational Memory of LLM Agents. ACL 2024, pp. 13851-13870.
- Pakhomov, E., Nijkamp, E., & Xiong, C. (2025). ConvoMem Benchmark: Why Your First 150 Conversations Don't Need RAG. arXiv:2511.10523.
- Chhikara, P., Khant, D., Aryan, S., Singh, T., & Yadav, D. (2025). Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory. arXiv:2504.19413.
- Daga, S., Sreedhar, S., & Shah, D. (2025). Supermemory is the New State-of-the-Art in Agent Memory. Supermemory Research.
- Supermemory. (2025). MemoryBench: open-source framework for benchmarking memory providers.
- TypeSafe AI. (2026, September 15). Jev: System One model announcement.
