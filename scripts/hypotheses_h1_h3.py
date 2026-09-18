"""H1 and H3 tests for the batch_300 toolset ablation, per the pre-registered plan.

Plan is locked in docs/swebench/EXPERIMENT_LOCK.md §2.6; results and explanation live
in docs/swebench/H1.md and docs/swebench/H3.md. Needs a graded experiment
(`resolved` backfilled into rows.jsonl) and localization.jsonl from
scripts/localization.py (for the Holm primary family only).

Conditions (2×2): A bash, B +str_replace, C +search group, D all tools.

- H1: cost per resolved, (B+D) vs (A+C) = Σcost / Σresolved per group.
      Paired bootstrap 95% CI of the difference; confirmed if the whole CI < 0.
      Supplementary Wilcoxon over dᵢ = mean(costB, costD) − mean(costA, costC).
- H3: R_B − R_D (resolve rate), paired bootstrap 95% CI; confirmed if lower bound > −5 pp.

Bootstrap: 10 000 resamples of instances with replacement, each instance taken in all
four conditions at once, percentile interval, seed 20260915. Every analysis is run
twice: primary (invalid_prompt counts as an outcome of the arm, §2.3) and sensitivity
(instances with an api_error in any arm dropped).

    python scripts/hypotheses_h1_h3.py artifacts/swebench/experiments/<exp_id>
"""
import argparse
import json
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

SEED = 20260915
N_BOOT = 10_000
MARGIN_PP = 5.0
ARMS = list("ABCD")
TOOLS_TO_ARM = {
    "bash": "A",
    "bash+str_replace": "B",
    "bash+search+read_file+find_file": "C",
    "bash+search+str_replace+read_file+find_file": "D",
}


def load(exp_dir: Path) -> pd.DataFrame:
    with open(exp_dir / "rows.jsonl") as f:
        rows = pd.DataFrame([json.loads(line) for line in f])
    with open(exp_dir / "localization.jsonl") as f:
        loc = pd.DataFrame([json.loads(line) for line in f])
    df = rows.merge(loc[["run_id", "localized"]], on="run_id", how="left")
    df["arm"] = df.tools.map(TOOLS_TO_ARM)
    if df.arm.isna().any():
        raise SystemExit(f"unknown toolset: {sorted(df.loc[df.arm.isna(), 'tools'].unique())}")
    if df.resolved.isna().any():
        raise SystemExit("rows.jsonl has ungraded runs (resolved is null) — grade first")
    return df


def pivot(df: pd.DataFrame, col: str) -> pd.DataFrame:
    return df.pivot(index="instance_id", columns="arm", values=col)[ARMS]


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2**n, 1.0)


def wilcoxon_signed(d: np.ndarray) -> tuple[float, float, float]:
    """Two-sided Wilcoxon; returns (W = min(W+, W−), p, signed rank-biserial r)."""
    w, p = wilcoxon(d)
    nz = d[d != 0]
    ranks = pd.Series(np.abs(nz)).rank().values
    w_plus, w_minus = ranks[nz > 0].sum(), ranks[nz < 0].sum()
    return w, p, (w_plus - w_minus) / (w_plus + w_minus)


def holm(pvals: dict[str, float], alpha: float = 0.05) -> list[tuple[str, float, float, bool]]:
    out, failed = [], False
    for j, name in enumerate(sorted(pvals, key=pvals.get)):
        thr = alpha / (len(pvals) - j)
        failed = failed or pvals[name] >= thr
        out.append((name, pvals[name], thr, not failed))
    return out


def ci(samples: np.ndarray) -> tuple[float, float]:
    lo, hi = np.nanpercentile(samples, [2.5, 97.5])
    return float(lo), float(hi)


def boot_indices(n: int) -> np.ndarray:
    """Same resampled instance sets for every statistic — one fixed-seed draw."""
    rng = np.random.default_rng(SEED)
    return rng.integers(0, n, size=(N_BOOT, n))


