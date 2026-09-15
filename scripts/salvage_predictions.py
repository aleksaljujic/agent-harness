"""Rebuild predictions/*.jsonl from the per-run checkouts left in artifacts/swebench/work/.

Only needed for experiments produced before predictions were persisted per run: back
then `predictions/<session>.jsonl` was written once, after a whole session finished, so
interrupting a 300-instance session threw away every patch it had produced. The
checkouts under `work/` are the only surviving copy, and `predict.extract()` can
recover the diff from each one.

Runs are matched against rows.jsonl — a checkout with no row is an interrupted run and
is skipped, since no row means nothing downstream refers to it.

    python scripts/salvage_predictions.py artifacts/swebench/experiments/<exp_id>
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from evals.swebench.steps import predict


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exp_dir", help="artifacts/swebench/experiments/<exp_id>")
    ap.add_argument("--work-root", default=None,
                    help="defaults to <artifacts>/swebench/work/<exp_id>")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prune", action="store_true",
                    help="delete each checkout once its patch is safely written, to keep "
                         "disk flat while a batch is still running")
    args = ap.parse_args()

    exp_dir = Path(args.exp_dir).resolve()
    exp_id = exp_dir.name
    work_root = Path(args.work_root) if args.work_root else exp_dir.parent.parent / "work" / exp_id
    if not work_root.exists():
        raise SystemExit(f"no work dir: {work_root}")

    rows = [json.loads(l) for l in (exp_dir / "rows.jsonl").read_text().splitlines() if l.strip()]
    by_run = {r["run_id"]: r for r in rows}
    print(f"{len(rows)} rows, work root {work_root}")

    recovered: dict[str, list] = {}
    pruneable: dict[str, list[Path]] = {}
    skipped = failed = 0
    for session_dir in sorted(p for p in work_root.iterdir() if p.is_dir()):
        session_id = session_dir.name
        for inst_dir in sorted(p for p in session_dir.iterdir() if p.is_dir()):
            for run_dir in sorted(p for p in inst_dir.iterdir() if p.is_dir()):
                run_id = f"{session_id}/{inst_dir.name}/{run_dir.name}"
                # No row means the run never finished — on a live batch that is the
                # one currently executing, so leave its checkout alone.
                if run_id not in by_run:
                    skipped += 1
                    continue
                try:
                    info = predict.extract(run_dir)
                except Exception as e:  # noqa: BLE001
                    print(f"  FAILED {run_id}: {type(e).__name__}: {e}")
                    failed += 1
                    continue
                recovered.setdefault(session_id, []).append({
                    "instance_id": inst_dir.name,
                    "model_name_or_path": session_id,
                    "model_patch": info.model_patch,
                })
                pruneable.setdefault(session_id, []).append(run_dir)

    print(f"recovered {sum(len(v) for v in recovered.values())} patches, "
          f"skipped {skipped} (unfinished), failed {failed}")

    for session_id, recs in sorted(recovered.items()):
        path = exp_dir / "predictions" / f"{session_id}.jsonl"
        # Merge, never overwrite: with --prune the checkouts behind earlier records
        # are already gone, so a plain rewrite would silently shrink the file each
        # time this is run.
        existing = {r["instance_id"]: r for r in predict.read_predictions(path)}
        added = sum(1 for r in recs if r["instance_id"] not in existing)
        existing.update({r["instance_id"]: r for r in recs})
        merged = list(existing.values())
        nonempty = sum(1 for r in merged if r["model_patch"].strip())
        print(f"  {session_id}: +{added} new, {len(merged)} total ({nonempty} non-empty) -> {path}")
        if not args.dry_run:
            predict.write_predictions(path, merged)

    if args.prune and not args.dry_run:
        freed = 0
        for dirs in pruneable.values():
            for d in dirs:
                freed += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                shutil.rmtree(d, ignore_errors=True)
        print(f"pruned {sum(len(v) for v in pruneable.values())} checkouts, "
              f"freed ~{freed / 1e9:.1f} GB")
    if args.dry_run:
        print("(dry run, nothing written or pruned)")


if __name__ == "__main__":
    main()
