import csv
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path


def _load(rows_or_path) -> list[dict]:
    if isinstance(rows_or_path, (str, Path)):
        p = Path(rows_or_path)
        if p.suffix == ".json":
            return json.loads(p.read_text())
        with open(p, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return list(rows_or_path)


def _b(v) -> bool:
    return v in (True, "True", "true", 1, "1")


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def summarize(rows_or_path) -> dict:
    rows = _load(rows_or_path)
    by_session = defaultdict(list)
    for r in rows:
        by_session[r["session_id"]].append(r)

    print(f"\n{'session':<34} {'n':>4} {'resolved':>15} {'empty':>6} {'crash':>6} "
          f"{'$/run':>9} {'$/res':>9} {'tok/run':>9} {'calls':>6} {'s/run':>7}")
    print("-" * 120)

    report = {}
    for sid, rs in sorted(by_session.items()):
        n = len(rs)
        res = sum(_b(r["resolved"]) for r in rs)
        cost = sum(_f(r["cost"]) for r in rs)
        empty = sum(_b(r["empty_patch"]) for r in rs)
        crash = sum(_b(r["crashed"]) for r in rs)
        tok = _mean(_f(r["prompt_tokens"]) + _f(r["completion_tokens"]) for r in rs)
        calls = _mean(_f(r["calls"]) for r in rs)
        secs = _mean(_f(r["wall_time"]) for r in rs)
        print(f"{sid:<34} {n:>4} {f'{res}/{n} ({res / n:.0%})':>15} {empty:>6} {crash:>6} "
              f"{cost / n:>9.4f} {(cost / res if res else float('nan')):>9.4f} "
              f"{tok:>9.0f} {calls:>6.1f} {secs:>7.0f}")
        report[sid] = {
            "n": n, "resolved": res, "resolved_rate": res / n,
            "empty_patch": empty, "crashed": crash,
            "cost_total": cost, "cost_per_run": cost / n,
            "cost_per_resolved": (cost / res if res else None),
            "mean_tokens": tok, "mean_calls": calls, "mean_wall_time": secs,
            "termination": dict(Counter(r["termination_reason"] for r in rs)),
        }

    print("\ntermination_reason:")
    for sid, rs in sorted(by_session.items()):
        print(f"  {sid:<34} {dict(Counter(r['termination_reason'] for r in rs))}")

    print("\nresolved by repo:")
    for sid, rs in sorted(by_session.items()):
        per = defaultdict(lambda: [0, 0])
        for r in rs:
            per[r["repo"]][0] += _b(r["resolved"])
            per[r["repo"]][1] += 1
        print(f"  {sid}")
        for repo, (k, m) in sorted(per.items()):
            print(f"    {repo:<28} {k}/{m}")

    if len(by_session) > 1:
        print("\npaired Δ resolve (discordant b = only-A, c = only-B):")
        keyed = {sid: {(r["instance_id"], r["run_index"]): _b(r["resolved"]) for r in rs}
                 for sid, rs in by_session.items()}
        for a, bsid in combinations(sorted(keyed), 2):
            shared = keyed[a].keys() & keyed[bsid].keys()
            b = sum(keyed[a][k] and not keyed[bsid][k] for k in shared)
            c = sum(keyed[bsid][k] and not keyed[a][k] for k in shared)
            delta = sum(keyed[bsid][k] for k in shared) - sum(keyed[a][k] for k in shared)
            print(f"  {a}  vs  {bsid}:  n={len(shared)}  Δ={delta:+d}  b={b} c={c}")
            report.setdefault("pairs", {})[f"{a}|{bsid}"] = {
                "n": len(shared), "delta": delta, "b": b, "c": c}

    return report


if __name__ == "__main__":
    import sys
    summarize(sys.argv[1])
