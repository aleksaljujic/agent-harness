# Metrics Schema — Tool-Ablation Experiment on SWE-bench Lite

Purpose: define the per-run result row and the aggregate metrics for the
experiment "does giving the agent more tools (`bash` → `bash+search` →
`bash+search+str_replace+…`) change the SWE-bench Lite resolve rate, and at what
cost."

Reference input record (what is currently emitted):

```json
{
  "model": "gpt-5.4-nano", "toolset_condition": "minimal",
  "session_id": "gpt-5.4-nano__bash", "task": "hello", "task_id": "hello",
  "run_index": 0, "uses_bash": true, "uses_search": false, "uses_str_replace": false,
  "ok": true, "crashed": false, "error_type": "", "termination_reason": "completed",
  "tests_fail_to_pass_total": 0, "tests_fail_to_pass_passed": 0,
  "tests_pass_to_pass_total": 0, "tests_pass_to_pass_passed": 0,
  "prompt_tokens": 1138, "completion_tokens": 102, "reasoning_tokens": 0,
  "total_tokens": 1240, "calls": 3,
  "tool_calls_breakdown": {"bash": 3}, "tool_call_errors": {"bash": 0},
  "error_recovery": false, "cost": 0.0003551, "wall_time": 4.82,
  "temperature": 0, "reasoning_effort": null, "ts": 1787697505.83
}
```

---

## 1. Per-run row — final schema

One row per `(model, toolset, instance, run_index)`.

### 1.1 Identity / grouping keys

| Field | Type | Source | Note |
|---|---|---|---|
| `run_id` | str | harness | unique per row, e.g. `<session_id>/<instance_id>/<run_index>` |
| `session_id` | str | harness | `"<model>__<tools-slug>"`; convenience, derivable |
| `model` | str | config | |
| `tools` | list[str] | config | explicit enabled tools, e.g. `["bash","search"]` |
| `toolset_condition` | str | config | human label: `minimal` / `bash_search` / `full` |
| `instance_id` | str | dataset | SWE-bench `instance_id` (rename `task_id` → this) |
| `repo` | str | dataset | e.g. `astropy/astropy` — enables per-project slicing |
| `run_index` | int | harness | repeat number, `0..repeats-1` |

Drop: `task` (duplicate of `task_id`), and keep **either** `tools` **or** the
`uses_bash` / `uses_search` / `uses_str_replace` booleans — not both.

### 1.2 Primary outcome

| Field | Type | Definition |
|---|---|---|
| `tests_fail_to_pass_total` | int | count of `FAIL_TO_PASS` node-ids |
| `tests_fail_to_pass_passed` | int | how many passed after the agent's patch + gold `test_patch` |
| `tests_pass_to_pass_total` | int | count of `PASS_TO_PASS` node-ids |
| `tests_pass_to_pass_passed` | int | how many still passed |
| **`resolved`** | bool | `f2p_passed == f2p_total and p2p_passed == p2p_total` — **the headline metric** |
| **`empty_patch`** | bool | agent produced no diff |
| **`patch_applied`** | bool | the agent diff applied cleanly before testing |
| `patch_files_changed` | int | size signal |
| `patch_lines_changed` | int | size signal (added + removed) |

`ok` — keep only if toy tasks share this pipeline; for SWE-bench it must equal
`resolved`.

### 1.3 Cost / efficiency (secondary outcomes)

| Field | Type | Note |
|---|---|---|
| `prompt_tokens` | int | |
| `completion_tokens` | int | |
| `reasoning_tokens` | int | 0 for models without visible reasoning; keep for cross-model compare |
| `cost` | float | USD, from `MODEL_PRICING` |
| `wall_time` | float | seconds, per run |
| `calls` | int | LLM completions |

Drop `total_tokens` — derive as `prompt + completion (+ reasoning)`.

### 1.4 Failure taxonomy

| Field | Type | Values / definition |
|---|---|---|
| `crashed` | bool | harness raised |
| `error_type` | str | exception class name, else `""` |
| `termination_reason` | str | `completed` \| `max_turns` \| `wall_timeout` \| `token_budget` \| `crash` \| `empty_patch` \| `apply_failed` |
| `turns_used` | int | LLM turns consumed |
| `max_turns` | int | cap in effect (log even though constant) |

### 1.5 Tool behaviour (the ablation signal)

| Field | Type | Note |
|---|---|---|
| `tool_calls_breakdown` | dict[str,int] | calls per tool name |
| `tool_call_errors` | dict[str,int] | error results per tool name |
| `error_recovery` | bool | keep only with a precise definition: a failing tool call followed by a later successful call to the *same* tool in the same run; else drop |

### 1.6 Provenance (constant per session, still logged per row)

| Field | Type | Note |
|---|---|---|
| `temperature` | float | |
| `reasoning_effort` | str \| null | |
| `harness_sha` | str | `git rev-parse HEAD` of this repo at run time |
| `dataset` | str | `SWE-bench/SWE-bench_Lite` |
| `split` | str | `test` |
| `eval_image` | str | swebench image id/tag used for grading |
| `network` | str | sandbox network policy in effect (`none` / …) |
| `ts` | float | unix time |

---

## 2. Aggregate metrics

Computed by grouping rows on `(model, toolset_condition)` unless noted.

| # | Metric | Formula | Purpose |
|---|---|---|---|
| 1 | **% Resolved (pass@1)** | `mean(resolved)` over all `(instance, run_index)` | headline score per condition |
| 2 | **% Resolved (pass@k / pass^k)** | per instance over `run_index`: `pass@k` = resolved in ≥1 of k; `pass^k` = resolved in all k | stability under repeats |
| 3 | **Δ resolve rate** | `resolved_rate(cond_B) − resolved_rate(cond_A)`, paired by `instance_id`, with a significance test (McNemar / bootstrap CI) | the thesis claim |
| 4 | **Cost per resolved instance** | `sum(cost) / count(resolved)` | efficiency of the extra tools |
| 5 | **Mean tokens / calls / wall_time** | mean of each per condition | overhead of the extra tools |
| 6 | **Failure breakdown** | share of runs by `termination_reason` | where runs die |
| 7 | **Empty-patch rate** | `mean(empty_patch)` | "did nothing" vs "tried and failed" |
| 8 | **Crash rate** | `mean(crashed)` | harness stability per condition |
| 9 | **Tool-usage profile** | per tool: mean `tool_calls_breakdown[t]`, error rate `tool_call_errors[t] / tool_calls_breakdown[t]` | how the added tools are actually used |
| 10 | **Resolve rate by repo** | metric 1 grouped by `repo` | which projects drive the difference |

Reporting: for every rate, give N and a 95% CI (Wilson for proportions,
bootstrap for ratios like #4). Fix `run_index` count (`repeats`) across all
conditions so comparisons are paired.

---

## 3. Minimal vs full field set

- **Minimal** (can still compute metrics 1, 4, 5, 6): `instance_id`, `repo`,
  `model`, `toolset_condition`, `run_index`, `resolved`, `empty_patch`,
  `termination_reason`, `prompt_tokens`, `completion_tokens`, `cost`,
  `wall_time`, `calls`.
- **Full**: everything in §1 — needed for pass^k (#2), tool-usage profile (#9),
  and failure diagnosis.
