# TODO

## 5. Set up `tests/` with pytest — for tomorrow

No test infrastructure exists for the harness code: no `tests/` folder, no
`test_*.py`/`conftest.py` anywhere under `src/` or `evals/`, and `pytest` isn't
even a dependency in `pyproject.toml` (`evals/eval_ws/pytest/` is an eval-task
fixture, not a test suite for the harness itself).

To do:
- Add `pytest` to the `dev` dependency group in `pyproject.toml`.
- Create `tests/` with unit tests for the recent fixes:
  - `src/harness/scripts/str_replace.py` — n=0, n>1 (with line numbers),
    `occurrence`, `replace_all`, out-of-range, mutually-exclusive args.
  - `src/harness/tools/search.py` — glob-with-slash vs. basename glob,
    empty-match returns "No matches." (not the leaked sandbox string).
  - `src/harness/sandbox.py` — output truncation marker.
  - `src/harness/providers/openai_provider.py` — `assistant_message` shape
    (no `refusal`/`annotations`/`audio`/`function_call` leakage, `tool_calls`
    key omitted when empty).
- Decide pytest config (`testpaths`, whether `src` needs `pythonpath` or the
  `harness` package is already installed editable via `uv sync`) and whether
  sandbox/docker-dependent tests should skip when Docker/the `agent-sandbox`
  image is unavailable.

## 6. Pre-pull eval images before grading — 10 min timeout kills first run per repo

Hit on the first real graded run (`20260912_031417_smoke_test`). The `swebench`
package was installed and grading genuinely ran, but the instance still came
back ungraded:

```
03:15:04 - Image not found locally, attempting to pull...
03:25:16 - ERROR - Image swebench/sweb.eval.x86_64.astropy_1776_astropy-12907 not found
```

The image exists on the registry (verified with `docker manifest inspect`) —
it is just **4.16 GB**, and the evaluator's pull gave up after exactly 10
minutes. After pulling it manually, re-grading the same predictions worked
and produced a real verdict (F2P 0/2, P2P 13/13).

So every repo that hasn't been pulled before burns ~10 min and then reports a
false `0/0`. Options:
- Pre-pull the eval images for the selected instances before the grading step
  (`docker pull` per unique `sweb.eval.*` image, with progress), or
- Call `swebench.harness.run_evaluation.main()` in-process with `task_repo=`
  to build locally instead of pulling. Note the CLI does **not** expose
  `--task_repo` — it is a Python-API-only parameter, so the current
  `python -m swebench.harness.run_evaluation` subprocess in `grade.py` can
  never reach it.
- Budget disk: ~4 GB per repo.

Fixed alongside this: `grade_error` was computed by `grade.py` but dropped on
the floor (not in `GRADE_FIELDS`, no field on `RunRow`), so a never-graded run
looked identical to a genuine all-tests-failed run. It is now a real column,
populated with the first `ERROR` line from the evaluator's `run_instance.log`.

## 1. `swebench` dependency group not installed → grading silently no-ops — RESOLVED

`swebench` is declared as a separate `dependency-group` in
[pyproject.toml](../../pyproject.toml) rather than a base dependency, so
`uv sync` does not install it by default. When it's missing,
`evals/swebench/steps/grade.py` runs `python -m swebench.harness.run_evaluation`
as a subprocess, which exits non-zero immediately (`ModuleNotFoundError`).
`grade.grade()` then falls back to `_blank()` for every instance, so
`resolved`, `tests_fail_to_pass_total`, and `tests_pass_to_pass_total` are
all `0`/`False` across the board — indistinguishable from a model that
actually failed every test.

Fix: run `uv sync --group swebench` before any swebench experiment, and/or
have `grade.grade()` detect the missing module and raise loudly instead of
producing blank-but-valid-looking rows.

## 2. `django__django-11630` and `scikit-learn__scikit-learn-14087` throw `BadRequestError` — IN PROGRESS

**Correction:** the original claim that both instances fail "across all three
toolsets" was wrong. Verified from `rows.jsonl`:

| instance | bash | bash+search+str_replace | bash+str_replace |
|---|---|---|---|
| django-11630 | **400** (turn 9, 9.5k tok) | completed | **400** (turn 5, 2.5k tok) |
| scikit-learn-14087 | **400** (turn 9, 32.8k tok) | completed | completed |

