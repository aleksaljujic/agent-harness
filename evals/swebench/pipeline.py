import json
import shutil
import subprocess
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from openai import OpenAIError
from tqdm import tqdm

from evals.evals import make_session_id
from evals.pipeline import all_tool_combinations, write_csv
from evals.swebench.steps import grade, predict, provision
from evals.swebench.config import DATASET, TOOL_UNIVERSE, swe_settings
from evals.swebench.prompt import SWEBENCH_SYSTEM
from evals.swebench.schemas import GRADE_FIELDS, PatchInfo, Prediction, RunRow
from harness.agent import Agent
from harness.config import settings
from harness.providers import make_provider
from harness.sandbox import Sandbox

DEFAULT_TOOLS = list(TOOL_UNIVERSE)

# Grace period for a timed-out agent thread to stop before the row is recorded.
STOP_GRACE_SECONDS = 5


def _harness_sha() -> str:
    p = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return p.stdout.strip() or "unknown"


def _error_detail(e: Exception) -> dict:
    """Collect exception details, including the API error body if present."""
    detail = {
        "type": type(e).__name__,
        "message": str(e),
        "traceback": traceback.format_exc(),
    }
    status_code = getattr(e, "status_code", None)
    if status_code is not None:
        detail["status_code"] = status_code
    request_id = getattr(e, "request_id", None)
    if request_id is not None:
        detail["request_id"] = request_id
    body = getattr(e, "body", None)
    if body is not None:
        detail["body"] = body
        if isinstance(body, dict):
            # SDK returns a flat dict; the {"error": {...}} envelope is also handled.
            err = body["error"] if isinstance(body.get("error"), dict) else body
            detail["api_code"] = err.get("code")
            detail["api_param"] = err.get("param")
            detail["api_message"] = err.get("message")
    response = getattr(e, "response", None)
    text = getattr(response, "text", None) if response is not None else None
    if text is not None:
        detail["response_text"] = text[:20000]
    # Set by OpenAIProvider after exhausting invalid_prompt retries.
    retries = getattr(e, "invalid_prompt_retries", None)
    if retries is not None:
        detail["invalid_prompt_retries"] = retries
    return detail


def _error_summary(detail: dict) -> str:
    """One line for the CSV/JSONL row; full detail goes to the errors/ file."""
    msg = detail.get("api_message") or detail.get("message") or ""
    msg = " ".join(msg.split())[:300]
    prefix = str(detail.get("status_code") or detail.get("type") or "error")
    code = detail.get("api_code")
    return f"{prefix} {code}: {msg}" if code else f"{prefix}: {msg}"


def _run_agent_bounded(agent: Agent, task: str, timeout: int) -> tuple[str, str, dict]:
    """Run agent.run(task) under a wall-clock bound.

    Returns (termination_reason, error_type, error_detail). A mid-run exception (API
    moderation, rate limit, network) is caught, not raised — the partial working tree
    is still worth extracting a patch from.
    """
    box: dict = {}

    def target():
        try:
            box["ret"] = agent.run(task)
        except Exception as e:  # noqa: BLE001
            box["exc"] = e
            # Must be captured in this thread; format_exc() is per-thread.
            box["tb"] = traceback.format_exc()

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        # Stop the agent so usage is final and no tools hit a destroyed sandbox.
        # Cannot interrupt a request already blocked in provider.complete().
        agent.stop.set()
        t.join(STOP_GRACE_SECONDS)
        return "wall_timeout", "", {}
    if "exc" in box:
        exc = box["exc"]
        detail = _error_detail(exc)
        if box.get("tb"):
            detail["traceback"] = box["tb"]
        # Only provider-side failures count as api_error; anything else is a harness bug.
        reason = "api_error" if isinstance(exc, OpenAIError) else "harness_error"
        return reason, detail["type"], detail
    return agent.termination_reason, "", {}


