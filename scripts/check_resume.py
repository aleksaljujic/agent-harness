"""Dry-run check for `run_swebench.py --resume`: would this command re-run anything?

Takes the exact flags you intend to pass to run_swebench.py and reports, without
touching the API, Docker, or any file, which run_ids the pipeline would consider
already done vs. newly executed. Use it before a resume whose only purpose is
grading — a mismatched --combo/--limit silently turns a free grading pass into
thousands of fresh agent runs.

Mirrors pipeline.py: instances come from `load_instances`, combos from
`all_tool_combinations` when --combo is absent, and the run key is
`make_session_id(model, tools)/<instance_id>/<run_index>` (pipeline.py:368,380).

    python scripts/check_resume.py --resume artifacts/swebench/experiments/<exp_id> \
        --limit 300 --combo bash --combo bash,str_replace
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from evals.evals import make_session_id
from evals.pipeline import all_tool_combinations
from evals.swebench.steps.dataset import load_instances
from scripts.run_swebench import build_arg_parser


def main() -> None:
    p = build_arg_parser()
    p.prog = "check_resume.py"
    args = p.parse_args()
    if not args.resume:
        raise SystemExit("--resume EXP_DIR is required — there is nothing to check without it")

    exp_root = Path(args.resume).resolve()
    rows_path = exp_root / "rows.jsonl"
    if not rows_path.exists():
        raise SystemExit(f"no rows.jsonl in {exp_root}")

    rows = [json.loads(l) for l in rows_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    done = {r["run_id"]: r for r in rows}

    instances = load_instances(split=args.split, ids=args.instances, limit=args.limit,
                               repos=args.repos, sample=args.sample, seed=args.seed)
    if not instances:
        raise SystemExit("no instances matched the selection")
    combos = args.combos or all_tool_combinations(args.tools, ("bash",))

    expected, per_session = [], {}
    for tools in combos:
        sid = make_session_id(args.model, tools)
        keys = [f"{sid}/{i['instance_id']}/{r}"
                for i in instances for r in range(args.repeats)]
        per_session[sid] = keys
        expected.extend(keys)

    hit = [k for k in expected if k in done]
    miss = [k for k in expected if k not in done]
    orphan = [k for k in done if k not in set(expected)]

    print(f"experiment : {exp_root.name}")
    print(f"rows.jsonl : {len(rows)} row(s)")
    print(f"selection  : {len(instances)} instance(s) × {len(combos)} combo(s) "
          f"× {args.repeats} repeat(s) = {len(expected)} expected run(s)\n")

    print(f"{'session_id':<58} {'exp':>5} {'done':>5} {'RERUN':>6} {'preds':>6}")
    for sid, keys in per_session.items():
        d = sum(1 for k in keys if k in done)
        preds_file = exp_root / "predictions" / f"{sid}.jsonl"
        n_preds = (len([l for l in preds_file.read_text(encoding="utf-8").splitlines() if l.strip()])
                   if preds_file.exists() else -1)
        print(f"{sid:<58} {len(keys):>5} {d:>5} {len(keys) - d:>6} "
              f"{(n_preds if n_preds >= 0 else 'MISSING'):>6}")

    print(f"\nalready done : {len(hit)}")
    print(f"WOULD RE-RUN : {len(miss)}", end="")
    if miss:
        cost = sum(r.get("cost", 0.0) for r in rows) / max(len(rows), 1) * len(miss)
        secs = sum(r.get("wall_time", 0.0) for r in rows) / max(len(rows), 1) * len(miss)
        print(f"   (~{secs / 3600:.1f}h, ~${cost:.2f} at this experiment's observed averages)")
        for sid, n in Counter(k.split("/", 1)[0] for k in miss).most_common():
            print(f"    {n:>5}  {sid}")
    else:
        print()
    if orphan:
        print(f"\nrows not covered by this selection: {len(orphan)} "
              "(they stay in rows.jsonl but this command would not grade them)")
        for sid, n in Counter(k.split("/", 1)[0] for k in orphan).most_common():
            print(f"    {n:>5}  {sid}")

    graded = sum(1 for k in hit if not done[k].get("grade_error", "")
                 and done[k].get("tests_pass_to_pass_total", 0) > 0)
    print(f"\nalready carry a grader verdict: {graded}/{len(hit)}")

    if miss:
        print("\nNOT SAFE as a grading-only pass — fix the flags until WOULD RE-RUN is 0.")
        sys.exit(1)
    print("\nSAFE: every expected run is already recorded; the resume would go straight to grading.")


if __name__ == "__main__":
    main()
