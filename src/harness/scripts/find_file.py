import json, sys, os
from fnmatch import fnmatch

EXCLUDE_DIRS = {".git", "node_modules"}

def main():
    try:
        d = json.load(sys.stdin)
        pattern = d["pattern"]
        limit = d.get("limit")
    except Exception as e:
        return f"ERROR: band input: {e}"

    if limit is None:
        limit = 100
    if not isinstance(pattern, str) or not pattern:
        return "ERROR: pattern must be a non-empty string"
    if not isinstance(limit, int) or limit < 1:
        return f"ERROR: limit must be a positive integer, got {limit!r}"

    has_glob = any(c in pattern for c in "*?[")
    matches = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [x for x in dirs if x not in EXCLUDE_DIRS]
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), ".")
            if has_glob:
                hit = fnmatch(name, pattern) or fnmatch(rel, pattern)
            else:
                hit = pattern in name
            if hit:
                matches.append(rel)

    matches.sort()
    total = len(matches)

    if total == 0:
        return "No files found."

    out = "\n".join(matches[:limit])
    if total > limit:
        out += f"\n... (truncated, showing first {limit} of {total})"
    return out

print(main())
