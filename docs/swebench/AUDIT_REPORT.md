# Harness Integrity Audit (Static Review)

Scope: static reading only. No commands were run — no containers started, no
`git`, no harness execution, no network calls. Line numbers refer to the
working-tree state at audit time.

> **Overarching finding:** there is **no SWE-bench instance machinery in this
> codebase yet.** No code loads `problem_statement`, `test_patch`,
> `FAIL_TO_PASS`, `PASS_TO_PASS`, `base_commit`, or `instance_id`; nothing
> imports `datasets` / `load_dataset` / HuggingFace; there is no `git clone`,
> `git checkout`, or repo-preparation script anywhere. The eval harness
> (`evals/`) runs 12 hand-written toy tasks defined as
> `(name, prompt, check_lambda)` tuples in `evals/tasks.py`. The SWE-bench
> protocol described in `../research/reference_research.md` (deferred `test_patch`,
> git-history strip, per-arm isolation) is a **design note, not an
> implementation.** Several findings below are therefore about the *path a
> SWE-bench integration would take through the existing code*, since that is
> what a full experiment would exercise.

---

## Summary

- **1. Test Patch Timing — CANNOT DETERMINE FROM CODE ALONE (no SWE-bench loader exists) / RISK by design.** The only task-provisioning path (`evals/evals.py::prepare` → bind mount, `evals/pipeline.py:27`) writes *every* task file into `/work` **before** `agent.run()` (`evals/pipeline.py:36`). One current task (`pytest`) deliberately ships its test file to the agent. If SWE-bench instances are wired through this same `SEEDS`/`prepare` path, `test_patch` would be applied pre-run → **CONFIRMED LEAK**. The current grader (`check`) runs *after* the agent and is not mounted (OK).
- **2a. Git history in container — N/A / RISK by omission.** No checkout or clone exists; `/work` is a bind-mounted plain directory with no `.git`. There is no history-stripping step to inherit when SWE-bench is added.
- **2b. Network egress — RISK (near-CONFIRMED from config).** `src/harness/sandbox.py:20–28` runs the container with **no `--network` flag** → Docker default bridge → outbound internet. No egress allowlist, no `--dns`, no firewall config anywhere in the repo. Author notes (`../research/REZIME.md:121`, `../agent/NOTES.md:256`) explicitly confirm the network is reachable.
- **3. Container / state isolation — OK with caveats.** Fresh container per run (`docker run --rm` + unique name, `docker rm -f` teardown); the bind-mount dir is wiped and recreated per `run_one` (`evals/evals.py:9–10`). Caveats: `shutil.rmtree(..., ignore_errors=True)` can silently leave stale files; the mount path is keyed on task name only (not arm / `run_index`); orphaned in-container processes from a timed-out command persist for the rest of that run.
- **4. Timeout / termination — RISK.** No per-run wall-clock timeout of any kind. Only stop conditions are `max_turns` (LLM-turn count; 20 in config, 50 in `run.py`) and the model choosing to stop. No token or tool-call budget. The 60 s per-command timeout (`src/harness/sandbox.py:32–41`) only catches the exception and returns a string — it does **not** kill the process spawned inside the container; hard kill (`docker rm -f`, SIGKILL) happens only at run teardown (`evals/pipeline.py:44`).

---

## 1. Test Patch Timing

### What exists

There is no SWE-bench instance data in the repo. Grep across `*.py` for
`problem_statement`, `test_patch`, `FAIL_TO_PASS`, `PASS_TO_PASS`,
`base_commit`, `instance_id`, `load_dataset`, `datasets`, `huggingface`,
`golden`, `gold_patch` returns **zero hits in harness code** — only prose in
`../research/reference_research.md` (lines 39, 64, 133) describing an intended
protocol.

### Task provisioning path (the mechanism a SWE-bench loader would reuse)

1. `evals/pipeline.py:142` — pipeline iterates `for name, task, check in tasks`
   (tuples from `evals/tasks.py`).