def describe_arms(C: pd.DataFrame, R: pd.DataFrame, T: pd.DataFrame, E: pd.DataFrame, idx: np.ndarray) -> None:
    n = len(C)
    print(f"{'arm':3s} {'resolved':>13s} {'95% CI':>17s} {'Σcost':>8s} {'cost/run':>9s} "
          f"{'median':>8s} {'cost/resolved':>13s} {'95% CI':>19s} {'empty':>5s} {'inv_prompt':>10s} {'max_turns':>9s}")
    for k in ARMS:
        r, c = R[k].values, C[k].values
        r_bs = r[idx].mean(1) * 100
        cpr_bs = c[idx].sum(1) / np.where(r[idx].sum(1) == 0, np.nan, r[idx].sum(1))
        print(f"{k:3s} {int(r.sum()):4d}/{n} {r.mean()*100:5.2f}% [{ci(r_bs)[0]:5.2f}; {ci(r_bs)[1]:5.2f}] "
              f"{c.sum():8.2f} {c.mean():9.4f} {np.median(c):8.4f} {c.sum()/r.sum():13.4f} "
              f"[{ci(cpr_bs)[0]:.4f}; {ci(cpr_bs)[1]:.4f}] {int(E[k].sum()):5d} "
              f"{int((T[k] == 'invalid_prompt').sum()):10d} {int((T[k] == 'max_turns').sum()):9d}")


def h1(C: pd.DataFrame, R: pd.DataFrame, idx: np.ndarray) -> float:
    c, r = C.values, R.values  # columns A B C D
    n = len(C)

    def stat(cs: np.ndarray, rs: np.ndarray) -> np.ndarray:
        """cs/rs: (..., 4) column sums → (B+D) − (A+C) cost per resolved; NaN if a group has 0 resolved."""
        with np.errstate(invalid="ignore", divide="ignore"):
            g_str = (cs[..., 1] + cs[..., 3]) / (rs[..., 1] + rs[..., 3])
            g_no = (cs[..., 0] + cs[..., 2]) / (rs[..., 0] + rs[..., 2])
        bad = ((rs[..., 1] + rs[..., 3]) == 0) | ((rs[..., 0] + rs[..., 2]) == 0)
        return np.where(bad, np.nan, g_str - g_no), g_str, g_no

    cs_bs = np.stack([c[idx, j].sum(1) for j in range(4)], axis=-1)
    rs_bs = np.stack([r[idx, j].sum(1) for j in range(4)], axis=-1)
    diff_bs, str_bs, no_bs = stat(cs_bs, rs_bs)
    diff, g_str, g_no = stat(c.sum(0), r.sum(0))
    dropped = int(np.isnan(diff_bs).sum())
    lo, hi = ci(diff_bs)

    print("\n--- H1: cost per resolved, (B+D) vs (A+C)")
    print(f"(B+D): Σcost ${c[:, [1, 3]].sum():.4f} / {int(r[:, [1, 3]].sum())} resolved = ${g_str:.4f}  "
          f"95% CI [{ci(str_bs)[0]:.4f}; {ci(str_bs)[1]:.4f}]")
    print(f"(A+C): Σcost ${c[:, [0, 2]].sum():.4f} / {int(r[:, [0, 2]].sum())} resolved = ${g_no:.4f}  "
          f"95% CI [{ci(no_bs)[0]:.4f}; {ci(no_bs)[1]:.4f}]")
    print(f"difference ${diff:+.4f} ({diff / g_no * 100:+.1f}%)  95% CI [{lo:+.4f}; {hi:+.4f}]  "
          f"bootstrap SE {np.nanstd(diff_bs):.4f}  dropped {dropped}/{N_BOOT} ({dropped / N_BOOT:.1%})")
    print(f"share of bootstrap samples with difference < 0: {np.nanmean(diff_bs < 0):.3f}")
    print(f"CONFIRMED (whole CI < 0): {hi < 0}")

    # decomposition: cost per resolved = (cost per run) / (resolve rate)
    cpr_str, cpr_no = c[:, [1, 3]].mean(), c[:, [0, 2]].mean()
    rate_str, rate_no = r[:, [1, 3]].mean(), r[:, [0, 2]].mean()
    print(f"decomposition: cost/run ${cpr_str:.5f} vs ${cpr_no:.5f} (×{cpr_str / cpr_no:.3f}); "
          f"resolve rate {rate_str*100:.2f}% vs {rate_no*100:.2f}% (×{rate_str / rate_no:.3f}); "
          f"ratio of cost/resolved ×{g_str / g_no:.3f}")

    d = ((C.B + C.D) / 2 - (C.A + C.C) / 2).values
    w, p, r_rb = wilcoxon_signed(d)
    med_bs = np.median(d[idx], axis=1)
    print(f"Wilcoxon over dᵢ = mean(B,D) − mean(A,C) per run: median ${np.median(d):+.5f} "
          f"95% CI [{ci(med_bs)[0]:+.5f}; {ci(med_bs)[1]:+.5f}]  mean ${d.mean():+.5f}  "
          f"dᵢ<0 in {(d < 0).sum()}/{n}  W={w:.0f}  p={p:.3e}  r_rb={r_rb:+.3f}")

    print("exploratory — str_replace effect per arm (cost per resolved):")
    for x, y in (("A", "B"), ("C", "D")):
        jx, jy = ARMS.index(x), ARMS.index(y)
        with np.errstate(invalid="ignore", divide="ignore"):
            e_bs = cs_bs[:, jy] / rs_bs[:, jy] - cs_bs[:, jx] / rs_bs[:, jx]
        e = c[:, jy].sum() / r[:, jy].sum() - c[:, jx].sum() / r[:, jx].sum()
        print(f"  {x}→{y}: ${c[:, jx].sum() / r[:, jx].sum():.4f} → ${c[:, jy].sum() / r[:, jy].sum():.4f}  "
              f"Δ ${e:+.4f}  95% CI [{ci(e_bs)[0]:+.4f}; {ci(e_bs)[1]:+.4f}]")
    with np.errstate(invalid="ignore", divide="ignore"):
        cpr = cs_bs / rs_bs
    inter_bs = (cpr[:, 3] - cpr[:, 2]) - (cpr[:, 1] - cpr[:, 0])
    cpr0 = c.sum(0) / r.sum(0)
    print(f"  interaction (D−C) − (B−A): ${(cpr0[3] - cpr0[2]) - (cpr0[1] - cpr0[0]):+.4f}  "
          f"95% CI [{ci(inter_bs)[0]:+.4f}; {ci(inter_bs)[1]:+.4f}]")
    return p


