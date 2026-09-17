import json, os, subprocess, sys, tempfile
from fnmatch import fnmatch

EXCLUDE_DIRS = {".git", "node_modules"}
GLOB_CHARS = "*?["
MAX_HITS = 50
BATCH = 500  # files per grep call, keeps argv well under ARG_MAX
WORKDIR = "/work/"


def normalize(glob):
    glob = glob.removeprefix(WORKDIR)
    while glob.startswith("./"):
        glob = glob[2:]
    return glob


def files_matching(glob):
    # Same rule as find_file.py, so any glob that works there works here too.
    # A path glob like sympy/**/*.py cannot go to grep --include (basename only)
    # or be passed as a literal path (grep gets "sympy/**/*.py", which does not exist).
    out = []
    for root, dirs, files in os.walk("."):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(root, name), ".")
            if fnmatch(name, glob) or fnmatch(rel, glob):
                out.append(rel)
    return out


def grep(pattern, targets):
    """targets=None searches the whole tree. Returns (hits, total, error)."""
    base = [
        "grep", "-rnHIs", "--exclude-dir=.git", "--exclude-dir=node_modules",
        # -e so a pattern starting with "-" is never parsed as a grep option
        "-E", "-e", pattern, "--",
    ]
    batches = [[]] if targets is None else [targets[i:i + BATCH] for i in range(0, len(targets), BATCH)]
    hits, total = [], 0
    for batch in batches:
        with tempfile.TemporaryFile(mode="w+") as err:
            p = subprocess.Popen(base + batch, stdout=subprocess.PIPE, stderr=err,
                                 text=True, errors="replace")
            for line in p.stdout:
                total += 1
                if len(hits) < MAX_HITS:
                    hits.append(line.rstrip("\n"))
            rc = p.wait()
            err.seek(0)
            msg = err.read().strip()
        # -s silences unreadable-file noise, so any stderr left on exit 2 is real
        # (e.g. an invalid regex) and would repeat for every batch.
        if rc == 2 and msg:
            return hits, total, msg
    return hits, total, None


def main():
    try:
        d = json.load(sys.stdin)
        pattern = d["pattern"]
        glob = d.get("glob")
    except Exception as e:
        return f"ERROR: bad input: {e}"

    if not isinstance(pattern, str):
        return "ERROR: pattern must be a string"

    targets = None
    if glob:
        glob = normalize(glob)
        if "/" in glob and not any(c in glob for c in GLOB_CHARS):
            if not os.path.exists(glob):
                return f"ERROR: path not found: {glob}"
            targets = [glob]
        else:
            targets = files_matching(glob)
            if not targets:
                return f"No files match glob: {glob}"

    hits, total, error = grep(pattern, targets)
    if error:
        return f"ERROR: {error}"
    if total == 0:
        return "No matches."

    out = "\n".join(hits)
    if total > MAX_HITS:
        out += f"\n... (truncated, showing first {MAX_HITS} of {total} matches; narrow pattern or glob)"
    return out


print(main())
