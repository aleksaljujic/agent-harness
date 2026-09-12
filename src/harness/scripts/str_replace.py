import json, sys


def _lines_of(src, offsets):
    return [src.count("\n", 0, o) + 1 for o in offsets]


def main():
    try:
        d = json.load(sys.stdin)
        path, old, new = d["path"], d["old"], d["new"]
    except Exception as e:
        return f"ERROR: bad input: {e}"

    replace_all = bool(d.get("replace_all") or False)
    occurrence = d.get("occurrence")

    if replace_all and occurrence is not None:
        return "ERROR: pass either replace_all or occurrence, not both."
    if occurrence is not None and (isinstance(occurrence, bool) or not isinstance(occurrence, int)):
        return f"ERROR: occurrence must be an integer, got {occurrence!r}."
    if not old:
        return "ERROR: old_str is empty."

    try:
        src = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return f"ERROR: file not found: {path}"
    except UnicodeDecodeError:
        return f"ERROR: file not valid UTF-8: {path}"
    except OSError as e:
        return f"ERROR: cannot read {path}: {e}"

    offsets, i = [], src.find(old)
    while i != -1:
        offsets.append(i)
        i = src.find(old, i + len(old))
    n = len(offsets)

    if n == 0:
        return "ERROR: old_str not found. Read the file and copy exact text including indentation."

    where = f"{path} (lines {', '.join(str(x) for x in _lines_of(src, offsets))})"

    if occurrence is not None and not 1 <= occurrence <= n:
        return f"ERROR: occurrence {occurrence} out of range; old_str appears {n} time(s) in {where}."

    if n > 1 and not replace_all and occurrence is None:
        return (
            f"ERROR: old_str appears {n} times in {where}, must be unique. "
            "Duplicated blocks are usually identical below as well, so adding lines below "
            "will not help; extend old_str UPWARD instead (the preceding comment, def or "
            "class line). Or pass replace_all=true to change every occurrence, or "
            "occurrence=N (1-based, in file order) to pick one."
        )

    targets = [offsets[occurrence - 1]] if occurrence is not None else offsets
    done = _lines_of(src, targets)

    out = src
    for o in reversed(targets):
        out = out[:o] + new + out[o + len(old):]

    try:
        open(path, "w", encoding="utf-8").write(out)
    except OSError as e:
        return f"ERROR: cannot write {path}: {e}"

    return f"OK: replaced {len(targets)} occurrence(s) in {path} (lines {', '.join(str(x) for x in done)})"


print(main())
