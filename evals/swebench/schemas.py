"""Typed shapes for SWE-bench eval output.

`RunRow` is the per-run record — the single source of truth for the CSV / JSONL
columns described in docs/swebench/METRICS_SWE.md. `PatchInfo` is what
`predict.extract` returns. The manifest / ledger / rollup dicts stay plain:
they are assembled once and serialized immediately.
"""
import json
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field

# outcome fields the grader backfills onto a RunRow after the agent has run
GRADE_FIELDS = (
    "resolved",
    "tests_fail_to_pass_total", "tests_fail_to_pass_passed",
    "tests_pass_to_pass_total", "tests_pass_to_pass_passed",
    "eval_image", "grade_error",
)


class Prediction(TypedDict):
    """One line of the official SWE-bench predictions.jsonl."""
    instance_id: str
    model_name_or_path: str
    model_patch: str


class PatchInfo(BaseModel):
    """Result of diffing the agent's working tree against the base commit."""
    model_patch: str = ""
    empty_patch: bool = True
    patch_applied: bool = False
    patch_files_changed: int = 0
    patch_lines_changed: int = 0


class RunRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # identity
    run_id: str
    session_id: str
    model: str
    tools: str
    toolset_condition: str
    instance_id: str
    repo: str
    run_index: int

    # outcome — GRADE_FIELDS are filled in later by grade.grade()
    tests_fail_to_pass_total: int = 0
    tests_fail_to_pass_passed: int = 0
    tests_pass_to_pass_total: int = 0
    tests_pass_to_pass_passed: int = 0
    resolved: bool = False
    # why the evaluator produced no verdict; "" when it actually graded.
    # Without this a never-graded run is indistinguishable from a failed one.
    grade_error: str = ""
    empty_patch: bool = True
    patch_applied: bool = False
    patch_files_changed: int = 0
    patch_lines_changed: int = 0

    # cost
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    wall_time: float = 0.0
    llm_seconds: float = 0.0
    tool_seconds: float = 0.0
    calls: int = 0

    # failure
    crashed: bool = False
    error_type: str = ""
    error_message: str = ""
    termination_reason: str = "unstarted"
    turns_used: int = 0
    max_turns: int = 0

    # tools
    tool_calls_breakdown: dict[str, int] = Field(default_factory=dict)
    tool_call_errors: dict[str, int] = Field(default_factory=dict)

    # provenance
    temperature: float = 0.0
    reasoning_effort: str = ""
    harness_sha: str = ""
    dataset: str = ""
    split: str = ""
    eval_image: str = ""
    network: str = ""
    ts: float = 0.0

    def csv_row(self) -> dict:
        """model_dump() with the dict-valued columns flattened to JSON strings."""
        d = self.model_dump()
        d["tool_calls_breakdown"] = json.dumps(d["tool_calls_breakdown"])
        d["tool_call_errors"] = json.dumps(d["tool_call_errors"])
        return d
