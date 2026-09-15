# TODO

## [x] 1. `swebench` dependency group not installed → grading silently no-ops — RESOLVED

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

## [ ] 2. `django__django-11630` and `scikit-learn__scikit-learn-14087` throw `BadRequestError` — IN PROGRESS

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

**Root cause found (confirmed, not just a hypothesis):** re-ran a fresh django
instance (`django-16816`, `20260912_144704_django_smoke`) on the harness build
that already includes the `agent.py` echo fix above, and it still hit
`api_error`. The now-captured `errors/<run>.json` gives the real body this
time:

```
status_code: 400, code: "invalid_prompt"
message: "Invalid prompt: your prompt was flagged as potentially violating
our usage policy."
```

So the raw-SDK-message-echo theory was **not** the (or not the only) cause —
it reproduced on already-fixed code. This is the provider's content-moderation
classifier flagging the prompt, not a request-construction bug in our code.
Inspected the full conversation up to the failing turn
(`messages/gpt-5.4-nano__bash__django__django-16816__0.json`): plain Django
source + a stack trace (`FieldDoesNotExist`, `ManyToManyField`, admin checks
code) — nothing that looks like an actual policy violation. Best read: a false
positive, possibly triggered by the density of `raise`/`Exception`/traceback
patterns combined with "locate the cause... resolve the issue" instructions,
which can pattern-match to prompt-injection heuristics.

This is provider-side and not something our code can fix directly. What's
left:
- ~~Decide whether to auto-retry on `code == "invalid_prompt"`~~ — **shipped.**
  `OpenAIProvider.complete()` now retries that code specifically (2 retries,
  2s apart, `INVALID_PROMPT_RETRIES`), and *only* that code: every other 400
  still aborts the run, since a real 400 is deterministic and retrying it
  just loops (the A5 policy still holds, narrowed rather than reversed).
  Verified offline against the real captured error body from
  `20260912_145932_django_smoke`: it is recognised and retried, while a
  `context_length_exceeded` 400 is not.
- The retry is **self-measuring**, which also answers the non-determinism
  question for free instead of needing a separate `replay_request.py`
  experiment: `RunRow.invalid_prompt_retries` counts retries that eventually
  succeeded, and `errors/<run>.json` carries the count for runs that retried
  and still failed. After the next batch: if retries frequently succeed the
  classifier is flaky; if they never do, the content is hard-blocked and the
  retry should be removed as pure waste.
- Fixed while here, a latent bug in the capture itself: `_error_detail` read
  `body["error"]["code"]`, but the OpenAI SDK hands back the **flat** error
  dict (`{message, type, param, code}`), so `api_code`/`api_param`/
  `api_message` were silently `None` on every error ever captured — confirmed
  against the saved `errors/*.json`. Now handles both shapes.
- The `agent.py:72` raw-message fix from before still stands as a real
  correctness fix (response-only SDK fields shouldn't be echoed upstream) —
  just not the explanation for these errors.

## [x] 3. `str_replace` tool has a high error rate — FIXED

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

## [x] 4. Stray top-level `swebench/` directory — REMOVED

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

## [ ] 5. Set up `tests/` with pytest — for tomorrow

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

## [ ] 6. Pre-pull eval images before grading — 10 min timeout kills first run per repo

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

## [ ] 7. Pre-warm eval images for all SWE-bench Lite repos, or decide to pre-clone instead

Surfaced while smoke-testing different repos for #2 (moderation-flag
investigation): every *new* repo hit during a smoke test cold-pulls its
`sweb.eval.*` image (~4 GB, see #6), which is slow enough to block quick
iteration between repos (`django` → `scikit-learn` → next). Idea raised:
clone/pre-pull everything up front instead of paying the cost per-repo,
ad hoc, mid-investigation.

Confirmed via `datasets.load_dataset("SWE-bench/SWE-bench_Lite", split="test")`
+ `Counter(r["repo"] ...)`: **300 instances, 12 unique repos** — django/django
(114), sympy/sympy (77), matplotlib/matplotlib (23), scikit-learn/scikit-learn
(23), pytest-dev/pytest (17), sphinx-doc/sphinx (16), astropy/astropy (6),
psf/requests (6), pylint-dev/pylint (6), pydata/xarray (5), mwaskom/seaborn
(4), pallets/flask (3). Source git mirrors already cloned (`~/.cache/agent-harness/repos/`,
3.7GB): astropy, django, matplotlib, psf/requests, scikit-learn, sphinx-doc,
sympy (7/12) — missing pytest-dev/pytest, pylint-dev/pylint, pydata/xarray,
mwaskom/seaborn, pallets/flask, all small.

Needs before deciding:
- Total disk budget at ~4 GB/repo × unique-repo-count for eval images specifically
  — this is Docker image size, not source-clone size, so "clone the repos"
  and "pre-pull the eval images" are two different fixes for two different
  things (source checkout for the agent to work in, vs. the Docker image
  the *grader* runs tests in) — don't conflate them when scoping this.
- Whether to just `docker pull` all `sweb.eval.*` images once, in the
  background, ahead of any experiment (simplest), vs. building images
  in-process per #6's `task_repo=` option.

## [ ] 8. Evaluator says "Image not found locally" for an image that IS present

Hit while smoke-testing `scikit-learn__scikit-learn-10297`
(`20260912_150323_scikit-learn-smoke`). `run_instance.log` logged `Image not
found locally, attempting to pull...` at `15:04:08` and was still stuck on
that same line 12+ minutes later (no `ERROR`, no progress) — worse than #6's
"cold pull just takes a while," since `docker images` showed
`swebench/sweb.eval.x86_64.scikit-learn_1776_scikit-learn-10297` **already
present locally**, 5.34GB, created ~4 weeks ago (verified with
`docker system df -v`, not just `docker images | grep`). Killed both the
`run_swebench.py` and `swebench.harness.run_evaluation` processes (PIDs
136824/137485) since it was making no visible progress.

So the evaluator's local-image existence check can produce a **false
negative** — it doesn't see an image that unambiguously exists — and then
gets stuck attempting a pull instead of erroring out quickly. This is
different from, and worse than, #6/#7 (genuinely-cold image, slow but
bounded ~10min pull): here pre-pulling might not even help if the detection
itself is what's broken.

