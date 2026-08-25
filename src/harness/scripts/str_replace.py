import json, sys

def main():
    try:
        d = json.load(sys.stdin)
        path, old, new = d["path"], d["old"], d["new"]
    except Exception as e:
        return f"ERROR: band input: {e}"    
    
    try:
        src = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return f"ERROR: file not found: {path}"
    except UnicodeDecodeError:
        return f"ERROR: file not vallid UTF-8: {path}"
    except OSError as e:
        return f"ERROR: cannot read {path}: {e}"

    n = src.count(old)
    
    if n==0:
        return "ERROR: old_str not found. Read the file and copy exact text including indentation."
    if n > 1:
        return f"ERROR: old_str appears {n} times, must be unique. Include more surrounding lines."
    
    try:
        open(path, "w", encoding="utf-8").write(src.replace(old, new, 1))
    except OSError as e:
        return f"ERROR: cannot write {path}: {e}"

    return f"OK: replaced in {path}"
 
print(main())