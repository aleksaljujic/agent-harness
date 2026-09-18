# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A minimal coding-agent harness: an LLM (via an OpenAI-compatible / Azure OpenAI
endpoint) driving a small tool loop (`bash`, `search`, `str_replace`, `read_file`,
`find_file`, `run_tests`) inside a disposable Docker container. Built as the
practical component of a thesis on tool-surface ablation (which tools change
agent cost/success, not just which model). The repo has two independent
consumers of the same harness core:

- an interactive REPL (`run.py`) for driving the agent against `workspace/`
- an eval framework with two pipelines: toy tasks (`evals/`) and SWE-bench Lite
  (`evals/swebench/`)

Design rationale and lessons learned live in [docs/agent/NOTES.md](docs/agent/NOTES.md)
— read it before changing the sandbox, tools, or system prompt; it explains *why*
things are shaped this way, not just what they do. [docs/README.md](docs/README.md)
indexes the rest of `docs/`.

## Setup

Requires Docker, Python 3.12+, `uv`, and an Azure OpenAI (or OpenAI-compatible)
deployment.

```bash
uv sync
docker build -t agent-sandbox .        # sandbox image; rebuild after Dockerfile changes
cp .env.example .env                   # fill ENDPOINT, API_KEY, MODEL, PROVIDER
```

`PROVIDER` is `openai` or `azure` (both use `OpenAIProvider`). Any model used
must have a pricing entry in `MODEL_PRICING` in
[src/harness/config.py](src/harness/config.py) — `Agent.usage.cost` raises if
the model isn't listed there, and `Settings` itself fails to construct for an
unpriced `MODEL`.

## Commands

```bash
uv run run.py                                    # interactive REPL against workspace/
uv run scripts/run_eval.py                        # toy-task eval sweep (writes to artifacts/evals/)
uv run scripts/run_swebench.py --limit 5           # SWE-bench Lite sweep (writes to artifacts/swebench/)
uv run evals/view_runs.py [task|fail]              # pretty-print runs.jsonl transcripts
uv run scripts/replay_request.py ...               # replay a saved messages/*.json payload against the API
uv run ruff check .                                # lint (only linter configured; no formatter/type-checker set up)
```

There is no automated test suite for the harness itself (`evals/eval_ws/` and
`evals/tasks.py` are *eval fixtures*, not unit tests — see
[docs/todo/TODO.md](docs/todo/TODO.md) item 5, still open).

Grading SWE-bench predictions needs the `swebench` package, which is a separate
dependency group, not installed by default:

```bash
uv sync --group swebench
```

Without it, `evals/swebench/steps/grade.py` fails to invoke the evaluator and
every instance silently gets a blank result (`resolved=False`,
`tests_*_total=0`) — indistinguishable at a glance from a model that failed
every test. **Always check the `grade_error` column before trusting a `0/0` or
an all-`False` `resolved` column** — it's empty only when the evaluator
actually produced a verdict (see [docs/todo/TODO.md](docs/todo/TODO.md) items 1
and 6–8 for the ways grading silently no-ops or hangs: missing dependency,
un-pulled eval images, or a false "image not found").

Commit or otherwise back up `workspace/` before pointing the REPL at a real
project — the agent edits files in place there.

## Architecture

### The agent loop (`src/harness/agent.py`)

`Agent.run(task)` is the whole loop: call the provider with the message
history and active tool schemas → if the response has no tool calls, return
its content (`termination_reason = "completed"`) → otherwise dispatch each
tool call against the sandbox, append `{"role": "tool", ...}` results, and
continue, up to `max_turns` (`termination_reason = "max_turns"`). `Usage` on
the agent accumulates tokens, cost, per-tool call/error counts, and
LLM-vs-tool wall time as the loop runs — this is the source of every cost
number reported by both eval pipelines.

