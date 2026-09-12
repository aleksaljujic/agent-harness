import re
import shutil
import subprocess
from pathlib import Path

from tqdm import tqdm

from evals.swebench.config import REPO_CACHE_DIR as CACHE_ROOT

_GIT_ID = ["-c", "user.email=eval@harness", "-c", "user.name=eval"]
_PROGRESS_RE = re.compile(r"(Counting|Compressing|Receiving|Resolving deltas|Enumerating) objects.*?(\d+)%")


def _run(args, check=True) -> subprocess.CompletedProcess:
    p = subprocess.run(args, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed ({p.returncode}): {' '.join(map(str, args))}\n{p.stderr}")
    return p


def _run_with_progress(args, desc: str) -> None:
    """Run a `git --progress` command, mirroring its stderr into a tqdm bar.

    git only emits progress on a tty by default; --progress forces it even when
    piped. Without this, a slow clone (a large repo, first time) looks hung.
    """
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, bufsize=1)
    bar, phase, last = None, None, 0
    try:
        for line in proc.stderr:
            m = _PROGRESS_RE.search(line)
            if not m:
                continue
            this_phase, pct = m.group(1), int(m.group(2))
            if this_phase != phase:
                if bar:
                    bar.close()
                phase, last = this_phase, 0
                bar = tqdm(total=100, desc=f"{desc}: {phase.lower()}", unit="%", leave=False)
            bar.update(pct - last)
            last = pct
    finally:
        if bar:
            bar.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"cmd failed ({proc.returncode}): {' '.join(map(str, args))}")


def _mirror(repo: str) -> Path:
    """Cached bare mirror of github.com/<repo>; cloned once, fetched thereafter."""
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    dest = CACHE_ROOT / (repo.replace("/", "__") + ".git")
    if dest.exists():
        _run_with_progress(
            ["git", "--git-dir", str(dest), "fetch", "--progress", "--all", "--prune"],
            desc=f"fetch {repo}")
    else:
        _run_with_progress(
            ["git", "clone", "--progress", "--mirror", f"https://github.com/{repo}.git", str(dest)],
            desc=f"clone {repo}")
    return dest


def checkout(instance: dict, dest) -> Path:
    """Materialize <repo>@<base_commit> at `dest`, history stripped to one commit.

    Host-side only: keeps git out of the sandbox image, and removes the upstream
    fix from reachable history (see docs/swebench/AUDIT_REPORT.md 2a).
    """
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    mirror = _mirror(instance["repo"])
    _run(["git", "clone", "--quiet", "--no-checkout", str(mirror), str(dest)])
    _run(["git", "-C", str(dest), "checkout", "--quiet", "--detach", instance["base_commit"]])

    shutil.rmtree(dest / ".git")
    _run(["git", "-C", str(dest), "init", "--quiet"])
    _run(["git", "-C", str(dest), *_GIT_ID, "add", "-A"])
    _run(["git", "-C", str(dest), *_GIT_ID, "commit", "--quiet", "-m", "base"])

    n = _run(["git", "-C", str(dest), "rev-list", "--count", "HEAD"]).stdout.strip()
    if n != "1":
        raise RuntimeError(f"history strip failed: {n} commits at {dest}")
    if _run(["git", "-C", str(dest), "remote"]).stdout.strip():
        raise RuntimeError(f"remotes still present at {dest}")
    return dest
