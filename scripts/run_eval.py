import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))  # scripts/ isn't on sys.path when run directly; evals/ lives at the project root

from evals.pipeline import run_pipeline
from evals.tasks import SEEDS1, SEEDS2, TASKS1, TASKS2
from harness.config import settings

DEFAULT_MODEL = "gpt-5.4-nano"
DEFAULT_TOOLS = ["bash", "search", "str_replace"]


def parse_combo(value):
    return [t.strip() for t in value.split(",") if t.strip()]


def build_arg_parser():
    p = argparse.ArgumentParser(description="Run harness evals across tool combinations and tasks.")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"model name (default: {DEFAULT_MODEL})")
    p.add_argument("--repeats", type=int, default=3, help="repeats per (combo, task) pair (default: 3)")
    p.add_argument("--tools", nargs="+", default=DEFAULT_TOOLS,
                    help=f"tool universe to auto-generate combinations from (default: {DEFAULT_TOOLS})")
    p.add_argument("--combo", action="append", type=parse_combo, dest="combos",
                    help="explicit tool combo, comma-separated (e.g. --combo bash,search). "
                         "Repeatable. When given, bypasses auto-generation from --tools entirely.")
    p.add_argument("--require", nargs="+", default=["bash"],
                    help="tools required in every auto-generated combo (ignored when --combo is used)")
    p.add_argument("--task-set", choices=["1", "2", "all"], default="all",
                    help="which task set to run (default: all)")
    p.add_argument("--max-turns", type=int, default=None,
                    help=f"max agent turns per run (default: settings.max_turns={settings.max_turns})")
    p.add_argument("--artifacts-dir", default=str(ROOT / "artifacts"),
                    help="directory to write runs_eval_<timestamp>.{json,csv} into")
    return p


def resolve_tasks(task_set):
    if task_set == "1":
        return list(TASKS1), dict(SEEDS1)
    if task_set == "2":
        return list(TASKS2), dict(SEEDS2)
    return list(TASKS1) + list(TASKS2), {**SEEDS1, **SEEDS2}


def main():
    args = build_arg_parser().parse_args()
    tasks, seeds = resolve_tasks(args.task_set)

    json_path, csv_path, md_path, rows = run_pipeline(
        model=args.model,
        tool_universe=args.tools,
        repeats=args.repeats,
        tasks=tasks,
        seeds=seeds,
        artifacts_dir=args.artifacts_dir,
        required_tools=args.require,
        combos=args.combos,
        max_turns=args.max_turns,
    )

    print(f"\nDone. {len(rows)} runs.")
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print(f"MD:   {md_path}")


if __name__ == "__main__":
    main()