`_dispatch` validates a tool call's JSON arguments against the tool's Pydantic
`args_model` before invoking its handler; a validation failure or unknown tool
name comes back as a normal `"ERROR: ..."` tool-result string rather than an
exception — the model sees it and can react (see NOTES.md §4, "tool output is
a prompt").

### Providers (`src/harness/providers/`)

`LLMProvider` is the abstract interface (`complete(messages, tools) ->
CompletionResult`); `OpenAIProvider` is the only implementation, used for both
`openai` and `azure` (`make_provider` in `providers/__init__.py` switches on
`settings.provider`). `CompletionResult.assistant_message` is a hand-built
plain dict (`role`, `content`, `tool_calls`) — never append the raw SDK
`ChatCompletionMessage` back into `messages`; response-only fields
(`refusal`, `annotations`, `audio`, deprecated `function_call`) get echoed to
the API on the next turn otherwise (this was a real bug — see
[docs/todo/TODO.md](docs/todo/TODO.md) item 2's confirmed-fix section, even
though it turned out not to be the root cause of the 400s it was chasing).

### Sandbox (`src/harness/sandbox.py`)

One Docker container per `Sandbox` instance, run once with `sleep <TTL>` and
driven afterward via `docker exec ... bash -lc <command>`. `workdir` (host) is
bind-mounted to `/work` (container) — same inodes, not a copy, so writes are
immediate and visible on both sides. `SCRIPTS` (`src/harness/scripts/`) is
mounted read-only at `/opt/agent-scripts` — tools that need real logic (not
just a bash one-liner) shell a script from there via `Tool.run_script()`,
piping a JSON payload in on stdin. Command output is capped at `MAX_OUTPUT`
(8000 chars) with an explicit truncation marker so the model knows a view is
partial rather than complete. `--user $(id -u):$(id -g)`, `--pids-limit`, and
`--memory` are load-bearing, not defensive boilerplate — see NOTES.md §2 and
§8 for what breaks without each one (root-owned files, fork bombs, a missing
mount dir silently created as root).

### Tools (`src/harness/tools/`)

Each tool is a `Tool(name, args_model, definition, handler)` dataclass in its
own module; `tools/__init__.py` collects them into `REGISTRY`/`TOOLS` (OpenAI
function-schema list)/`SCHEMAS`/`HANDLERS`. `get_active_tools(enabled)` filters
to a subset — this is what lets both eval pipelines run the same task across
different tool combinations to measure their effect. `settings.enabled_tools`
is validated against `REGISTRY` at config-load time, so an unknown tool name
in `.env` fails fast.

`bash` is a pure `sandbox.run()` wrapper; `search`, `str_replace`,
`read_file`, `find_file`, `run_tests` shell out to a same-named script in
`src/harness/scripts/` via `run_script()`. Adding a new tool means: a module in
`tools/` with `TOOL = Tool(...)`, an entry in `tools/__init__.py`'s `_TOOLS`
list, and (if it needs one) a script in `scripts/`.

Tool-specific notes that matter for correctness, not just behavior:
- `str_replace` requires `old_str` to match exactly once by default (the
  uniqueness check *is* the safety property — see NOTES.md §3); `replace_all`
  and `occurrence` exist so the model can resolve an ambiguous match without
  guessing a longer anchor.
- `search`'s `glob` arg is a file or directory path when it contains `/` and no
  wildcard (missing path → `ERROR`); otherwise it selects files with the same
  `fnmatch` rule as `find_file`, so path globs like `sympy/**/*.py` work. The
  file list goes to grep explicitly — neither `--include` (basename only) nor
  passing the glob as a literal target can express a path glob. `batch_300`
  ran with the old version, where such globs returned grep's "No such file or
  directory" in ~53% of `search` calls.
- `run_tests` overrides the sandbox's default 60s timeout with its own 300s
  (`DOCKER_EXEC_TIMEOUT`) since pytest runs can be slow.

### Config (`src/harness/config.py`)

`Settings` (pydantic-settings) loads from `ROOT/.env`; `ROOT` is anchored via
`Path(__file__).resolve().parent.parent.parent` specifically so behavior
doesn't depend on the invoking shell's cwd. `workspace`/`scripts` paths are
absolutized against `ROOT` if given relative. Two independently-tunable
runtime knobs live here (`max_turns`, `timeout`) that most call sites
override per-purpose rather than relying on the default (e.g. SWE-bench uses
its own `max_turns=40`/`run_timeout=1800` from `evals/swebench/config.py`).

### Two eval pipelines, same shape, separate concerns

Both pipelines follow: pick a tool universe → generate every tool combo that
still contains `bash` (`all_tool_combinations`, required by
`ok, ok = "bash" in combo`-style checks) → run each (combo × task/instance ×
repeat) → write JSON/CSV/Markdown artifacts. They're kept as separate
top-level implementations (not templated) because their units differ:
"task + a sandbox-inspection check" for the toy set vs. "instance + official
grader" for SWE-bench.

**`evals/` (toy tasks)** — `evals/tasks.py` defines `TASKS1`/`TASKS2` as
`(name, prompt, check)` tuples where `check` inspects the sandbox's
filesystem/output *after* the agent runs, never the agent's own report of
success (NOTES.md §5: models routinely report success on files they never
wrote). `evals/pipeline.py` drives the sweep; `evals/evals.py` has the
generic pieces (`prepare` seeds a fresh eval workdir, `log_run` appends every
run's full message transcript to `runs.jsonl` at the repo root, regardless of
`--artifacts-dir`). Entry point: `scripts/run_eval.py`.

**`evals/swebench/` (SWE-bench Lite)** — kept deliberately separate from
`harness.config` (`evals/swebench/config.py`'s `SweBenchSettings`, env prefix
`SWEBENCH_`) because it's evaluation policy, not agent runtime. Flow per
instance, in `evals/swebench/pipeline.py`:

1. `steps/provision.py` checks out `<repo>@<base_commit>` host-side (git
   history stripped to a single commit — keeps git out of the sandbox image
   and removes the upstream fix from reachable history; repos are cached as
   bare mirrors under `~/.cache/agent-harness/repos/`).
2. Agent runs against the checkout inside a `Sandbox` with
   `network=swe_settings.sandbox_network` (default `"none"` — v1 runs "blind",
   which is also why `run_tests` is excluded from `TOOL_UNIVERSE` here).
   `_run_agent_bounded` runs `agent.run()` in a thread with a wall-clock
   timeout (`wall_timeout` outcome) and catches exceptions from the API
   itself, capturing full error detail (`status_code`, `request_id`, `body`)
   rather than just the exception type name — needed to tell a real bug apart
   from a provider-side moderation false-positive (see
   [docs/todo/TODO.md](docs/todo/TODO.md) item 2).
3. `steps/predict.py` extracts a unified diff against the base commit
   (`git add -A && git diff --cached`) plus shape diagnostics
   (`empty_patch`, `patch_applied` via `git apply --check --reverse`).
4. `steps/grade.py` shells out to the official
   `swebench.harness.run_evaluation` and parses its `report.json` /
   `run_instance.log` per instance, backfilling `RunRow.resolved` and the
   `tests_*` counts. `grade_error` captures *why* no verdict exists when one
   doesn't (missing eval image, evaluator crash, etc.) — this is the field
   that disambiguates "genuinely failed" from "never actually graded".

Output tree per experiment: `artifacts/swebench/experiments/<timestamp>_<name>/`
with `conversations/` (rendered Markdown), `messages/` (raw message-list JSON,
for byte-exact replay via `scripts/replay_request.py`), `errors/`,
`predictions/` (official SWE-bench `predictions.jsonl` format), `grading/`,
`rows.{jsonl,csv}`, and `manifest.json`; every experiment also appends one line
to the append-only `artifacts/swebench/MANIFEST.jsonl` ledger. `RunRow`
(`evals/swebench/schemas.py`) is the single source of truth for every column
in that output — extend it (and `GRADE_FIELDS` if grader-sourced) rather than
adding ad hoc dict keys elsewhere in the pipeline. Column-by-column meaning is
documented in [docs/swebench/METRICS_SWE.md](docs/swebench/METRICS_SWE.md);
CLI flags in [docs/swebench/CLI.md](docs/swebench/CLI.md); dataset structure
in [docs/swebench/DATASET.md](docs/swebench/DATASET.md). Entry point:
`scripts/run_swebench.py`.

## Working notes

- `workspace/` (REPL), `evals/eval_ws/` (toy-task scratch), `artifacts/`
  (all eval output), and `scratch/` are git-ignored — treat their contents as
  disposable, generated, or session-local, not source.
- [docs/todo/TODO.md](docs/todo/TODO.md) is a live incident/investigation log
  for this project (root-caused bugs, open questions, what's still being
  chased) — check it before re-investigating something that looks like a
  known issue (e.g. eval-image pull timeouts, the moderation-flag 400s, the
  `str_replace` uniqueness error).
