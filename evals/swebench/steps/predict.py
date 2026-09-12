import json
import subprocess
from pathlib import Path

from evals.swebench.schemas import PatchInfo, Prediction


def _git(workdir, *args, check=True) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", "-C", str(workdir), *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr}")
    return p


def extract(workdir) -> PatchInfo:
    """The agent's changes as a unified diff, plus shape diagnostics.

    Stages everything (so new files are captured) and diffs against the base
    commit left by provision.checkout().
    """
    workdir = Path(workdir)
    _git(workdir, "add", "-A")
    diff = _git(workdir, "diff", "--cached", "HEAD").stdout

    files = [f for f in _git(workdir, "diff", "--cached", "--name-only", "HEAD").stdout.split() if f]
    ins = dels = 0
    for line in _git(workdir, "diff", "--cached", "--numstat", "HEAD").stdout.splitlines():
        a, b, *_ = (*line.split("\t"), "", "")
        if a.isdigit() and b.isdigit():
            ins += int(a)
            dels += int(b)

    empty = not diff.strip()
    applied = False
    if not empty:
        applied = subprocess.run(
            ["git", "-C", str(workdir), "apply", "--check", "--reverse", "-"],
            input=diff, capture_output=True, text=True,
        ).returncode == 0

    return PatchInfo(
        model_patch=diff,
        empty_patch=empty,
        patch_applied=applied,
        patch_files_changed=len(files),
        patch_lines_changed=ins + dels,
    )


def write_predictions(path, records: list[Prediction]) -> Path:
    """One JSON object per line: {instance_id, model_name_or_path, model_patch}."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({
                "instance_id": r["instance_id"],
                "model_name_or_path": r["model_name_or_path"],
                "model_patch": r["model_patch"],
            }) + "\n")
    return path
