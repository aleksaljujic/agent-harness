import json, sys

def main():
    try:
        d = json.load(sys.stdin)
        path = d["path"]
        start = d.get("start_line")
        end = d.get("end_line")
    except Exception as e:
        return f"ERROR: band input: {e}"

    try:
        src = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return f"ERROR: file not found: {path}"
    except UnicodeDecodeError:
        return f"ERROR: file not vallid UTF-8: {path}"
    except IsADirectoryError:
        return f"ERROR: is a directory: {path}"
    except OSError as e:
        return f"ERROR: cannot read {path}: {e}"

    lines = src.splitlines()
    total = len(lines)
    # Checked before the range: with no lines, the default range 1..0 would
    # otherwise fail as "start_line 1 is after end_line 0".
    if total == 0:
        return f"OK: {path} is empty"

    lo = 1 if start is None else start
    hi = total if end is None else end

    if not isinstance(lo, int) or not isinstance(hi, int):
        return "ERROR: start_line and end_line must be integers"
    if lo < 1:
        return f"ERROR: start_line must be >= 1, got {lo}"
    if lo > total:
        return f"ERROR: start_line {lo} beyond end of file ({total} lines)"
    if lo > hi:
        return f"ERROR: start_line {lo} is after end_line {hi}"

    hi = min(hi, total)

    out = "\n".join(f"{i:6d}\t{lines[i - 1]}" for i in range(lo, hi + 1))
    return out

print(main())