2. `evals/pipeline.py:146–150` → `run_one(...)`.
3. `evals/pipeline.py:27` — `workdir = prepare(name, seeds)` — **first thing in `run_one`.**
4. `evals/evals.py:7–14` — `prepare()`:
   - `d = os.path.abspath(f"./eval_ws/{name}")`
   - `shutil.rmtree(d, ignore_errors=True)` then `os.makedirs(d)`
   - `for fname, content in seeds.get(name, {}).items(): write file`
   - returns `d`.
5. `evals/pipeline.py:28` — `s = Sandbox(workdir)`.
6. `src/harness/sandbox.py:24` — `-v {workdir}:/work` (read-write bind mount).
7. `evals/pipeline.py:36` — `agent.run(task)` — agent starts **after** all seed
   files are on disk and mounted.
8. `evals/pipeline.py:37` — `ok = bool(check(s))` — grader runs **after** the
   agent returns (or raises).

### Findings

- **Seed files (including test files) are present before the agent starts.**
  `prepare()` writes everything in the `SEEDS` dict for that task, then the dir
  is mounted, then the agent runs. Order is unambiguous:
  `evals/pipeline.py:27` (prepare) → `:28` (mount) → `:36` (agent).
- **One current task deliberately exposes its test to the agent.**
  `evals/tasks.py:40–44` (`pytest` task): prompt = *"Run the tests and fix the
  code so they all pass. Do not modify the test file."* Its seeds
  (`evals/tasks.py:93–96`, `SEEDS2["pytest"]`) write both `test_math.py` and a
  buggy `mathlib.py` into `/work`. This is intentional for a "make tests pass"
  task, but it is exactly the shape of a `test_patch` pre-application leak.
- **The grader is not a leak vector in the current design.** `check` is a
  Python lambda living in the harness process (`evals/tasks.py:11, 17, 22, …`).
  It is never written to disk or mounted. It calls `s.run("…")` to inspect
  sandbox state *after* the agent finishes. The agent cannot read it.
- **`FAIL_TO_PASS` / `PASS_TO_PASS` identifiers do not exist anywhere**, so
  there is currently no file the agent could read them from. The new
  `run_tests` tool (`src/harness/tools/run_tests.py`,
  `src/harness/scripts/run_tests.py`) takes node-ids *from the model*; it does
  not read them from metadata.
- **The harness source, docs, `.env`, and `evals/tasks.py` are NOT reachable
  from inside the container.** Only two mounts exist
  (`src/harness/sandbox.py:24–25`): `{workdir}:/work` and
  `{SCRIPTS}:/opt/agent-scripts:ro`, with `-w /work`. The repo root is not
  mounted. So instance metadata sitting on the host (if it were added outside
  `/work`) would not be directly readable — subject to the network caveat in
  §2.

### Verdict

**CANNOT DETERMINE FROM CODE ALONE for SWE-bench specifically (not
implemented).** For the provisioning path that a SWE-bench integration would
almost certainly use: **RISK / CONFIRMED LEAK if `test_patch` is added to the
`SEEDS`/`prepare` flow**, because that flow applies all provided files before
the agent runs. The deferred-application requirement from
`../research/reference_research.md:39` has no corresponding code.

---

## 2. Git History Exposure

### 2a. Does the container repo retain full git history?

**Confirmed from code:** there is no repo checkout at all.

- No `git clone`, `git checkout`, `git init`, `--depth`, `--orphan`,
  `checkout --orphan`, `reflog`, or history-squash anywhere in `evals/`,
  `src/`, `scripts/`, `run.py` (grep for `git`, `clone`, `checkout`, `.git`,
  `reflog`, `fetch`, `remote` returns only: `search.py:33` and
  `find_file.py:4`, which merely *exclude* `.git` from search results; and the
  `subprocess` calls in `sandbox.py` / `run_tests.py`, none git-related).
- `Dockerfile` installs `xvfb`, `ripgrep`, `pytest`, `pygame`. It does **not**
  install `git` and does **not** add any repo.
- `/work` is a bind mount of `eval_ws/<name>` (`evals/evals.py:8`), a directory
  created fresh by `os.makedirs` and populated only with `SEEDS` content. No
  `.git` directory is created or copied.

