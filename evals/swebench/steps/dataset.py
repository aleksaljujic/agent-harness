import random

from evals.swebench.config import INSTANCE_FIELDS, swe_settings
from harness.load_data.load_swe_bench_lite import load_raw

# Test columns are left out; the evaluator reads them from the dataset itself.
_FIELDS = INSTANCE_FIELDS


def load_instances(split="test", ids=None, limit=None, repos=None,
                   sample=None, seed=None) -> list[dict]:
    """Select instances from a SWE-bench Lite split.

    `limit` takes the first N by instance_id; `sample` takes N at random
    (`seed` defaults to `swe_settings.seed`). The two are mutually exclusive.
    Output is always sorted by instance_id.
    """
    if limit is not None and sample is not None:
        raise ValueError("pass only one of limit / sample")
    if seed is None:
        seed = swe_settings.seed

    df = load_raw(split)

    if ids:
        wanted = list(ids)
        df = df[df.instance_id.isin(wanted)]
        missing = set(wanted) - set(df.instance_id)
        if missing:
            raise ValueError(f"instance ids not in {split!r}: {sorted(missing)}")
    if repos:
        df = df[df.repo.isin(list(repos))]

    df = df.sort_values("instance_id")

    if sample is not None:
        pool = list(df.instance_id)
        if sample > len(pool):
            raise ValueError(f"sample {sample} > {len(pool)} available instances")
        picked = set(random.Random(seed).sample(pool, sample))
        df = df[df.instance_id.isin(picked)].sort_values("instance_id")
    elif limit is not None:
        df = df.head(limit)

    return [{k: row[k] for k in _FIELDS} for _, row in df.iterrows()]
