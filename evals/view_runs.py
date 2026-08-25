import json, sys

COLORS = {"user": "\033[36m", "assistant": "\033[33m", "bash": "\033[35m",
          "out": "\033[90m", "reset": "\033[0m"}

def c(key, text):
    return f"{COLORS[key]}{text}{COLORS['reset']}"

def show(entry):
    status = "PASS" if entry["ok"] else "FAIL"
    print(f"\n{'=' * 70}\n{status}  {entry['task']}\n{'=' * 70}")

    for m in entry["messages"]:
        role = m.get("role")

        if role == "system":
            continue

        if role == "user":
            print(f"\n{c('user', '▸ TASK')}  {m['content']}")

        elif role == "assistant":
            if m.get("content"):
                print(f"\n{c('assistant', '▸ SAYS')}  {m['content'].strip()}")
            for tc in (m.get("tool_calls") or []):
                args = json.loads(tc["function"]["arguments"])
                cmd = args.get("command", "")
                print(f"\n{c('bash', '$')} {cmd}")

        elif role == "tool":
            out = (m.get("content") or "").rstrip()
            lines = out.split("\n")
            if len(lines) > 12:
                lines = lines[:12] + [f"... (+{len(lines) - 12} redova)"]
            for line in lines:
                print(c("out", f"  │ {line}"))

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    with open("runs.jsonl") as f:
        for line in f:
            e = json.loads(line)
            if only in (None, e["task"], "fail" if not e["ok"] else "_"):
                show(e)