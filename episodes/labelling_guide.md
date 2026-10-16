# Labelling guide

This file is the prompt for the two scope-layer taggers and the instructions for the two human annotators. It expands the "Scope model and labelling rules" section of the README. If the two disagree, fix the README and this file together.

## What gets labelled

Label each **instruction or preference the user states** (one sentence or clause, copied verbatim from the session). Do not label facts, questions, the assistant's replies, or the user's reasons ("because my teammate only knows pandas" is a reason, not a separate memory).

The memory `text` ends where the instruction ends. Leave out "because ..." clauses, so the quoted span is the same kind of thing in every pair. Clauses that do not change what is asked ("please", "if that's okay") are optional.

Each memory gets three fields:

| Field | Values |
| --- | --- |
| `scope` | `standing`, `project`, `single_task` |
| `key` | Project name for `project`, the session's task id for `single_task`, null for `standing` |
| `condition` | `<var> <op> <value>` or null |

## Scope

Decide in this order and stop at the first cue that fires.

1. **`single_task`**: the user limits the instruction to the current task. Cues: "this time", "for this one", "just for now", "for this job", "only for this". Key is the task id of the session. If a sentence has both a task cue and a project cue ("for Project X, just this time"), the narrower one wins, so label `single_task`.
2. **`project`**: the user names a project ("for Project X", "on Project X", "in the Atlas repo"), or says "in this project". Key is the project name as written. A bare instruction in a session whose declared active project is X also counts (see the default below).
3. **`standing`**: the user generalises. Cues: "always", "in general", "I prefer", "I tend to", "usually", "most of the time", "from now on", "by default", "whenever", "stick to", "standardize on", "go with", with no project or task named. A hedged cue ("usually", "most of the time") is still a standing preference, so label it like "I prefer".
4. **No cue at all.** Use the narrowest scope the session context supports: `single_task` if a task is active, otherwise `project` if a project is active, otherwise `standing`. In this suite every session has a task, so an uncued instruction would be `single_task`. Episodes therefore avoid uncued instructions. If you meet one, flag it. It will be rewritten.

A bare "from now on" inside a project session is ambiguous (standing cue, project context). Flag it. It will be rewritten ("from now on, on Project X" or "from now on, everywhere").

### Negative cues

"Never use X" and "don't use X" state the same choice as "use Y instead", so the memory's action is the alternative the same sentence names ("never use unittest, stick to pytest" has action `pytest`). Pairs use a negative cue only when the sentence names the alternative, so the action stays unambiguous. Scope cues work as before: "On Project Atlas, never use unittest" is `project`.

## Condition

A condition limits when a memory applies without changing its scope. Write it as `<var> <op> <value>`:

- Operators: `>`, `>=`, `<`, `<=`, `==`, `!=`.
- Numbers are written out in full: "over 1M rows" is `rows > 1000000`, "under 100MB" is `size_mb < 100`.
- Strings are bare words: "when writing for executives" is `audience == exec`.
- Use a short snake_case variable name. Two memories that test the same quantity use the same variable name.
- One condition per memory. Memories with "and"/"or" conditions are rewritten.

"For datasets over 1M rows, I prefer Polars" is `standing` with `condition: rows > 1000000`.

## Task boundary

Each session and each probe has a task id. A probe is the same task as a `single_task` memory only if it shares that memory's task id, which the probe text must show ("continue the dedupe job from earlier"). A probe that starts something new says so ("new task: ..."). Task ids are gold-only. The text carries the cue.

## Worked edge cases

| Statement (session context) | scope | key | condition | Why |
| --- | --- | --- | --- | --- |
| "I prefer bullet points." (no project) | standing | null | null | "I prefer", nothing narrower. |
| "For Project X, use pandas because my teammate only knows pandas." | project | Project X | null | Named project. The reason is not a memory. |
| "Use Polars for this one." (task t7) | single_task | t7 | null | "for this one". |
| "For Project X, just this time, write it in R." (task t7) | single_task | t7 | null | Task cue is narrower than the project cue. |
| "For datasets over 1M rows, I prefer Polars." | standing | null | `rows > 1000000` | Generalised, with a condition. |
| "I usually write summaries as bullet points." | standing | null | null | Hedged, but it still generalises. |
| "Never use unittest on Project Atlas, stick to pytest." | project | Project Atlas | null | Negative cue. The action is `pytest`. |
| "This time, give the amounts in cups." (task t4, active project Lumen, after "On Lumen, use grams" and "I prefer metric") | single_task | t4 | null | Task cue beats the project memory (rule 2), and the project memory beats the standing one for any other Lumen task. |
| "On Project X, files over 100MB should be parquet." | project | Project X | `size_mb > 100` | Scope and condition are labelled separately. |
| "Actually, on Project X switch to Polars." (after "on Project X use pandas") | project | Project X | null | Same scope and key as the earlier memory. This is a correction, so the later memory wins. |
| "On Project X, for datasets over 1M rows, use Polars." (after "on Project X use pandas") | project | Project X | `rows > 1000000` | Adds a condition, so it is a more specific memory, not a correction. |

## Writing episodes

- Every scope signal must be in the text. The adapters, the taggers and the agent never see `active_project`, `task_id` or `facts`. If the project is "Project Y" the probe says "Project Y". If the table has 5M rows the probe says "5M-row" and the `facts` entry repeats that string in `text`.
- Each memory's `text` is a verbatim substring of its session.
- Probes A and B differ only in the one thing that changes scope (project name, task cue, or the value a condition tests).
- Every pair has at least one unrelated standing memory with a retention check, and the probes are written so its effect shows in the answer.
- No genuine ties. `python -m episodes.validate` walks the resolution rules over the gold tags and fails if a probe is tied or resolves differently from the file.
