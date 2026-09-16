# Agent harness

A minimal coding agent. Three tools — `bash`, `search`, `str_replace` — running
inside a disposable Docker container.

https://github.com/user-attachments/assets/006438bd-3239-48da-8a95-3151aae8efde

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
