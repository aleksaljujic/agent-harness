"""Configuration for the SWE-bench evaluation.

Kept separate from `harness.config` on purpose: this is evaluation logic, not
part of the agent runtime. Env overrides use the `SWEBENCH_` prefix
(e.g. `SWEBENCH_SEED=42`, `SWEBENCH_GRADE_MAX_WORKERS=2`).
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from harness.config import ROOT

# --- structural constants (not tunable) ---
DATASET = "SWE-bench/SWE-bench_Lite"
INSTANCE_FIELDS = (
    "instance_id", "repo", "base_commit", "problem_statement", "version", "image",
)
REPO_CACHE_DIR = Path.home() / ".cache" / "agent-harness" / "repos"
# v1 runs "blind" in agent-sandbox (no repo deps) → run_tests is not offered here
TOOL_UNIVERSE = ("bash", "search", "str_replace", "read_file", "find_file")
REASONING_LEVELS = ("minimal", "low", "medium", "high")


class SweBenchSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_prefix="SWEBENCH_", extra="ignore"
    )

    split: str = "test"
    seed: int = 0                       # default RNG seed for --sample
    repeats: int = 1
    max_turns: int = 40
    run_timeout: int = 1800             # wall-clock seconds per instance run
    grade_max_workers: int = 4          # parallelism for the official evaluator
    sandbox_network: str = "none"       # agent sandbox network policy (none = no internet)


swe_settings = SweBenchSettings()
