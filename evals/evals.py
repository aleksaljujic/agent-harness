import json
import os
import shutil
import time


def prepare(name, seeds):
    d = os.path.abspath(f"./eval_ws/{name}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for fname, content in seeds.get(name, {}).items():
        with open(os.path.join(d, fname), "w") as f:
            f.write(content)
    return d


def make_session_id(model: str, tools: list[str]) -> str:
    tools_slug = "-".join(sorted(tools))
    return f"{model}__{tools_slug}"


def log_run(session_id, name, messages, ok, usage, wall_time=None):
    with open("runs.jsonl", "a") as f:
        f.write(json.dumps({
            "session": session_id,
            "ts": time.time(),
            "task": name,
            "ok": ok,
            "wall_time": wall_time,
            "usage": {
                "prompt": usage.prompt,
                "completion": usage.completion,
                "calls": usage.calls,
                "cost": usage.cost,
            },
            "messages": [
                m if isinstance(m, dict) else m.model_dump() for m in messages
            ],
        }, ensure_ascii=False) + "\n")