def run_one(instance: dict, tools: list[str], run_index: int, *, provider, session_id,
            work_root: Path, max_turns: int, run_timeout: int,
            harness_sha: str, temperature: float | None = None,
            keep_work: bool = False) -> tuple[RunRow, list, Prediction, dict]:
    iid = instance["instance_id"]
    workdir = work_root / session_id / iid / str(run_index)

    crashed, error_type, error_message, termination_reason = False, "", "", "unstarted"
    error_detail: dict = {}
    pred = PatchInfo()
    agent = None
    s = None
    wall_start = time.perf_counter()
    try:
        provision.checkout(instance, workdir)
        s = Sandbox(workdir, network=swe_settings.sandbox_network)
        agent = Agent(s, provider=provider, tools=tools,
                      system_promt=SWEBENCH_SYSTEM, max_turns=max_turns)
        termination_reason, error_type, error_detail = _run_agent_bounded(
            agent, instance["problem_statement"], run_timeout)
        if error_detail:
            error_message = _error_summary(error_detail)
        if termination_reason == "wall_timeout" and s:
            s.destroy()
            s = None
        try:
            pred = predict.extract(workdir)
        except Exception as e:  # noqa: BLE001 - diff extraction is best-effort
            error_type = error_type or type(e).__name__
            traceback.print_exc()
    except Exception as e:  # noqa: BLE001 - provisioning / sandbox setup failed
        crashed = True
        error_type = type(e).__name__
        error_detail = _error_detail(e)
        error_message = _error_summary(error_detail)
        termination_reason = "crash"
        traceback.print_exc()
    finally:
        if s:
            s.destroy()
        # ~80MB per checkout; not needed once the diff is extracted.
        if not keep_work:
            shutil.rmtree(workdir, ignore_errors=True)
    wall_time = time.perf_counter() - wall_start

    usage = agent.usage if agent else None
    messages = agent.messages if agent else []
    row = RunRow(
        run_id=f"{session_id}/{iid}/{run_index}",
        session_id=session_id,
        model=provider.model,
        tools="+".join(tools),
        toolset_condition="+".join(sorted(tools)),
        instance_id=iid,
        repo=instance["repo"],
        run_index=run_index,
        empty_patch=pred.empty_patch,
        patch_applied=pred.patch_applied,
        patch_files_changed=pred.patch_files_changed,
        patch_lines_changed=pred.patch_lines_changed,
        prompt_tokens=usage.prompt if usage else 0,
        completion_tokens=usage.completion if usage else 0,
        reasoning_tokens=usage.reasoning if usage else 0,
        cost=usage.cost if usage else 0.0,
        wall_time=wall_time,
        llm_seconds=usage.llm_time_seconds if usage else 0.0,
        tool_seconds=usage.tool_time_seconds if usage else 0.0,
        calls=usage.calls if usage else 0,
        crashed=crashed,
        error_type=error_type,
        error_message=error_message,
        # A failed run's retries are only in error_detail, not in usage.
        invalid_prompt_retries=(
            (usage.invalid_prompt_retries if usage else 0)
            or error_detail.get("invalid_prompt_retries", 0)
        ),
        termination_reason=termination_reason,
        turns_used=agent.turns_used if agent else 0,
        max_turns=max_turns,
        tool_calls_breakdown=dict(usage.tool_calls) if usage else {},
        tool_call_errors=dict(usage.tool_call_errors) if usage else {},
        reasoning_effort=getattr(provider, "reasoning_effort", None) or "",
        temperature=temperature,
        harness_sha=harness_sha,
        dataset=DATASET,
        split=swe_settings.split,
        network=swe_settings.sandbox_network,
        ts=time.time(),
    )
    prediction: Prediction = {"instance_id": iid, "model_name_or_path": session_id,
                              "model_patch": pred.model_patch}
    return row, messages, prediction, error_detail


def _render_md(row: RunRow, messages: list) -> str:
    error_line = f"- error: {row.error_message}\n" if row.error_message else ""
    head = (
        f"## {row.session_id} · {row.instance_id} · run {row.run_index}\n\n"
        f"- resolved: **{row.resolved}**  |  termination: {row.termination_reason}  "
        f"|  crashed: {row.crashed} {row.error_type}\n"
        f"{error_line}"
        f"- F2P {row.tests_fail_to_pass_passed}/{row.tests_fail_to_pass_total}  ·  "
        f"P2P {row.tests_pass_to_pass_passed}/{row.tests_pass_to_pass_total}\n"
        f"- patch: {row.patch_files_changed} files, {row.patch_lines_changed} lines, "
        f"applied={row.patch_applied}, empty={row.empty_patch}\n"
        f"- {row.calls} calls · {row.prompt_tokens} in / {row.completion_tokens} out · "
        f"${row.cost:.4f} · {row.wall_time:.0f}s · turns {row.turns_used}/{row.max_turns}\n"
        f"- tools: {row.tool_calls_breakdown}  errors: {row.tool_call_errors}\n\n"
        "### Conversation\n\n"
    )
    parts = []
    for m in messages:
        m = m if isinstance(m, dict) else m.model_dump()
        role = m.get("role", "?")
        seg = [f"**{role}**"]
        if m.get("content"):
            seg.append(m["content"] if isinstance(m["content"], str) else str(m["content"]))
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            seg.append(f"→ `{fn.get('name', '?')}({fn.get('arguments', '')})`")
        parts.append("\n\n".join(seg))
    return head + "\n\n---\n\n".join(parts) + "\n"


