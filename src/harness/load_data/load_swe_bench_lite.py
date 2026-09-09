import pandas as pd

splits = {'test': 'data/test-00000-of-00001.parquet', 'dev': 'data/dev-00000-of-00001.parquet'}
df_swe = pd.read_parquet("hf://datasets/SWE-bench/SWE-bench_Lite/" + splits["test"])