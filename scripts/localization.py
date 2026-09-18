"""File-level localization: does the agent's patch touch a file the gold patch touches?

Post-hoc, no new runs — reads the experiment's predictions/*.jsonl and rows.jsonl and
compares each patch against the `patch` column of SWE-bench Lite (not `test_patch`).
Definition is locked in docs/swebench/EXPERIMENT_LOCK.md §2.5:

- files of a patch = paths from the diff headers (`--- a/…`, `+++ b/…`), minus /dev/null
- localized = the agent's files and the gold files intersect
- empty patch = not localized
- partial patches from api_error / max_turns / wall_timeout runs are scored as-is

Writes <exp_dir>/localization.{jsonl,csv}, one line per row in rows.jsonl, and prints
a per-toolset summary.

    python scripts/localization.py artifacts/swebench/experiments/<exp_id>
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from harness.load_data.load_swe_bench_lite import load_raw


def patch_files(patch: str) -> set[str]:
    """Paths a unified diff touches, read from file headers only.

    Only lines between a `diff --git` header and the first hunk are considered, so a
    hunk line that happens to start with `+++ b/` or `--- a/` is never taken as a path.
    """
    files: set[str] = set()
    in_header = False
    for line in (patch or "").splitlines():
        if line.startswith("diff --git "):
            in_header = True
        elif line.startswith("@@"):
            in_header = False
        elif in_header and line.startswith(("--- ", "+++ ")):
            path = line[4:].split("\t", 1)[0].strip()
            if path == "/dev/null":
                continue
            if path.startswith(("a/", "b/")):
                path = path[2:]
            files.add(path)
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exp_dir", help="artifacts/swebench/experiments/<exp_id>")
    ap.add_argument("--split", default="test")
    ap.add_argument("--allow-missing", action="store_true",
                    help="skip rows whose patch is not in predictions/ yet (e.g. while a "
                         "batch is still running and prune_work_loop.sh has not caught up); "
                         "never use for the final analysis")
    args = ap.parse_args()

    exp_dir = Path(args.exp_dir).resolve()
    rows = [json.loads(line) for line in
            (exp_dir / "rows.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

    # (session_id, instance_id) -> patch; ambiguous with repeats>1 (ISSUES #9).
    patches: dict[tuple[str, str], str] = {}
    for path in sorted((exp_dir / "predictions").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            p = json.loads(line)
            key = (p["model_name_or_path"], p["instance_id"])
            if key in patches:
                raise SystemExit(f"duplicate prediction for {key} in {path.name} — "
                                 "repeats>1 is not supported (ISSUES #9)")
            patches[key] = p["model_patch"]

    gold = {r.instance_id: patch_files(r.patch)
            for r in load_raw(args.split)[["instance_id", "patch"]].itertuples()}

    out, missing = [], []
    for r in rows:
        key = (r["session_id"], r["instance_id"])
        if key not in patches:
            missing.append(r["run_id"])
            continue
        agent_files = patch_files(patches[key])
        gold_files = gold[r["instance_id"]]
        overlap = agent_files & gold_files
        out.append({
            "run_id": r["run_id"],
            "instance_id": r["instance_id"],
            "repo": r["repo"],
            "tools": r["tools"],
            "termination_reason": r["termination_reason"],
            "empty_patch": not agent_files,
            "localized": bool(overlap),
            "n_agent_files": len(agent_files),
            "n_gold_files": len(gold_files),
            "n_overlap": len(overlap),
            "agent_files": sorted(agent_files),
            "gold_files": sorted(gold_files),
        })

    if missing:
        msg = (f"{len(missing)} row(s) have no prediction, e.g. {missing[:3]} — "
               "run scripts/salvage_predictions.py first")
        if not args.allow_missing:
            raise SystemExit(msg)
        print(f"WARNING: skipped {msg}\n")

    with open(exp_dir / "localization.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(o, ensure_ascii=False) + "\n" for o in out)
    with open(exp_dir / "localization.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        for o in out:
            w.writerow({**o, "agent_files": ";".join(o["agent_files"]),
                        "gold_files": ";".join(o["gold_files"])})

    by_tools: dict[str, list[dict]] = defaultdict(list)
    for o in out:
        by_tools[o["tools"]].append(o)
    print(f"{'tools':<45} {'runs':>5} {'localized':>10} {'rate':>7} {'empty':>6}")
    for tools, os_ in sorted(by_tools.items()):
        n, loc = len(os_), sum(o["localized"] for o in os_)
        print(f"{tools:<45} {n:>5} {loc:>10} {loc / n:>7.1%} {sum(o['empty_patch'] for o in os_):>6}")
    print(f"\nwrote {exp_dir / 'localization.jsonl'} and localization.csv")


if __name__ == "__main__":
    main()