**Inferred, needs manual check:** if `git` is nonetheless available in the base
image `python:3.12-slim` (it typically is **not**, but the image contents were
not inspected here), and a SWE-bench integration later mounts a real cloned
repo into `/work` **without** stripping `.git`, then `git log` / `git show` /
`git diff <base>..origin/HEAD` would expose the upstream fix. **No stripping
step exists to reuse**, so this is a **RISK by omission** for the planned
experiment.

### 2b. Would the container have network access to github.com / git remotes?

**Confirmed from config:**

- `src/harness/sandbox.py:20–28` — the full `docker run` argument list:
  `-d --rm --name <n> --memory 2g --pids-limit 256 --user <uid>:<gid>
  -v <workdir>:/work -v <scripts>:/opt/agent-scripts:ro -w /work <image>
  sleep 3600`. **There is no `--network`, `--net`, `--dns`, `--add-host`, or
  `--cap-drop` flag.** Docker's default for a container with no network flag is
  the `bridge` network with NAT to the host's outbound route → **full outbound
  internet access**, including `github.com`, `pypi.org`, `huggingface.co`, and
  arbitrary LLM/search APIs.
- There is **no** `docker-compose.yml`, no `compose*.yaml`, no
  `.dockerignore`, no `daemon.json`, and no firewall/iptables/egress-proxy
  configuration file anywhere in the repo.
- The Docker daemon's own configuration (host-level `daemon.json`, a
  default-deny bridge, an outer network namespace, corporate egress proxy) was
  **not** inspected and cannot be inspected by reading this repo — see Manual
  Checks.

**Corroborating author statements (explicit, in-repo prose — not config):**

- `../research/REZIME.md:121`: *"`no-network` test je 'prolazio' jer mreža nije bila
  isključena — testirao je pogrešnu stvar."* ("The `no-network` test 'passed'
  because the network was not disabled — it tested the wrong thing.")
- `../agent/NOTES.md:256`: *"it never once tried `pip install pytest`, even with
  network access available."*

### Verdict

- **2a: N/A (no checkout in code) → RISK by omission** for the planned
  SWE-bench run: there is no history-strip step, so one must be written from
  scratch, not merely verified.
- **2b: RISK, effectively CONFIRMED from configuration.** The container is
  created with default networking and there is no egress control anywhere in
  the repository. Independent of the git-history question, unrestricted network
  access is itself a first-order leakage channel for SWE-bench (agent can fetch
  the upstream PR, the fixed file, or a published solution). The only
  unknown is a host-level Docker restriction outside this repo.

---

## 3. Container / State Isolation Between Tool-set Arms and Runs

### Mechanism (from code)

- **Loop structure:** `evals/pipeline.py:140–150` —
  `for tools in tool_combos: for name, task, check in tasks: for run_index in
  range(repeats): run_one(...)`. Every `(toolset, task, run_index)` triple is a
  separate `run_one` call.
- **Per-run container:** `evals/pipeline.py:28` — each `run_one` constructs a
  new `Sandbox`. `src/harness/sandbox.py:19` — `self.name =
  f"agent-{uuid.uuid4().hex[:8]}"` (unique per instance).
  `src/harness/sandbox.py:21` — `docker run -d --rm` (auto-remove on stop).
  `src/harness/sandbox.py:43–44` — `destroy()` = `docker rm -f <name>`, called
  in the `finally` of `run_one` (`evals/pipeline.py:44`). So the **container
  and its writable layer are genuinely fresh per run** and force-removed after.
- **Filesystem the agent writes to:** a **bind mount**, not a named volume, not
  an overlay upperdir: `src/harness/sandbox.py:24` — `-v {workdir}:/work`,
  where `workdir = prepare(name, seeds)` = host path `eval_ws/<name>`.
- **Reset between runs:** `evals/evals.py:9–10` —
  `shutil.rmtree(d, ignore_errors=True)` then `os.makedirs(d)` at the top of
  every `prepare()` call, i.e. once per `run_one`. So the bind-mount contents
  are recreated from `SEEDS` each run.