To do:
- Re-run grading on the same `predictions.jsonl` (no API cost, predictions
  already exist) and see if it reproduces or was a one-off.
- If it reproduces: figure out what image identifier/tag the evaluator
  actually checks for vs. what's in `docker images` — likely a naming/tag
  mismatch (e.g. digest vs. tag, or a repo prefix difference) rather than a
  real absence.
- If it's a hang rather than a bounded timeout: check whether
  `run_evaluation` needs a max-wait wrapper independent of whatever internal
  timeout #6 identified, since this one didn't seem to hit any timeout at
  all in 12+ minutes.

## [ ] 9. `repeats > 1` silently drops all but the last repeat's grade — root cause confirmed

Surfaced during external review of the experimental protocol (see
[RECOMMENDATION.md](../RECOMMENDATION.md) point 2) before it was ever hit in
practice — every run so far has used the default `repeats=1`
(`evals/swebench/config.py:31`), so no experiment has actually been affected
yet. Root-caused before enabling `repeats>1` for the first time.

**Confirmed mechanism** (not just "grader sees them as the same instance" —
traced to the exact line): `evals/swebench/steps/predict.write_predictions`
writes one JSON line per `(instance_id, run_index)` to `predictions.jsonl`,
so with `repeats=3` the same `instance_id` appears on 3 lines with 3
different `model_patch` values. The **official, pip-installed** `swebench`
package then loads that file and does, in
`swebench/harness/run_evaluation.py:743`:

```python
predictions = {pred["instance_id"]: pred for pred in predictions}
```

A dict comprehension over a list with duplicate keys keeps only the
**last** occurrence — so only run_index 2's patch is ever actually built,
run, and graded. Runs 0 and 1's patches are silently discarded **before
grading even starts**, not "graded as if identical."

Back in our own `evals/swebench/pipeline.py:316`
(`r = results.get(row.instance_id)`), `grade()`'s result dict has exactly
one entry per `instance_id` (matching only the last repeat that actually
ran) — so **all three rows** in `rows.csv` for that instance get backfilled
with that one verdict, including the two rows whose own patch was never
tested at all.

This bug lives partly in the third-party `swebench` package (the dedup-by-
instance_id dict comprehension), not only in our pipeline — so it can't be
fixed by changing `RunRow`/`GRADE_FIELDS` alone.

**Stopgap (in effect now):** keep `repeats=1` for the upcoming 50-instance
batch and any batch before this is fixed. With one prediction per
`instance_id`, there's no collision and grading is correct.

**Real fix, when `repeats>1`/pass@k is actually needed:** don't put multiple
repeats of the same instance in one `predictions.jsonl` / one
`run_evaluation` call. Grade each `run_index` as its own evaluator
invocation (own `predictions.jsonl` containing one row per instance, own
`run_id`), then merge results back keyed by `(instance_id, run_index)`
instead of `instance_id` alone.

## [ ] 10. `wall_timeout` doesn't stop the agent thread — usage undercounted, sandbox used after destroy

Surfaced by code review of `src/harness/agent.py` + `_run_agent_bounded`
(`evals/swebench/pipeline.py:72-95`), confirmed by reading both files —
not yet hit in a way that was traced back to this at the time, but real and
live in every `wall_timeout` row produced so far.

**Confirmed mechanism:** `_run_agent_bounded` runs `agent.run()` in a daemon
thread and does `t.join(timeout)`. If the thread is still alive after that,
it returns `"wall_timeout"` immediately — but never signals the thread to
stop. `Agent.run()` (`agent.py`) has no cooperative-cancellation check
anywhere in its `for turn in range(self.max_turns)` loop, so the thread just
keeps calling the model and dispatching tools on its own, unobserved, until
it either finishes naturally or hits `max_turns`.

