import json, sys, os, subprocess, tempfile
import xml.etree.ElementTree as ET

PYTEST_TIMEOUT = 280

def main():
    try:
        d = json.load(sys.stdin)
        tests = d["tests"]
    except Exception as e:
        return json.dumps({"error": f"band input: {e}"})

    path = d.get("path") or "."

    if not isinstance(tests, list) or not tests or not all(isinstance(t, str) and t.strip() for t in tests):
        return json.dumps({"error": 'tests must be a non-empty list of node ids, or ["all"]'})

    targets = [path] if tests == ["all"] else tests

    fd, xml_path = tempfile.mkstemp(suffix=".xml", prefix="pytest-")
    os.close(fd)
    try:
        p = subprocess.run(
            ["python", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
             "--tb=short", "--junit-xml", xml_path, *targets],
            capture_output=True, text=True, timeout=PYTEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        os.unlink(xml_path)
        return json.dumps({"error": f"pytest timed out after {PYTEST_TIMEOUT}s"})

    try:
        has_xml = os.path.getsize(xml_path) > 0
    except OSError:
        has_xml = False

    if p.returncode in (2, 3, 4) or not has_xml:
        tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-25:])
        result = _blank()
        result["collection_error"] = tail or f"pytest exited {p.returncode} with no report"
        os.unlink(xml_path)
        return json.dumps(result, indent=2)

    try:
        result = parse_junit(xml_path)
    finally:
        os.unlink(xml_path)
    return json.dumps(result, indent=2)


def _blank():
    return {
        "summary": {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "total": 0, "duration_seconds": 0.0},
        "passed": [], "failed": [], "errors": [], "skipped": [],
        "failure_details": {},
        "collection_error": None,
    }


def parse_junit(xml_path):
    root = ET.parse(xml_path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")

    res = _blank()
    duration = 0.0
    for suite in suites:
        try:
            duration += float(suite.get("time") or 0.0)
        except ValueError:
            pass
        for tc in suite.findall("testcase"):
            file = tc.get("file") or (tc.get("classname", "").replace(".", "/") + ".py")
            nodeid = f"{file}::{tc.get('name')}"
            error = tc.find("error")
            failure = tc.find("failure")
            skipped = tc.find("skipped")
            if error is not None:
                res["errors"].append(nodeid)
                res["failure_details"][nodeid] = _short(error)
            elif failure is not None:
                res["failed"].append(nodeid)
                res["failure_details"][nodeid] = _short(failure)
            elif skipped is not None:
                res["skipped"].append(nodeid)
            else:
                res["passed"].append(nodeid)

    res["summary"] = {
        "passed": len(res["passed"]),
        "failed": len(res["failed"]),
        "errors": len(res["errors"]),
        "skipped": len(res["skipped"]),
        "total": sum(len(res[k]) for k in ("passed", "failed", "errors", "skipped")),
        "duration_seconds": round(duration, 3),
    }
    return res


def _short(el):
    msg = (el.get("message") or "").strip()
    if msg:
        return msg.splitlines()[0][:300]
    text = (el.text or "").strip()
    return (text.splitlines()[-1][:300] if text else "")


print(main())