- **Image:** single static `agent-sandbox` image (`src/harness/sandbox.py:6`),
  built once by the operator (`README.md`), never rebuilt by the harness. Not a
  per-run state carrier (the writable layer is per-container).
- **Read-only shared mount:** `src/harness/sandbox.py:25` —
  `-v {SCRIPTS}:/opt/agent-scripts:ro`. Shared across all runs but read-only
  and static (the four helper scripts). Not a state-carry vector.
- **Host-side artifacts** (`runs.jsonl` via `evals/evals.py:22`, `artifacts/…`
  via `evals/pipeline.py:157–165`) are written by the harness process, never
  mounted into the container.

### Caveats / weaknesses

1. **`ignore_errors=True` on `rmtree`** (`evals/evals.py:9`): if deletion of any
   file fails, it is silently skipped and the run proceeds with a partially
   stale `/work`. Low probability (container runs as the host uid via
   `--user`, `src/harness/sandbox.py:23`, so file ownership should not block
   deletion), but there is no assertion that the directory is actually empty
   before seeding. Stale `.pyc` / `.bak` files are visibly accumulating in the
   committed `evals/eval_ws/` tree (e.g. `refactor/calc2.py.bak`,
   `pytest/__pycache__/…`), which shows this directory is not always pristine
   in practice.
2. **Mount path keyed on task name only** (`evals/evals.py:8`,
   `f"./eval_ws/{name}"`): not parameterised by model, toolset, or
   `run_index`. The pipeline is currently **sequential**, so runs do not
   overlap and this is safe today. But any future parallelism (across arms or
   repeats) would have multiple containers bind-mounting the **same host
   directory** simultaneously → cross-run contamination. Nothing in the code
   prevents this.
3. **CWD dependence** (`evals/evals.py:8`): `./eval_ws/...` is relative to the
   harness process CWD. Running from a different directory silently uses a
   different `eval_ws` root (there are two on disk: `./eval_ws` and
   `./evals/eval_ws`). Not an isolation break per se, but a reproducibility
   footgun.
4. **Intra-run process leakage** (see §4): a command that hits the 60 s timeout
   is not killed inside the container, so later tool calls *in the same run*
   share the sandbox with a runaway process. This is within-run, not
   between-run, but it degrades the per-run state guarantee.
5. **No per-arm discard of an overlay upperdir.** `../research/reference_research.md:39`
   envisions `fuse-overlayfs` with per-arm upper dirs; the actual
   implementation is a plain bind mount reset by `rmtree`. Functionally
   equivalent *if* `rmtree` always fully succeeds; weaker as a guarantee.

### Verdict

**OK for the current sequential pipeline** — each run gets a fresh container
and a re-seeded working directory. **RISK if runs are ever parallelised**, and
a **latent weakness** in that isolation depends on `rmtree` silently doing its
job rather than on an explicit fresh-directory guarantee or a discarded
overlay/volume.

---

## 4. Timeout / Forced Termination

### Wall-clock timeout per run

- **None.** `src/harness/agent.py:46–85` (`Agent.run`): the loop is
  `for _ in range(self.max_turns):` with no time check, no deadline, no
  `signal.alarm`, no `time`-based break. `evals/pipeline.py:34, 45` measure
  `wall_time` with `time.perf_counter()` **for reporting only** — the value is
  written to the CSV row (`evals/pipeline.py:65`) and never compared to a
  limit.
- `../research/reference_research.md:39` calls for a "60-minute wall-time cap per
  (instance, arm, run) with SIGKILL on timeout." **No such cap exists in code.**

### Per-command timeout

- `src/harness/sandbox.py:32–41` — `Sandbox.run(command, timeout=None)`,
  `timeout = timeout if timeout is not None else settings.timeout`.
- `src/harness/config.py:39` — `timeout: int = Field(60, ge=1, le=600)` →
  default **60 s** per command.
