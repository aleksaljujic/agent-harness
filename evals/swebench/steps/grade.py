import json
import subprocess
import sys
from pathlib import Path

from evals.swebench.config import DATASET


def _blank(reason="") -> dict:
    return {
        "resolved": False,
        "tests_fail_to_pass_total": 0, "tests_fail_to_pass_passed": 0,
        "tests_pass_to_pass_total": 0, "tests_pass_to_pass_passed": 0,
        "eval_image": "",
        "grade_error": " ".join(str(reason).split())[:300],
    }


def _instance_log_error(instance_dir: Path) -> str:
    """First ERROR line the evaluator logged for this instance.

    The evaluator's own verdict is only in run_instance.log; without it a row
    says "no report" and gives no way to tell a missing eval image from a real
    test failure.
    """
    log = instance_dir / "run_instance.log"
    if not log.exists():
        return "no run_instance.log"
    for line in log.read_text(errors="replace").splitlines():
        if " - ERROR - " in line:
            return line.split(" - ERROR - ", 1)[1]
    return "no ERROR line in run_instance.log"


def _counts(report_path: Path, instance_id: str) -> dict:
    data = json.loads(report_path.read_text())
    rec = data.get(instance_id, data)  # file is {instance_id: {...}}
    ts = rec.get("tests_status", {})
    f2p, p2p = ts.get("FAIL_TO_PASS", {}), ts.get("PASS_TO_PASS", {})
    f2p_ok, f2p_bad = len(f2p.get("success", [])), len(f2p.get("failure", []))
    p2p_ok, p2p_bad = len(p2p.get("success", [])), len(p2p.get("failure", []))
    return {
        "resolved": bool(rec.get("resolved", False)),
        "tests_fail_to_pass_total": f2p_ok + f2p_bad,
        "tests_fail_to_pass_passed": f2p_ok,
        "tests_pass_to_pass_total": p2p_ok + p2p_bad,
        "tests_pass_to_pass_passed": p2p_ok,
        "eval_image": "",
        "grade_error": "",
    }


def grade(predictions_path, run_id: str, model: str, output_dir,
          max_workers: int = 4, timeout: int | None = None) -> dict[str, dict]:
    """Run the official SWE-bench evaluator; return per-instance results keyed by id.

    `model` must match the predictions' `model_name_or_path`. Report JSON and the
    per-instance logs are written under `output_dir`.
    """
    predictions_path = Path(predictions_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ids = [json.loads(line)["instance_id"] for line in
           predictions_path.read_text().splitlines() if line.strip()]

    cmd = [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", DATASET,
        "--predictions_path", str(predictions_path),
        "--run_id", run_id,
        "--max_workers", str(max_workers),
    ]
    proc = subprocess.run(cmd, cwd=output_dir, text=True, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-40:])
        return {i: _blank(f"evaluator exited {proc.returncode}: {tail}") for i in ids}

    summary_files = sorted(output_dir.glob(f"*{run_id}.json"))
    resolved_ids, error_ids = set(), set()
    if summary_files:
        s = json.loads(summary_files[-1].read_text())
        resolved_ids = set(s.get("resolved_ids", []))
        error_ids = set(s.get("error_ids", []))

    run_logs = output_dir / "logs" / "run_evaluation" / run_id
    logs_root = run_logs / model
    if not logs_root.is_dir() and run_logs.is_dir():
        subdirs = [d for d in run_logs.iterdir() if d.is_dir()]
        if len(subdirs) == 1:  # swebench may sanitize the model name differently
            logs_root = subdirs[0]

    out: dict[str, dict] = {}
    for i in ids:
        report = logs_root / i / "report.json"
        if report.exists():
            out[i] = _counts(report, i)
        elif i in resolved_ids:
            out[i] = {**_blank(), "resolved": True}
        else:
            reason = "no report" + (" (error_instance)" if i in error_ids else "")
            out[i] = _blank(f"{reason}: {_instance_log_error(logs_root / i)}")
    return out
