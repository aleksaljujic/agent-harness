import csv
import itertools
import json
import time
import traceback
from datetime import datetime
from pathlib import Path

from evals import log_run, make_session_id, prepare
from harness.agent import Agent
from harness.config import settings
from harness.providers import make_provider
from harness.sandbox import Sandbox


def all_tool_combinations(tools, required=("bash",)):
    """Every non-empty subset of `tools` that contains all of `required`."""
    combos = []
    for r in range(1, len(tools) + 1):
        for combo in itertools.combinations(tools, r):
            if all(req in combo for req in required):
                combos.append(list(combo))
    return combos


def run_one(session_id, name, task, check, *, provider, tools, seeds, run_index, max_turns):
    workdir = prepare(name, seeds)
    s = Sandbox(workdir)
    agent = Agent(s,provider=provider, tools=tools, max_turns=max_turns)

    ok = False
    crashed = False
    error_type = ""
    wall_start = time.perf_counter()
    try:
        agent.run(task)
        ok = bool(check(s))
    except Exception as e:
        crashed = True
        error_type = type(e).__name__
        ok = False
        traceback.print_exc()
    finally:
        s.destroy()
    wall_time = time.perf_counter() - wall_start

    log_run(session_id, name, agent.messages, ok, agent.usage, wall_time)

    row = {
        "model": provider.model,
        "session_id": session_id,
        "task": name,
        "run_index": run_index,
        "uses_bash": "bash" in tools,
        "uses_search": "search" in tools,
        "uses_str_replace": "str_replace" in tools,
        "ok": ok,
        "crashed": crashed,
        "error_type": error_type,
        "prompt_tokens": agent.usage.prompt,
        "completion_tokens": agent.usage.completion,
        "total_tokens": agent.usage.prompt + agent.usage.completion,
        "calls": agent.usage.calls,
        "cost": agent.usage.cost,
        "wall_time": wall_time,
        "ts": time.time(),
    }
    return row, agent.messages


def write_csv(path, rows):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_message_md(m):
    m = m if isinstance(m, dict) else m.model_dump()
    role = m.get("role", "?")
    label = f"**tool** (`{m['tool_call_id']}`)" if role == "tool" else f"**{role}**"

    parts = [label]
    content = m.get("content")
    if content:
        parts.append(content if isinstance(content, str) else str(content))

    for tc in m.get("tool_calls") or []:
        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
        parts.append(f"→ call `{fn.get('name', '?')}({fn.get('arguments', '')})`")

    return "\n\n".join(parts)


def render_run_markdown(row, messages):
    status = "PASS" if row["ok"] else (f"CRASH: {row['error_type']}" if row["crashed"] else "FAIL")
    header = (
        f"## {row['session_id']} · {row['task']} · run {row['run_index']}\n\n"
        f"- model: `{row['model']}`\n"
        f"- tools: bash={row['uses_bash']} search={row['uses_search']} str_replace={row['uses_str_replace']}\n"
        f"- result: {status}\n"
        f"- tokens: {row['prompt_tokens']} in / {row['completion_tokens']} out "
        f"({row['total_tokens']} total), calls={row['calls']}, cost=${row['cost']:.4f}, "
        f"wall_time={row['wall_time']:.1f}s\n\n"
        "### Conversation\n\n"
    )
    body = "\n\n---\n\n".join(format_message_md(m) for m in messages)
    return header + body + "\n"


def write_markdown(path, sections, model):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Eval runs — {model} — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("\n\n---\n\n".join(sections))
        f.write("\n")


def run_pipeline(*, model, tool_universe, repeats, tasks, seeds, artifacts_dir,
                  required_tools=("bash",), combos=None, max_turns=None):
    artifacts_dir = Path(artifacts_dir)
    json_dir = artifacts_dir / "evals" / "logs"
    csv_dir = artifacts_dir / "evals" / "tables"
    md_dir = artifacts_dir / "evals" / "conversation"
    for d in (json_dir, csv_dir, md_dir):
        d.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    provider = make_provider(settings, model=model)
    tool_combos = combos if combos is not None else all_tool_combinations(tool_universe, required_tools)
    max_turns = max_turns if max_turns is not None else settings.max_turns

    rows = []
    md_sections = []
    total_runs = len(tool_combos) * len(tasks) * repeats
    done = 0

    for tools in tool_combos:
        session_id = make_session_id(model, tools)
        for name, task, check in tasks:
            for run_index in range(repeats):
                done += 1
                print(f"[{done}/{total_runs}] {session_id} · {name} · run {run_index + 1}/{repeats}")
                row, messages = run_one(
                    session_id, name, task, check,
                    provider=provider, tools=tools, seeds=seeds,
                    run_index=run_index, max_turns=max_turns,
                )
                rows.append(row)
                md_sections.append(render_run_markdown(row, messages))
                status = "PASS" if row["ok"] else ("CRASH" if row["crashed"] else "FAIL")
                print(f"    {status}  {row['wall_time']:.1f}s  "
                      f"{row['total_tokens']:,} tok  ${row['cost']:.4f}")

    json_path = json_dir / f"runs_eval_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    csv_path = csv_dir / f"runs_eval_{timestamp}.csv"
    write_csv(csv_path, rows)

    md_path = md_dir / f"runs_eval_{timestamp}.md"
    write_markdown(md_path, md_sections, model)

    return json_path, csv_path, md_path, rows
