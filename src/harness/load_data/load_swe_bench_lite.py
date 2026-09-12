import pandas as pd

_HF_BASE = "hf://datasets/SWE-bench/SWE-bench_Lite/"
_SPLITS = {
    "test": "data/test-00000-of-00001.parquet",
    "dev": "data/dev-00000-of-00001.parquet",
}


def load_raw(split: str = "test") -> pd.DataFrame:
    """SWE-bench Lite split as a DataFrame. Needs pyarrow + huggingface_hub."""
    if split not in _SPLITS:
        raise ValueError(f"unknown split {split!r}; known: {sorted(_SPLITS)}")
    return pd.read_parquet(_HF_BASE + _SPLITS[split])