def h3(R: pd.DataFrame, T: pd.DataFrame, E: pd.DataFrame, repo: pd.Series, idx: np.ndarray) -> None:
    d = (R.B - R.D).values
    bs = d[idx].mean(1) * 100
    lo, hi = ci(bs)
    print("\n--- H3: non-inferiority, R_B − R_D, margin −5 pp")
    print(f"R_B {R.B.mean()*100:.2f}%  R_D {R.D.mean()*100:.2f}%  difference {d.mean()*100:+.2f} pp  "
          f"95% CI [{lo:+.2f}; {hi:+.2f}]  bootstrap SE {bs.std():.2f} pp  CI width {hi - lo:.2f} pp")
    print(f"lower bound − margin: {lo + MARGIN_PP:+.2f} pp  share of bootstrap samples ≤ −5 pp: {(bs <= -MARGIN_PP).mean():.4f}")
    print(f"CONFIRMED (lower bound > −{MARGIN_PP:g} pp): {lo > -MARGIN_PP}   whole CI > 0: {lo > 0}")

    both = int(((R.B == 1) & (R.D == 1)).sum())
    neither = int(((R.B == 0) & (R.D == 0)).sum())
    b = int(((R.B == 1) & (R.D == 0)).sum())
    c = int(((R.B == 0) & (R.D == 1)).sum())
    print(f"2×2: both {both}, neither {neither}, only B {b}, only D {c}  → McNemar p={mcnemar_exact(b, c):.2e}")

    only_b = (R.B == 1) & (R.D == 0)
    print("what D did on the 'only B' instances:",
          T.D[only_b].value_counts().to_dict(), f"empty patch in D: {int(E.D[only_b].sum())}")
    only_d = (R.B == 0) & (R.D == 1)
    print("what B did on the 'only D' instances:",
          T.B[only_d].value_counts().to_dict(), f"empty patch in B: {int(E.B[only_d].sum())}")

    print("exploratory — by repo (resolved B / D / n):")
    g = pd.DataFrame({"repo": repo, "B": R.B, "D": R.D}).groupby("repo").agg(B=("B", "sum"), D=("D", "sum"), n=("B", "size"))
    for name, row in g.sort_values("n", ascending=False).iterrows():
        print(f"  {name:28s} {int(row.B):3d} / {int(row.D):3d} / {int(row.n):3d}  Δ {int(row.B - row.D):+d}")


