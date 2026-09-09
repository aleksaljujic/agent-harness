# SWE-bench Lite Integration — Status & Gap Analysis

Scope: what the harness currently provides toward running **SWE-bench Lite**, and
what is still missing. Based on a static read of `src/harness/`, `evals/`,
`scripts/`, and cross-checked against `AUDIT_REPORT.md`.

> **Bottom line:** the *agent* side (LLM loop, tools, Docker sandbox, eval matrix
> runner) exists and works for toy tasks. The *SWE-bench* side (instance loader,
> repo checkout, environment provisioning, patch grader, leak controls) does
> **not exist** — nothing in the codebase reads `problem_statement`,
> `base_commit`, `test_patch`, `FAIL_TO_PASS`, or `PASS_TO_PASS`, and there is no
> `git clone` / `git checkout` / grader anywhere.

---

## 1. What exists today

| Piece | Location | State | Notes |
|---|---|---|---|
| Agent loop (tool-calling, `max_turns`, usage/cost tracking) | `src/harness/agent.py` | Works | `Usage` accumulates prompt/completion/calls and computes `cost` from `MODEL_PRICING`. |
| LLM provider (OpenAI-compatible, `temperature=0`) | `src/harness/providers/openai_provider.py` | Works | `make_provider` switches on `settings.provider` (`openai` / `azure`). |
| Docker sandbox (one container per run) | `src/harness/sandbox.py` | Works, with gaps | `docker run -d --rm`, bind-mounts `workdir → /work` and `SCRIPTS → /opt/agent-scripts:ro`, `--memory 2g`, `--pids-limit 256`, 1 h TTL, `destroy()` teardown. |
| Tools: `bash`, `search`, `str_replace`, `read_file`, `find_file`, `run_tests` | `src/harness/tools/` | Works | `run_tests` returns structured JUnit-parsed pass/fail (`src/harness/scripts/run_tests.py`), 300 s timeout. |
| Sandbox image | `Dockerfile` | Partial | `python:3.12-slim` + `pytest`, `pygame`, `ripgrep`, `xvfb`. **No `git`. No per-project dependencies.** |
| Eval matrix runner | `evals/pipeline.py`, `scripts/run_eval.py` | Works for toy tasks | Iterates `(tool_combo × task × repeat)` → `run_one` → writes `runs.jsonl` + `artifacts/evals/{logs,tables,conversation}`. |
| Task set | `evals/tasks.py` | Works | 12 hand-written `(name, prompt, check_lambda)` tuples + `SEEDS` dicts. |
| Task provisioning | `evals/evals.py::prepare` | Works for toy tasks | `rmtree` + `makedirs` + write every `SEEDS[name]` file, **before** the agent runs. |
| Parquet loader → `df_swe` | `src/harness/load_data/load_swe_bench_lite.py` | Loads only | Reads `hf://datasets/SWE-bench/SWE-bench_Lite/data/test-00000-of-00001.parquet` (300 rows × 17 cols). **Nothing consumes it.** Requires `pyarrow` + `huggingface_hub` (now in `pyproject.toml`). |
| Interactive REPL | `run.py` | Works | Single sandbox, `max_turns=50` (note: config default is 20 — inconsistent). |

### SWE-bench Lite dataset columns

Agent **input**: `repo`, `base_commit`, `problem_statement` (optionally `hints_text`).
Scoring **only**: `patch` (gold, unused), `test_patch`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `image`, `eval_script`, `log_parser`, `environment_setup_commit`, `version`.

---

## 2. What is missing

### 2.1 Instance → task adapter
- Build a task from a `df_swe` row: prompt = `problem_statement` (plus a system-prompt
  note that the agent is fixing a bug in an existing repo already checked out at `/work`).
- Must **not** pass `patch`, `test_patch`, `FAIL_TO_PASS`, or `PASS_TO_PASS` into the
  prompt or any mount.
- The current runner expects `(name, prompt, check_lambda)` tuples; SWE-bench needs a
  different shape (instance metadata + deferred grader).

### 2.2 Repo checkout / preparation
- No `git clone`, `git checkout`, or repo-prep step exists (`AUDIT_REPORT.md` §2a).
- Needed: clone `repo` on the **host**, `git checkout base_commit`, then **strip
  `.git`** (history + remotes + reflog) so the agent cannot recover the upstream fix
  via `git log` / `git show` / `git diff origin/HEAD`. Do this host-side, before the
  bind mount, so `git` stays out of the sandbox image.
- Add an assertion: `git log --oneline | wc -l == 1` and `git remote` empty (if a
  single-root-commit repo is kept for diffing), or no `.git` at all.

### 2.3 Environment provisioning — largest gap
- Each instance needs its repo's dependencies at specific versions
  (`environment_setup_commit`, `version`). The `agent-sandbox` image has none of
  `astropy`, `django`, `sympy`, `flask`, ….
