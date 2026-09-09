# Docs

| Folder | Contents |
|---|---|
| [`agent/`](agent/) | How the harness is built — the agent loop, sandbox, tools, design decisions. |
| [`evals/`](evals/) | The eval framework and its results on the toy-task suite. |
| [`swebench/`](swebench/) | SWE-bench Lite integration — status, plan, metrics schema, smoke test. |
| [`research/`](research/) | Thesis background: tool-surface literature review, session transcript. |
| [`media/`](media/) | Demo recordings. |

## agent/
- [`NOTES.md`](agent/NOTES.md) — building a coding-agent harness: the loop, the sandbox boundary, tools, what held up in practice.

## evals/
- [`EVALS.md`](evals/EVALS.md) — eval report for `gpt-5.4-nano` across tool variants on the 12 toy tasks (directional, repeats=1). *(git-ignored)*
- [`REPORT.md`](evals/REPORT.md) — placeholder.

## swebench/
- [`SWEBENCH_INTEGRATION_STATUS.md`](swebench/SWEBENCH_INTEGRATION_STATUS.md) — what exists vs. what's missing to run SWE-bench Lite; recommended split (harness → predictions, official `swebench` → scoring); task checklist.
- [`SMOKE_TEST_EXAMPLE.md`](swebench/SMOKE_TEST_EXAMPLE.md) — one-instance end-to-end walkthrough (checkout → agent → diff → evaluator → `resolved`), with exit criteria.
- [`METRICS.md`](swebench/METRICS.md) — per-run result-row schema and the aggregate metrics for the tool-ablation experiment.
- [`AUDIT_REPORT.md`](swebench/AUDIT_REPORT.md) — static integrity audit of the harness against the SWE-bench protocol (test-patch timing, git-history exposure, isolation, timeouts).

## research/
- [`reference_research.md`](research/reference_research.md) — tool-surface ablation literature (Yang et al. + the 2025–2026 field), framed for the thesis.
- [`REZIME.md`](research/REZIME.md) — full development-session transcript, by phase (Serbian).

## media/
- `demo.webm` — harness demo recording.
- `snapshot.mp4` — placeholder (empty).
