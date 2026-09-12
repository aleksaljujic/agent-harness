import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from evals.swebench.config import REASONING_LEVELS, swe_settings
from evals.swebench.pipeline import DEFAULT_TOOLS, run_pipeline
from evals.swebench.steps.dataset import load_instances
from evals.swebench.summary import summarize

DEFAULT_MODEL = "gpt-5.4-nano"


def _csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the agent on SWE-bench Lite and grade the patches.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--split", default=swe_settings.split)
    p.add_argument("--name", default=None, help="experiment name; folder is <timestamp>_<name|model>")

    sel = p.add_argument_group("instance selection")
    sel.add_argument("--instances", type=_csv, default=None, help="explicit instance_ids, comma-separated")
    sel.add_argument("--repos", type=_csv, default=None, help="filter to these repos, comma-separated")
    sel.add_argument("--limit", type=int, default=None, help="take the first N (after sorting by id)")
    sel.add_argument("--sample", type=int, default=None, help="take N at random (see --seed); excludes --limit")
    sel.add_argument("--seed", type=int, default=swe_settings.seed,
                     help=f"RNG seed for --sample (default {swe_settings.seed})")

    tg = p.add_argument_group("toolsets")
    tg.add_argument("--tools", nargs="+", default=DEFAULT_TOOLS,
                    help=f"tool universe for auto-generated combos (default: {DEFAULT_TOOLS})")
    tg.add_argument("--combo", action="append", type=_csv, dest="combos",
                    help="explicit tool combo, comma-separated; repeatable; bypasses --tools")

    p.add_argument("--reasoning-effort", choices=list(REASONING_LEVELS), default=None,
                   help="enable model reasoning at this effort level")
    p.add_argument("--repeats", type=int, default=swe_settings.repeats)
    p.add_argument("--max-turns", type=int, default=None,
                   help=f"per run (default {swe_settings.max_turns})")
    p.add_argument("--run-timeout", type=int, default=None,
                   help=f"wall-clock seconds per instance run (default {swe_settings.run_timeout})")
    p.add_argument("--max-workers", type=int, default=swe_settings.grade_max_workers,
                   help="parallelism for the swebench evaluator")
    p.add_argument("--no-grade", action="store_true", help="produce predictions only, skip evaluation")
    p.add_argument("--artifacts-dir", default=str(ROOT / "artifacts"))
    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    instances = load_instances(
        split=args.split, ids=args.instances, limit=args.limit, repos=args.repos,
        sample=args.sample, seed=args.seed)
    if not instances:
        raise SystemExit("no instances matched the selection")
    print(f"{len(instances)} instance(s): {', '.join(i['instance_id'] for i in instances)}")

    selection = {"split": args.split, "instances": args.instances, "repos": args.repos,
                 "limit": args.limit, "sample": args.sample, "seed": args.seed}

    exp_root, csv_path, rows_json, rows = run_pipeline(
        model=args.model,
        instances=instances,
        tool_combos=args.combos,
        tool_universe=args.tools,
        repeats=args.repeats,
        artifacts_dir=args.artifacts_dir,
        name=args.name,
        max_turns=args.max_turns,
        run_timeout=args.run_timeout,
        max_workers=args.max_workers,
        grade_enabled=not args.no_grade,
        reasoning_effort=args.reasoning_effort,
        selection=selection,
    )

    summarize(rows)
    print(f"\nexperiment: {exp_root}")
    print(f"  rows.csv     {csv_path}")
    print(f"  rows.jsonl   {rows_json}")
    print(f"  manifest     {exp_root / 'manifest.json'}")
    print(f"  ledger       {Path(args.artifacts_dir) / 'swebench' / 'MANIFEST.jsonl'}")


if __name__ == "__main__":
    main()
