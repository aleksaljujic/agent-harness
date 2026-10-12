# Agent harness

A minimal coding agent. Three tools — `bash`, `search`, `str_replace` — running
inside a disposable Docker container.

https://github.com/user-attachments/assets/006438bd-3239-48da-8a95-3151aae8efde

## BSc thesis: tool ablation on SWE-bench Lite

This harness was built for my BSc thesis at the Faculty of Organizational Sciences, University of Belgrade (2026): *Evaluation of LLM-based agents for solving software engineering problems*. The question was how much each tool actually contributes to success and cost when the model is fixed.

**Setup.** All 300 SWE-bench Lite tasks, gpt-5.4-nano at temperature 0, every run in an isolated Docker container. A 2x2 factorial design toggled `str_replace` and a search/read tool group, with `bash` available in every condition. Primary measures were resolve rate, cost per resolved task and fault localization (whether the agent edited the right file). Conditions were compared with paired bootstrap confidence intervals, McNemar tests and a non-inferiority analysis.

| Condition | Tools | Resolved (of 299) | Cost per run | Cost per resolved task | Localization |
|---|---|---|---|---|---|
| A | bash | 111 (37.1%) | $0.0208 | $0.0561 | 78.3% |
| B | bash + str_replace | **119 (39.8%)** | $0.0232 | $0.0583 | 77.6% |
| C | bash + search/read | 112 (37.5%) | $0.0365 | $0.0974 | 77.3% |
| D | all tools | 99 (33.1%) | $0.0272 | $0.0821 | 76.6% |

**Findings**

- **A smaller tool set made a better agent.** bash + str_replace resolved 6.7 percentage points more tasks than the full tool set (95% CI [+2.0, +11.4]) at a lower cost per resolved task.
- **Search tools added cost without better localization.** They used about 1.5x more input tokens, while the change in localization was not significant (-1.0 pp, 95% CI [-4.3, +2.3]).
- **Cost is driven by input tokens, not edit size.** Input tokens made up over 90% of cost, so str_replace saved money mainly by shortening trajectories, and only in conditions with search tools.
- **Harness bugs can look like model effects.** Fixing a single tool defect moved condition D from 28.0% to 33.1% resolved and changed the outcome of one hypothesis.

Costs are computed from list prices without prompt-caching discounts, so they are an upper bound. Each condition was run once.

Full thesis (in Serbian): [docs/thesis/BSc_thesis_tool_ablation.pdf](docs/thesis/BSc_thesis_tool_ablation.pdf). The code in this repository has changed since the thesis runs, so the current tool set may differ from the one evaluated.

## Setup

Requires Docker, Python 3.12+, [uv](https://docs.astral.sh/uv/), and an Azure OpenAI
deployment.

```bash
uv sync
docker build -t agent-sandbox .
cp .env.example .env
```

Fill in `.env`:

```
ENDPOINT=https://your-resource.services.ai.azure.com/openai/v1
API_KEY=your-key
DEPLOYMENT=your-deployment-name
```

`AZURE_OPENAI_DEPLOYMENT` is the deployment name from the Azure portal, not the model
name.

## Run

```bash
uv run run.py
```

Run from the project root. Type `exit` to quit.

```
prompt: Make a CLI todo app in Python and test it
[bash] cd /work && cat > todo.py <<'PY'
...
[edit] todo.py -> OK: replaced in todo.py

In 6 calls | Tokens: 11,573 in | 330 out | Cost: $0.000711
```

Files land in `workspace/`. Each prompt continues the same conversation, so follow-ups
work: `now add priorities to tasks`.

## Options

| Variable | Default | |
|---|---|---|
| `MAX_TURNS` | 20 | Max agent steps per task |
| `TIMEOUT` | 60 | Seconds before a command is killed |
| `WORKSPACE` | `./workspace` | Directory mounted into the container |

```bash
WORKSPACE=~/projects/my-repo MAX_TURNS=50 uv run run.py
```

Commit before pointing it at a real project — the agent edits files in place.

## Evals

```bash
uv run evals/evals.py       # run the task set
uv run view_runs.py fail    # read transcripts of failures
```

## Layout

```
run.py          CLI entry point
config.py       Settings from .env
sandbox.py      Docker container lifecycle
agent.py        The loop
tools.py        Tool schemas
utils.py        Tool implementations
prompt.py       System prompt
scripts/        Helpers mounted read-only into the container
```

See [NOTES.md](docs/agent/NOTES.md) for design decisions and what was learned building it.
