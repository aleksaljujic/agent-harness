# Docs

| Folder | Contents |
|---|---|
| [`agent/`](agent/) | How the harness is built — the agent loop, sandbox, tools, design decisions. |
| [`swebench/`](swebench/) | SWE-bench Lite integration — CLI, dataset, result-row schema, smoke test. |
| [`todo/`](todo/) | Incident/investigation log. |
| [`media/`](media/) | Architecture diagrams and demo recordings. |

## agent/
- [`NOTES.md`](agent/NOTES.md) — building a coding-agent harness: the loop, the sandbox boundary, tools, what held up in practice.
- [`TOOLS.md`](agent/TOOLS.md) — the tool surface.

## swebench/
- [`SWEBENCH_INTEGRATION_STATUS.md`](swebench/SWEBENCH_INTEGRATION_STATUS.md) — what exists vs. what's missing to run SWE-bench Lite; recommended split (harness → predictions, official `swebench` → scoring); task checklist.
- [`SMOKE_TEST_EXAMPLE.md`](swebench/SMOKE_TEST_EXAMPLE.md) — one-instance end-to-end walkthrough (checkout → agent → diff → evaluator → `resolved`), with exit criteria.
- [`CLI.md`](swebench/CLI.md) — `scripts/run_swebench.py` — svaki flag, instance-selection modovi, primeri, i šta se piše u `artifacts/swebench/`.
- [`DATASET.md`](swebench/DATASET.md) — struktura SWE-bench Lite dataseta: splitovi (dev/test), poreklo instanci, značenje svake kolone.
- [`METRICS_SWE.md`](swebench/METRICS_SWE.md) — field-by-field objašnjenje sirovog reda iz `artifacts/swebench/` i razlike u odnosu na stari `evals` runner.

## todo/
- [`ISSUES.md`](todo/ISSUES.md) — root-caused bugs, open questions, what's still being chased.

## media/
- `arhitektura.png`, `petlja.png`, `tok_eksperimenta.png` — diagrams (sources in `diagrams/`).
- `demo.webm` — harness demo recording.
- `snapshot.mp4` — placeholder (empty).