- Official path: the per-instance images in the `image` column
  (`swebench/sweb.eval.x86_64.<instance_id>`), which ship the built environment.
- Options:
  1. Run the agent **inside** the per-instance SWE-bench image (adapt `Sandbox.IMAGE`
     to be per-run).
  2. Keep the current sandbox for the agent, and only use SWE-bench images in the
     grader (agent produces a diff blind to a fully-installed env — riskier, tests
     may not even import).
  3. Build a combined image per instance (agent tools + SWE-bench env).

### 2.4 Patch grader — does not exist
Runs **after** `agent.run()` returns, in a context the agent cannot influence:
1. Capture the agent's changes as a unified diff (`git add -A && git diff`, or diff
   against the pristine checkout).
2. Apply the agent diff + gold `test_patch` in the instance's environment.
3. Run the `FAIL_TO_PASS` and `PASS_TO_PASS` node-ids (via `eval_script` /
   `log_parser`, or the official harness).
4. **resolved** ⟺ every `FAIL_TO_PASS` test passes **and** every `PASS_TO_PASS` test
   still passes.
5. Populate `tests_fail_to_pass_{total,passed}` / `tests_pass_to_pass_{total,passed}`
   in the result row.

### 2.5 Leak / isolation controls (required for valid numbers)
From `AUDIT_REPORT.md`:
- **§2b Network** — sandbox runs with default Docker networking → full outbound
  internet. Agent can fetch the upstream PR / fixed file / a published solution.
  Add `--network none` (make it a `Settings` field, default-deny).
- **§1 Test-patch timing** — the `SEEDS`/`prepare` path writes all provided files
  *before* the agent runs. If `test_patch` is ever routed through it, that is a
  confirmed leak. Keep `test_patch` and all instance metadata in the harness process
  only — never under `workdir`, never under `SCRIPTS`.
- **§3 Workdir isolation** — `eval_ws/<name>` is keyed on task name only and reset by
  `shutil.rmtree(..., ignore_errors=True)` (silent on failure). Key on full run
  identity (`<session>/<instance>/<run_index>`) and fail loudly, or use
  `tempfile.mkdtemp()` per run.
- **§4 Timeout** — no wall-clock cap; per-command timeout doesn't kill the
  in-container process. Add a per-run deadline with a hard `docker rm -f` kill, plus
  a token/cost ceiling.

### 2.6 Result schema drift
The result records currently being produced include fields the committed
`evals/pipeline.py` `row` dict does **not** emit: `toolset_condition`,
`termination_reason`, `reasoning_tokens`, `tool_calls_breakdown`,
`tool_call_errors`, `error_recovery`, `tests_fail_to_pass_*`,
`tests_pass_to_pass_*`. Either there is uncommitted work or a second runner script
not in the tree. Reconcile before wiring SWE-bench so the grader writes to a
single, known schema.

---

## 3. Recommended approach

**Split responsibilities:**

- **This harness → prediction generation only.** For each instance: prep repo,
  run the agent on `problem_statement`, emit one line of
  `predictions.jsonl`:
  ```json
  {"instance_id": "...", "model_name_or_path": "...", "model_patch": "<unified diff>"}
  ```
- **Official `swebench` harness → scoring.** Feed it `predictions.jsonl`:
  ```
  python -m swebench.harness.run_evaluation \
      --dataset_name SWE-bench/SWE-bench_Lite \
      --predictions_path predictions.jsonl \
      --run_id <run_id>
  ```
  It manages the per-instance images, applies `test_patch`, runs F2P/P2P, and emits a
  resolved/unresolved report — collapsing §2.3 and §2.4.

This leaves three things to build on our side: **§2.1** (adapter), **§2.2**
(host-side checkout + history strip), **§2.5** (network-off, per-run workdir,
wall-clock kill). Then merge the official report back into our result rows for the
tool-ablation analysis.

---

## 4. Task checklist

- [ ] Reconcile result-row schema (§2.6); pick the canonical field set.
- [ ] `--network none` + configurable network policy in `Sandbox` / `Settings` (§2.5).
- [ ] Per-run unique workdir; replace silent `rmtree` (§2.5).
- [ ] Per-run wall-clock timeout with `docker rm -f` hard kill; token/cost ceiling (§2.5).
- [ ] Host-side repo checkout module: clone → `checkout base_commit` → strip `.git` → assert (§2.2).
- [ ] Instance → task adapter: `df_swe` row → prompt, with metadata kept in-process (§2.1).
- [ ] Prediction writer: agent diff → `predictions.jsonl` (§3).
- [ ] Wire official `swebench.harness.run_evaluation`; parse its report (§3).
- [ ] Merge resolved/F2P/P2P results back into harness result rows (§2.4).
- [ ] Smoke test on ~5 instances across ≥2 repos before a full 300-instance run.