def families(C: pd.DataFrame, R: pd.DataFrame, L: pd.DataFrame, p_h1: float) -> None:
    d2 = ((C.C + C.D) / 2 - (C.A + C.B) / 2).values
    _, p_h2a, _ = wilcoxon_signed(d2)
    primary = {"Wilcoxon H1": p_h1, "Wilcoxon H2a": p_h2a}
    for x, y in (("A", "C"), ("B", "D")):
        b = int(((L[x] == 1) & (L[y] == 0)).sum())
        c = int(((L[x] == 0) & (L[y] == 1)).sum())
        primary[f"McNemar loc {x}–{y} (b={b}, c={c})"] = mcnemar_exact(b, c)
    print("\n--- Holm, primary family")
    for name, p, thr, ok in holm(primary):
        print(f"  {name:32s} p={p:.3e}  threshold={thr:.4f}  {'passes' if ok else 'fails'}")

    secondary = {}
    for x, y in (("A", "B"), ("C", "D"), ("A", "C"), ("B", "D")):
        b = int(((R[x] == 1) & (R[y] == 0)).sum())
        c = int(((R[x] == 0) & (R[y] == 1)).sum())
        secondary[f"{x}–{y} (b={b}, c={c})"] = mcnemar_exact(b, c)
    print("--- Holm, resolved McNemar (secondary family)")
    for name, p, thr, ok in holm(secondary):
        print(f"  {name:32s} p={p:.3e}  threshold={thr:.4f}  {'passes' if ok else 'fails'}")


def analyze(df: pd.DataFrame, label: str) -> None:
    df = df.copy()
    is_inv = (df.termination_reason == "api_error") & df.error_message.fillna("").str.contains("invalid_prompt")
    df["term"] = np.where(is_inv, "invalid_prompt", df.termination_reason)
    C = pivot(df, "cost").astype(float)
    R = pivot(df, "resolved").astype(int)
    L = pivot(df, "localized").astype(int)
    T = pivot(df, "term")
    E = pivot(df, "empty_patch").astype(int)
    repo = df.drop_duplicates("instance_id").set_index("instance_id").repo.loc[C.index]
    idx = boot_indices(len(C))

    print(f"\n{'#' * 16} {label} (n={len(C)} instances)")
    describe_arms(C, R, T, E, idx)
    p_h1 = h1(C, R, idx)
    h3(R, T, E, repo, idx)
    families(C, R, L, p_h1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("exp_dir", type=Path)
    args = ap.parse_args()
    df = load(args.exp_dir)

    # §2.3: only api_error that is NOT invalid_prompt is infrastructure → excluded by instance
    infra = (df.termination_reason == "api_error") & ~df.error_message.fillna("").str.contains("invalid_prompt")
    infra_ids = set(df.loc[infra, "instance_id"])
    print(f"infrastructure api_error (not invalid_prompt): {int(infra.sum())} runs, {len(infra_ids)} instances excluded")
    analyze(df[~df.instance_id.isin(infra_ids)], "PRIMARY (invalid_prompt = outcome)")

    any_api = set(df.loc[df.termination_reason == "api_error", "instance_id"])
    analyze(df[~df.instance_id.isin(any_api)], "SENSITIVITY (no api_error in any arm)")


if __name__ == "__main__":
    main()