Two concrete effects, both confirmed by reading `pipeline.py:117-176`:

1. **`RunRow`'s cost/token/timing columns for a `wall_timeout` row are a
   mid-flight snapshot, not a final value.** Right after
   `_run_agent_bounded` returns, `run_one` reads `agent.usage.prompt`,
   `.completion`, `.cost`, `.llm_time_seconds`, `.tool_time_seconds`,
   `.calls`, `.tool_calls`, `.tool_call_errors` (`pipeline.py:154-169`) to
   build the row — while the background thread may still be mutating that
   same `Usage` object. The row's `cost`/`prompt_tokens` are whatever they
   happened to be at the moment of the read, not what the run actually
   spent — so `total_cost` in the experiment/manifest ledger is
   **undercounted, unpredictably**, for every `wall_timeout` row.
2. **The sandbox is destroyed while the thread may still be using it.**
   `pipeline.py:119-120` does `if termination_reason == "wall_timeout" and
   s: s.destroy()` immediately after the bounded run returns. The still-alive
   thread keeps calling `_dispatch` → `handler(self.sandbox, args)` →
   `sandbox.run()` → `docker exec` against a container name that no longer
   exists. This doesn't crash — it just returns errors that increment
   `tool_call_errors`, except nothing reads that `Usage` object anymore
   (the row was already built and returned). Net effect: API calls keep
   being spent, silently, on a sandbox that's gone, running concurrently
   with whatever instance/run picks up next in the sequential loop — an
   invisible cost leak with no corresponding row to blame it on.

**Status: fixed** (agent-side effects). `Agent` now carries
`self.stop = threading.Event()`, checked at the top of each turn *and* before
each individual tool dispatch; `_run_agent_bounded` sets it and waits
`STOP_GRACE_SECONDS` (5) before returning, so `agent.usage` has settled before
`run_one` reads it and the abandoned thread stops dispatching into a sandbox
that is about to be destroyed. Remaining, deliberately not fixed here: a
thread blocked *inside* `provider.complete()` cannot be interrupted by an
event — that needs a request-level timeout on the OpenAI client, which is a
separate change. The two smaller items below are also still open.

**Fix as implemented:** cooperative cancellation via a `threading.Event`.
- `Agent.__init__`: add `self.stop = threading.Event()`.
- `Agent.run()`: check `self.stop.is_set()` at the top of the per-turn loop
  (set `termination_reason = "stopped"` and return if set) **and** again
  before each individual tool dispatch inside the `for call in
  result.tool_calls` loop — a single turn with several tool calls can run
  long on its own.
- `_run_agent_bounded`: on `t.is_alive()` after the first `join(timeout)`,
  call `agent.stop.set()`, then `t.join(5)` (short grace period) before
  reading `agent.usage` for the row. If still alive after that, it's stuck
  inside `provider.complete()` itself (a separate problem — fixable with a
  request-level timeout on the OpenAI client, not with the stop event).

**Two smaller, non-urgent items in the same file, noted while reading it:**

- `Agent.__init__`'s parameter is spelled `system_promt` (missing the second
  `p`), and `pipeline.py:114` passes `system_promt=SWEBENCH_SYSTEM` —
  matching typo, so `SWEBENCH_SYSTEM` **does** reach the model correctly
  today; there's no silent fallback to `DEFAULT_SYSTEM_PROMPT` happening
  (confirmed — no `**kwargs` on `__init__`, so a mismatched keyword would
  raise `TypeError` loudly, not fail silently). Doesn't change the TODO #1
  `str_replace`-prompt-bias finding or anything else already documented.
  Still worth fixing in both files in the same change, since the two sides
  only agree by coincidence.
- `provider = make_provider(settings)` at module level in `agent.py`, plus
  `self.provider = provider or globals()["provider"]` in `__init__`, means
  a provider gets constructed at **import time** whenever `harness.agent` is
  imported, even by a caller (like every eval pipeline) that always passes
  its own `provider=`. Harmless today but an odd side effect to import;
  `provider or make_provider(settings)` (lazy, only when actually needed)
  would be cleaner.
- `Usage.cost` raises `ValueError` if `self.model` (set from `provider.model`
  at `Agent.__init__` time) isn't in `MODEL_PRICING` — correct behavior, but
  since it's only evaluated when `.cost` is read (i.e. after the run,
  building the `RunRow`), a model/reasoning combination or Azure deployment
  name that doesn't map cleanly to a `MODEL_PRICING` key blows up **after**
  turns/API calls were already spent, not before. Worth a one-time check of
  the model→pricing mapping before a large batch (e.g. the planned
  mini/nano × reasoning sweep), not something to discover mid-run.