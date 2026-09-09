# Smoke Test — One SWE-bench Lite Instance, End to End

Goal: prove the full path works for **one** instance before building the adapter
or the eval matrix:

```
checkout base_commit  →  run agent on problem_statement  →  extract git diff
    →  predictions.jsonl  →  official swebench evaluator  →  resolved: true/false
```

This de-risks the parts that can sink the approach (does the official harness run
here, does the agent's diff apply, disk/time cost). It is throwaway — do not
wire it into `evals/pipeline.py` yet.

---

## 0. Prerequisites

- Docker running, `docker run hello-world` works.
- **Disk:** the official evaluator pulls/builds a per-instance image (~1–2 GB
  each) plus a shared base (~several GB). Have ~20 GB free.
- `swebench` installed in the venv:
  ```bash
  uv add --group dev swebench
  ```
- `.env` filled in (`ENDPOINT`, `API_KEY`, `MODEL`, `PROVIDER`) — same as a
  normal harness run.
- Sandbox image built: `docker build -t agent-sandbox .`

> Note: `agent-sandbox` is `python:3.12-slim + pytest` — it will **not** have
> `astropy` / `django` / etc. installed. That is fine for the smoke test: the
> agent only needs to read code and emit a diff. Test execution and grading
> happen later inside the official swebench image, not here.

---

## 1. Pick the instance

Use an easy one. From `df_swe` (`difficulty == "<15 min fix"`), e.g.:

```
instance_id  = astropy__astropy-14995
repo         = astropy/astropy
base_commit  = b16c7d12ccbc7b2d20364b89fb44285bcbfede54
```

Pull its row so you have `problem_statement`, `FAIL_TO_PASS`, `PASS_TO_PASS`
on hand (the evaluator reads these from the dataset itself — you only need
`problem_statement` for the agent):

```python
import pandas as pd
splits = {"test": "data/test-00000-of-00001.parquet"}
df = pd.read_parquet("hf://datasets/SWE-bench/SWE-bench_Lite/" + splits["test"])
row = df[df.instance_id == "astropy__astropy-14995"].iloc[0]
print(row["problem_statement"])
```

---

## 2. Check out the repo at `base_commit` (host side)

Into the directory that will become the sandbox's `/work`. Re-init git so the
agent's diff is clean and upstream history is not visible.

```bash
INSTANCE=astropy__astropy-14995
REPO=astropy/astropy
BASE=b16c7d12ccbc7b2d20364b89fb44285bcbfede54

WORK=$(pwd)/smoke/$INSTANCE
rm -rf "$WORK" && mkdir -p "$WORK"

git clone https://github.com/$REPO "$WORK"
git -C "$WORK" checkout --quiet "$BASE"

# strip upstream history + remotes, keep a base commit to diff against
rm -rf "$WORK/.git"
git -C "$WORK" init -q
git -C "$WORK" add -A
git -C "$WORK" -c user.email=smoke@test -c user.name=smoke commit -qm base

# sanity
test "$(git -C "$WORK" log --oneline | wc -l)" = "1" && echo "history stripped OK"
test -z "$(git -C "$WORK" remote)" && echo "no remotes OK"
```

---

## 3. Run the agent on `problem_statement`

`run.py` is interactive; write a tiny throwaway script instead. It reuses
`Sandbox` + `Agent` as-is.

`smoke_run.py` (put at repo root, delete afterwards):

```python
import sys
from pathlib import Path
from harness.sandbox import Sandbox
from harness.agent import Agent

work = Path(sys.argv[1]).resolve()          # smoke/<instance_id>
problem = Path(sys.argv[2]).read_text()     # problem_statement saved to a file

SYSTEM = (
    "You are a software engineer fixing a bug in an existing repository already "
    "checked out at /work. Investigate with your tools, then make the minimal "
    "code change that resolves the issue. Do not edit or add tests."
)

s = Sandbox(work)
try:
    agent = Agent(s, tools=["bash", "search", "str_replace", "read_file", "find_file"],
                  system_promt=SYSTEM, max_turns=40)
    answer = agent.run(problem)
    print(answer)
    u = agent.usage
    print(f"\n[{u.calls} calls · {u.prompt} in · {u.completion} out · ${u.cost:.4f}]")
finally:
    s.destroy()
```

Run it:

```bash
python -c "
import pandas as pd
splits={'test':'data/test-00000-of-00001.parquet'}
df=pd.read_parquet('hf://datasets/SWE-bench/SWE-bench_Lite/'+splits['test'])
open('smoke/$INSTANCE.problem.txt','w').write(
    df[df.instance_id=='$INSTANCE'].iloc[0]['problem_statement'])
"
python smoke_run.py "smoke/$INSTANCE" "smoke/$INSTANCE.problem.txt"
```

> `run_tests` is left out of the toolset on purpose — the deps aren't installed
> in `agent-sandbox`, so it would only produce noise. Add it back once the agent
> runs inside the real swebench env.

---

## 4. Extract the prediction diff

```bash
git -C "$WORK" add -A
git -C "$WORK" diff --cached HEAD > "smoke/$INSTANCE.patch"

# must be non-empty and must apply cleanly
test -s "smoke/$INSTANCE.patch" && echo "non-empty patch OK"
git -C "$WORK" apply --check "smoke/$INSTANCE.patch" && echo "applies OK"
```

Write `predictions.jsonl` (one line):

```bash
python -c "
import json
patch = open('smoke/$INSTANCE.patch').read()
rec = {'instance_id': '$INSTANCE',
       'model_name_or_path': 'smoke-$(git rev-parse --short HEAD)',
       'model_patch': patch}
open('smoke/predictions.jsonl','w').write(json.dumps(rec) + '\n')
"
```

---

## 5. Run the official evaluator

```bash
python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Lite \
    --predictions_path smoke/predictions.jsonl \
    --max_workers 1 \
    --run_id smoke_$INSTANCE
```

First run is slow (image build/pull). It writes a report JSON in the CWD, e.g.
`smoke-<sha>.smoke_<instance>.json`.

---

## 6. Read the result

```bash
cat smoke-*.smoke_$INSTANCE.json
```

Look for:

```json
{
  "resolved_instances": 1,
  "resolved_ids": ["astropy__astropy-14995"],
  ...
}
```

`resolved` for this instance = `instance_id in resolved_ids`.
Per-instance detail (F2P / P2P breakdown) is under
`logs/run_evaluation/smoke_<instance>/…/report.json`.

---

## 7. Exit criteria

The smoke test **passes as an integration check** (regardless of whether the
instance is `resolved`) when:

- [ ] repo checked out at `base_commit`, history stripped (§2 sanity lines print OK)
- [ ] agent ran to completion without a harness crash
- [ ] `smoke/<instance>.patch` is non-empty and `git apply --check` passes
- [ ] official evaluator ran and produced a report JSON
- [ ] the report has an unambiguous resolved / not-resolved for the instance

Record for the real run planning: wall-clock of §3, wall-clock + disk of §5,
token cost of §3.

If `resolved: true` on the first easy instance — the whole path works, move to
the adapter (`SWEBENCH_INTEGRATION_STATUS.md` §2.1). If `false`, inspect the
patch and the `report.json` test output to see whether it's an agent miss
(fine, expected sometimes) or a harness/plumbing bug (checkout wrong, diff
malformed, wrong instance).

---

## 8. Cleanup

```bash
rm -rf smoke/ smoke_run.py
docker image prune -f      # optional; the swebench instance images are large
```