def _rollup(rows: list[RunRow]) -> dict:
    """Aggregate a set of run rows into totals + per-session breakdown."""
    def agg(rs: list[RunRow]) -> dict:
        n = len(rs)
        term: dict[str, int] = {}
        for r in rs:
            term[r.termination_reason] = term.get(r.termination_reason, 0) + 1
        return {
            "runs": n,
            "resolved": sum(r.resolved for r in rs),
            "resolved_rate": (sum(r.resolved for r in rs) / n if n else 0.0),
            "empty_patch": sum(r.empty_patch for r in rs),
            "crashed": sum(r.crashed for r in rs),
            "cost": sum(r.cost for r in rs),
            "prompt_tokens": sum(r.prompt_tokens for r in rs),
            "completion_tokens": sum(r.completion_tokens for r in rs),
            "wall_time": sum(r.wall_time for r in rs),
            "termination": term,
        }

    by_session: dict[str, list[RunRow]] = {}
    for r in rows:
        by_session.setdefault(r.session_id, []).append(r)
    return {
        "totals": agg(rows),
        "by_session": {sid: agg(rs) for sid, rs in sorted(by_session.items())},
    }


def run_pipeline(*, model, instances, tool_combos=None, tool_universe=None, repeats=1,
                 artifacts_dir, name=None, max_turns=None, run_timeout=None, max_workers=4,
                 grade_enabled=True, reasoning_effort=None, temperature=None, selection=None,
                 resume_from=None, keep_work=False):
    artifacts_dir = Path(artifacts_dir)
    swe_root = artifacts_dir / "swebench"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if resume_from:
        exp_root = Path(resume_from).resolve()
        if not exp_root.exists():
            raise SystemExit(f"--resume: no such experiment dir: {exp_root}")
        exp_id = exp_root.name
    else:
        exp_id = f"{timestamp}_{name or model}"
        exp_root = swe_root / "experiments" / exp_id
    conv_dir = exp_root / "conversations"
    msg_dir = exp_root / "messages"
    err_dir = exp_root / "errors"
    preds_dir = exp_root / "predictions"
    grade_dir = exp_root / "grading"
    work_root = swe_root / "work" / exp_id          # bulky checkouts, kept out of the results tree
    for d in (conv_dir, msg_dir, err_dir, preds_dir, grade_dir, work_root):
        d.mkdir(parents=True, exist_ok=True)

    provider = make_provider(settings, model=model, reasoning_effort=reasoning_effort,
                             temperature=temperature)
    # Temperature actually sent: never with reasoning_effort; None = not sent.
    effective_temperature = None if reasoning_effort else temperature
    max_turns = max_turns or swe_settings.max_turns
    run_timeout = run_timeout or swe_settings.run_timeout
    harness_sha = _harness_sha()

    if tool_combos is None:
        tool_combos = all_tool_combinations(tool_universe or DEFAULT_TOOLS, ("bash",))

    all_rows = []
    # Resume: runs already in rows.jsonl are skipped.
    done_rows: dict[str, RunRow] = {}
    if resume_from:
        for line in (exp_root / "rows.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = RunRow(**json.loads(line))
                done_rows[r.run_id] = r
        tqdm.write(f"resuming {exp_root.name}: {len(done_rows)} run(s) already done")

    total = len(tool_combos) * len(instances) * repeats
    pbar = tqdm(total=total, desc="swebench", unit="run")
    pbar.update(len(done_rows))

    # Rewritten after every run so an interrupted batch keeps its results.
    rows_json = exp_root / "rows.jsonl"

    def _checkpoint(rows: list[RunRow]) -> None:
        rows_json.write_text(
            "".join(json.dumps(r.model_dump(), ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8")

    for tools in tool_combos:
        session_id = make_session_id(model, tools)
        preds_path = preds_dir / f"{session_id}.jsonl"
        session_rows, session_preds = [], []
        if resume_from:
            # Checkouts are gone, so patches come from the predictions file.
            session_preds = predict.read_predictions(preds_path)
            session_rows = [done_rows[k] for k in
                            (f"{session_id}/{i['instance_id']}/{r}"
                             for i in instances for r in range(repeats))
                            if k in done_rows]

        for instance in instances:
            for run_index in range(repeats):
                if f"{session_id}/{instance['instance_id']}/{run_index}" in done_rows:
                    continue
                pbar.set_postfix_str(f"{session_id} · {instance['instance_id']} · run {run_index}")
                row, messages, prediction, error_detail = run_one(
                    instance, tools, run_index,
                    provider=provider, session_id=session_id, work_root=work_root,
                    max_turns=max_turns, run_timeout=run_timeout, harness_sha=harness_sha,
                    temperature=effective_temperature, keep_work=keep_work,
                )
                session_rows.append(row)
                session_preds.append(prediction)
                # Written after every run so an interrupt loses no patches.
                predict.write_predictions(preds_path, session_preds)
                run_name = f"{session_id}__{instance['instance_id']}__{run_index}"
                (conv_dir / f"{run_name}.md").write_text(
                    _render_md(row, messages), encoding="utf-8")
                (msg_dir / f"{run_name}.json").write_text(
                    json.dumps({
                        "model": provider.model, "tools": tools,
                        "reasoning_effort": reasoning_effort or "", "messages": messages,
                    }, ensure_ascii=False, default=str),
                    encoding="utf-8")
                if error_detail:
                    (err_dir / f"{run_name}.json").write_text(
                        json.dumps(error_detail, ensure_ascii=False, default=str, indent=2),
                        encoding="utf-8")
                tqdm.write(f"    {session_id} · {instance['instance_id']} · run {run_index} — "
                          f"{row.termination_reason}  {row.wall_time:.0f}s  "
                          f"${row.cost:.4f}  patch={not row.empty_patch}")
                pbar.update(1)
                _checkpoint(all_rows + session_rows)

        predict.write_predictions(preds_path, session_preds)

        if grade_enabled:
            run_id = f"{exp_id}_{session_id}"
            tqdm.write(f"  grading {session_id} ({len(session_preds)} predictions) …")
            try:
                results = grade.grade(preds_path, run_id=run_id, model=session_id,
                                      output_dir=grade_dir / session_id, max_workers=max_workers)
            except Exception as e:  # noqa: BLE001
                tqdm.write(f"  grading failed: {type(e).__name__}: {e}")
                results = {}
            for row in session_rows:
                r = results.get(row.instance_id)
                if r:
                    for k in GRADE_FIELDS:
                        setattr(row, k, r[k])
            _checkpoint(all_rows + session_rows)  # overwrite the ungraded snapshot

        all_rows.extend(session_rows)
        _checkpoint(all_rows)

    pbar.close()
    csv_path = exp_root / "rows.csv"
    write_csv(csv_path, [r.csv_row() for r in all_rows])

    rollup = _rollup(all_rows)
    # A resumed experiment keeps its original creation time.
    manifest_path = exp_root / "manifest.json"
    created = timestamp
    if resume_from and manifest_path.exists():
        created = json.loads(manifest_path.read_text(encoding="utf-8")).get("created", timestamp)
    manifest = {
        "exp_id": exp_id,
        "name": name,
        "ts": time.time(),
        "created": created,
        "resumed_at": timestamp if resume_from else None,
        "model": model,
        "dataset": DATASET,
        "split": swe_settings.split,
        "harness_sha": harness_sha,
        "graded": grade_enabled,
        "config": {
            "instances": [i["instance_id"] for i in instances],
            "n_instances": len(instances),
            "repeats": repeats,
            "toolsets": [make_session_id(model, t) for t in tool_combos],
            "max_turns": max_turns,
            "run_timeout": run_timeout,
            "network": swe_settings.sandbox_network,
            "reasoning_effort": reasoning_effort or "",
            "selection": selection or {},
        },
        **rollup,
        "artifacts": {"rows_csv": "rows.csv", "rows_jsonl": "rows.jsonl",
                      "conversations": "conversations/", "messages": "messages/",
                      "errors": "errors/", "predictions": "predictions/",
                      "grading": "grading/"},
    }
    (exp_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                            encoding="utf-8")

    # global append-only ledger
    t = rollup["totals"]
    ledger_line = {
        "exp_id": exp_id, "name": name, "ts": manifest["ts"], "model": model,
        "dataset": DATASET, "split": swe_settings.split,
        "toolsets": manifest["config"]["toolsets"],
        "n_instances": len(instances), "repeats": repeats, "runs": t["runs"],
        "resolved": t["resolved"], "resolved_rate": round(t["resolved_rate"], 4),
        "total_cost": round(t["cost"], 6),
        "total_tokens": t["prompt_tokens"] + t["completion_tokens"],
        "reasoning_tokens": sum(r.reasoning_tokens for r in all_rows),
        "wall_time_total": round(t["wall_time"], 1),
        "reasoning_effort": reasoning_effort or "",
        "graded": grade_enabled, "harness_sha": harness_sha,
        "path": f"experiments/{exp_id}",
    }
    with open(swe_root / "MANIFEST.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ledger_line, ensure_ascii=False) + "\n")

    return exp_root, csv_path, rows_json, [r.model_dump() for r in all_rows]