3 failures / 15 runs, non-deterministic, uncorrelated with payload size (a
2,553-token request failed while a 313,203-token one succeeded elsewhere) — so
"payload size" is not the cause.

Root cause was **undiagnosable**: `_run_agent_bounded` in
`evals/swebench/pipeline.py` kept only `type(e).__name__` and discarded the
server's error body, and transcripts were rendered markdown, not replayable
requests.

Shipped:
- `_run_agent_bounded` now returns full error detail (`status_code`,
  `request_id`, `body`, `response.text`, traceback); saved per-run to
  `errors/<run>.json`, summarized in the new `RunRow.error_message` column.
- Every run's exact message list is now persisted to `messages/<run>.json`
  for byte-exact replay.
- `scripts/replay_request.py` re-sends a saved payload (`--prefix`,
  `--bisect`) and prints the server's verbatim error.
- Fixed one confirmed correctness bug independent of the above:
  `agent.py:72` was appending the raw OpenAI SDK `ChatCompletionMessage`
  object back into the message list sent to the next request, instead of a
  clean `{role, content, tool_calls}` dict. Response-only fields (`refusal`,
  `annotations`, `audio`, deprecated `function_call`) were being echoed
  upstream — plausible given the failures are non-deterministic across
  otherwise-identical runs. Fixed in
  `providers/openai_provider.py`/`providers/base.py`/`agent.py`.

**Still open:** re-run `django-11630` (`bash`, `bash+str_replace`) and
`scikit-learn-14087` (`bash`) with `--no-grade` to confirm the fix, or use
`replay_request.py` on the errors/messages captured next time it recurs.

## 4. Stray top-level `swebench/` directory — REMOVED

Found while investigating #2: an untracked, broken duplicate of
`evals/swebench/` sat at the repo root (`swebench/pipeline.py`, `grade.py`,
`dataset.py`, `predict.py`, `provision.py`, `__init__.py`). It imported
`swebench.config`/`swebench.prompt`/`swebench.schemas`, none of which existed
in it — a stale snapshot from before the code was reorganized under
`evals/swebench/` (with its `steps/` subpackage). Nothing in `src/`, `evals/`,
or `scripts/` imported it, but since it had an `__init__.py` (a real package,
not a namespace package) sitting at the repo root, it would have **shadowed
the real pip `swebench` evaluator** for any process with the repo root on
`sys.path` — which `scripts/run_swebench.py` adds explicitly
(`sys.path.insert(0, str(ROOT))`). That would have kept #1 broken even after
`uv sync --group swebench`. Deleted.

## 3. `str_replace` tool has a high error rate — FIXED

Root cause confirmed: all 20 failures returned the identical message
`ERROR: old_str appears 2 times, must be unique. Include more surrounding
lines.` from `src/harness/scripts/str_replace.py`. In
`sphinx/ext/autodoc/__init__.py`, `DataDocumenter` (~1704) and
`AttributeDocumenter` (~2095) hold byte-identical ~14-line blocks. The old
error named no line numbers and advised extending the match **downward**,
which can never disambiguate since the duplicate block extends downward too
— the model looped the identical call until `max_turns`.

Shipped in `src/harness/scripts/str_replace.py` +
`src/harness/tools/str_replace.py`:
- The `n > 1` error now reports the line number of every match and advises
  extending **upward** instead.
- New optional args `replace_all` (change every occurrence) and `occurrence`
  (1-based, pick one) so the model can act on the error directly instead of
  guessing a longer anchor.

Also fixed two adjacent bugs that starved the model of information during
these runs:
- `src/harness/tools/search.py` — `grep --include` matches basenames only,
  so a glob containing `/` (a full file path) silently matched nothing; now
  a `/`-containing glob is used as grep's search target instead of
  `--include`.
- `src/harness/tools/search.py` — the empty-result guard never matched the
  string `sandbox.run` actually returns for a clean empty match
  (`"Without return, exit = N"`), leaking it to the model instead of
  `"No matches."`.
- `src/harness/sandbox.py` — command output was silently cut at 8000 chars
  with no marker; now appends `... [truncated N more chars; narrow the
  command]` so the model knows a view is incomplete.