- `src/harness/tools/run_tests.py:5, 51` overrides this to **300 s** for the
  `run_tests` tool (via `run_script(..., timeout=DOCKER_EXEC_TIMEOUT)` →
  `src/harness/tools/base.py:15–18`).
- **Termination behaviour is soft.** On `subprocess.TimeoutExpired`
  (`src/harness/sandbox.py:40–41`) the code just returns the string
  `f"Error : exited after {timeout}s"`. `subprocess.run(timeout=…)` SIGKILLs
  the **`docker exec` client process** on the host, but the process tree it
  started **inside the container is not reaped** — `docker exec` does not
  propagate the client's death to the in-container process. That process keeps
  running (consuming the container's 2 GB / CPU) until either the whole
  container is removed or PID 1 (`sleep 3600`) exits. There is no
  `docker exec … --sig-proxy`, no `docker stop`, no `docker kill`, no
  `os.killpg`, no in-container `timeout(1)` wrapper.

### Hard kill (where it does happen)

- `src/harness/sandbox.py:43–44` — `destroy()` runs `docker rm -f <name>`,
  which sends SIGKILL to the container (PID 1 and all descendants) and removes
  it. This is the only forceful termination in the codebase.
- It is invoked from the `finally` block of `run_one`
  (`evals/pipeline.py:43–44`) and the `finally` of `run.py:32–33`. So cleanup
  is guaranteed **at end of run**, but not before — a run that is "stuck" in a
  way that still returns from each `provider.complete()` and each
  `sandbox.run()` will simply continue until `max_turns` is exhausted.
- `SANDBOX_TTL = 3600` (`src/harness/sandbox.py:9`) — PID 1 is `sleep 3600`, so
  with `--rm` the container self-removes ~1 h after creation even if the
  harness process is killed. This is a **container-lifetime backstop**, not a
  per-run timeout, and 3600 s is long enough that a wedged run would burn
  significant model spend first.

### Budget-based stop conditions

- **`max_turns` only.** `src/harness/agent.py:36` —
  `self.max_turns = max_turns or settings.max_turns`. Sources:
  `src/harness/config.py:37` — `max_turns: int = Field(20, ge=1, le=100)`;
  `run.py:13` — hard-coded `Agent(s, max_turns=50, …)`;
  `scripts/run_eval.py:33–34` + `evals/pipeline.py:133` — `--max-turns` CLI,
  default `None` → `settings.max_turns` (20).
- One `max_turns` unit = **one LLM response**, not one tool call and not a
  token count. A single turn may emit multiple tool calls
  (`src/harness/agent.py:72–83` loops over `result.tool_calls`).
- **No token budget.** `Usage` (`src/harness/agent.py:13–30`) accumulates
  `prompt` / `completion` / `calls` and computes `cost`, but nothing in
  `Agent.run` compares these to a ceiling.
- **No tool-call-count budget.**
- **Early exit:** `src/harness/agent.py:67–68` — if a turn produces no tool
  calls, `run` returns immediately with the assistant text.

### Relationship between the two mechanisms

They barely interact, because only one truly exists:

- The **only** per-iteration stop check is `for _ in range(self.max_turns)` at
  `src/harness/agent.py:52`, evaluated at the top of each turn, before
  `provider.complete()`.
- The per-command 60 s timeout is **inside** a turn (during tool dispatch,
  `src/harness/agent.py:74`) and does not end the run — it returns an error
  string that becomes the tool result, and the loop proceeds to the next turn.
- There is no wall-clock or token condition to order against `max_turns`. Net
  effect: a run ends when (a) the model stops calling tools, or (b) `max_turns`
  LLM calls have been made — whichever first — with no upper bound on
  wall-time or spend in between.

### Verdict

**RISK.** No wall-clock cap; the required "SIGKILL on 60-min timeout" is
absent. Command-level timeouts are non-forceful and can orphan a process
inside the container for the remainder of the run. The sole guardrails are
`max_turns` (an LLM-call count, inconsistently set: 20 vs 50) and the 1 h
container TTL. Forceful termination (`docker rm -f`) exists only at run
teardown.

---

## Manual Checks Needed

These could not be determined by reading the repository:

1. **Is `git` present in the `agent-sandbox` image?**
   Static reading shows the `Dockerfile` never installs it and `python:3.12-slim`
   normally omits it, but the built image was not inspected.
   Check: `docker run --rm agent-sandbox bash -lc 'which git && git --version'`.
   (Also `which curl wget ssh`.)

2. **Does the container actually have outbound network?**
   The repo has no `--network` flag and no egress config, but a host-level
   Docker restriction (custom default bridge, egress proxy, outer netns,
   corporate firewall) cannot be seen from here.
   Check: `docker run --rm agent-sandbox bash -lc 'getent hosts github.com; curl -sS -m 5 -o /dev/null -w "%{http_code}\n" https://github.com; curl -sS -m 5 -o /dev/null -w "%{http_code}\n" https://huggingface.co'`.
   If any of these succeed, the SWE-bench run needs `--network none` (or an
   allowlisted proxy) regardless of the git-history question.

3. **Docker daemon defaults.**
   Inspect `/etc/docker/daemon.json` and `docker network inspect bridge` on the
   experiment host for any non-default `"iptables": false`, custom DNS, or a
   restricted default network.

4. **Does `docker exec`'s timeout actually leave a process running?**
   Confirm the §4 claim: `docker run -d --rm --name t agent-sandbox sleep 600`,
   then a Python snippet doing
   `subprocess.run(["docker","exec","t","bash","-lc","sleep 120 & echo started; wait"], timeout=5)`,
   then `docker exec t ps aux` after the `TimeoutExpired` — check whether the
   inner `sleep 120` is still listed. Then `docker rm -f t`.

5. **`rmtree` completeness under load.**
   The `ignore_errors=True` path is silent. If you want assurance, temporarily
   run the pipeline with `ignore_errors=False` (or add a post-`makedirs`
   `assert not os.listdir(d)`), or diff `eval_ws/<name>` contents against the
   expected `SEEDS` set after a run.

6. **The (not-yet-written) SWE-bench loader.**
   Everything in §1 and §2a is about code that does not exist. Once the
   instance loader / repo-prep script is written, re-audit: where the instance
   JSON is read, whether `test_patch` is applied and *when*, whether `.git` is
   stripped, and what exactly lands under `/work` vs. stays on the host.

---

## Recommended Fixes

Descriptions only — not implemented.

### §1 — Defer test material until after the agent exits (when SWE-bench is added)

- **New repo-prep step** (new module, e.g. `evals/swebench.py`): apply only the
  *code* state for the instance — `base_commit` checkout of the source repo —
  into the workdir that becomes `/work`. Do **not** write `test_patch` files
  there.
- **Grader step**: after `agent.run()` returns in `evals/pipeline.py` (around
  line 37), and inside a context where the agent can no longer act, `git apply`
  / write the `test_patch`, then run the `FAIL_TO_PASS` + `PASS_TO_PASS`
  node-ids and record per-test results.
- **Keep instance metadata off every mount.** `problem_statement` goes into the
  task prompt string only (`agent.run(task)`); the raw instance JSON,
  `test_patch`, and the pass/fail id lists must live only in the harness
  process, never under `workdir` and never under `SCRIPTS`
  (`src/harness/sandbox.py:24–25`).
- **Guard the existing `SEEDS` path** so it cannot be used to ship a
  `test_patch`: in `evals/evals.py::prepare`, if a SWE-bench instance is
  detected, refuse to write any path matching the instance's `test_patch`
  file list.
- The current `pytest` toy task (`evals/tasks.py:40–44`, `93–96`) is fine to
  keep as-is *for that task* — it is explicitly a "make the provided tests
  pass" exercise — but it must not share code with the SWE-bench grader path.

### §2a — Strip git history in the container repo (when SWE-bench is added)

- In the repo-prep step, after checking out `base_commit`, replace history with
  a single root commit and drop remotes/reflogs: conceptually
  `rm -rf .git && git init -q && git add -A && git -c user.email=… -c user.name=… commit -qm base`
  (or `git checkout --orphan` + `git reflog expire --all` + `git gc --prune=now`),
  performed on the host copy **before** it is bind-mounted. Add an assertion
  that `git log --oneline | wc -l == 1` and that `git remote` is empty.

### §2b — Remove container network access

- `src/harness/sandbox.py:20–28`: add `"--network", "none"` to the
  `docker run` argument list (and, defensively, `"--dns", "0.0.0.0"` is moot
  under `none`). If the sandbox legitimately needs a package index or the
  model API is reached *from inside* the container (it is not today — the
  provider call is in the harness process, `src/harness/agent.py:55`), replace
  `none` with a locked-down `--network` pointing at an allowlisting proxy.
- Make it configurable but **default-deny**: e.g. a
  `network: str = "none"` field in `Settings` (`src/harness/config.py`), passed
  through `Sandbox.__init__`, with any value other than `"none"` requiring an
  explicit opt-in flag in `scripts/run_eval.py`.
- Fix the `no-network` toy task (`evals/tasks.py:52–56`) at the same time — its
  `check` is `lambda s: True` and `../research/REZIME.md:121` notes it never actually
  tested anything.

### §3 — Make working-dir isolation explicit, not `rmtree`-dependent

- `evals/evals.py:7–14`: key the workdir on the full run identity, not just
  task name — e.g. `./eval_ws/{session_id}/{name}/{run_index}` — so concurrent
  or repeated runs can never share a host directory.
- Replace `shutil.rmtree(d, ignore_errors=True)` with either
  `ignore_errors=False` (fail loudly) or, after `os.makedirs(d)`,
  `assert not os.listdir(d)`.
- Consider creating each run's workdir under `tempfile.mkdtemp()` and deleting
  it in `run_one`'s `finally` next to `s.destroy()` (`evals/pipeline.py:44`),
  so nothing persists on disk between runs by default.
- If/when the pipeline is parallelised, this becomes mandatory, not optional.

### §4 — Add a wall-clock cap with a hard kill, and a spend ceiling

- **Per-run wall-clock timeout.** Simplest: in `evals/pipeline.py::run_one`,
  run `agent.run(task)` in a worker thread and `join(timeout=RUN_TIMEOUT)`;
  on expiry, call `s.destroy()` immediately (that is the SIGKILL — `docker
  rm -f`, `src/harness/sandbox.py:44`) and record the run as `timed_out`.
  Add `run_timeout: int` to `Settings` (`src/harness/config.py`), default e.g.
  3600, and a `--run-timeout` CLI flag in `scripts/run_eval.py`.
  A thread is needed because `Agent.run` is a synchronous loop with no
  cancellation point; alternatively add a deadline check at the top of the
  `for` loop in `src/harness/agent.py:52` (`if time.monotonic() > deadline:
  return "timeout"`), but that only fires between LLM calls, so still pair it
  with the destroy-based hard kill for a wedged HTTP call.
- **Kill the in-container process on command timeout.** In
  `src/harness/sandbox.py:32–41`, wrap the remote command so the container
  side enforces the limit: invoke `bash -lc "timeout -s KILL {t} {command}"`
  (the `coreutils` `timeout`, present in `python:3.12-slim`), or on
  `TimeoutExpired` issue `docker exec {name} pkill -KILL -P 1` / restart the
  container. Today the `except` branch (`:40–41`) only returns a string.
- **Token / cost ceiling.** In `src/harness/agent.py` `run` loop, after
  updating `self.usage` (around `:60–67`), `break`/return if
  `self.usage.prompt + self.usage.completion` exceeds a configured
  `max_tokens`, or `self.usage.calls` exceeds a `max_tool_calls`. Add the
  fields to `Settings`. Document the precedence explicitly (e.g. wall-clock >
  token budget > `max_turns`).
- **Unify `max_turns`.** `run.py:13` hard-codes 50 while `config` default is
  20 and `scripts/run_eval.py` uses the config value. Pick one source
  (`settings.max_turns`) so experiment runs and interactive runs match.
