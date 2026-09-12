# `run_swebench.py` — CLI

Pokreće agenta na SWE-bench Lite instancama, izvlači patch po instanci, opciono
ga oceni zvaničnim `swebench` evaluatorom, i upiše rezultate.

```
.venv/bin/python scripts/run_swebench.py [opcije]
```

Defaulti dolaze iz `evals/swebench/config.py` (`SweBenchSettings`), override kroz
env sa prefiksom `SWEBENCH_` (npr. `SWEBENCH_SEED=42`).

---

## Eksperiment

| flag | default | opis |
|---|---|---|
| `--model` | `gpt-5.4-nano` | ime modela; mora imati unos u `MODEL_PRICING` (`harness/config.py`) |
| `--split` | `test` | particija dataseta: `test` (300 instanci, pravi benchmark) ili `dev` (23, za razvoj) |
| `--name` | — | ime eksperimenta; folder je `<timestamp>_<name>`, inače `<timestamp>_<model>` |
| `--reasoning-effort` | — (isključeno) | `minimal` \| `low` \| `medium` \| `high`. Uključi model reasoning; kad je zadato, `temperature` se ne šalje |
| `--repeats` | `1` | koliko puta pustiti svaku (toolset × instanca) kombinaciju; `>1` za pass@k / varijansu |
| `--artifacts-dir` | `./artifacts` | koren za izlaz |

## Instance selection — koje instance pustiti

Prvo `--split` odredi bazen (300 ili 23), pa ovo bira podskup iz njega.

| flag | opis |
|---|---|
| *(nijedan)* | **sve** instance iz splita |
| `--limit N` | prvih N po abecednom `instance_id` — deterministički (uvek iste, astropy prve). Za brzi dim-test |
| `--sample N` | N **nasumično** izabranih. Reprezentativnije od `--limit` (nije samo jedan repo) |
| `--seed S` | seed za `--sample` (default `0`) — fiksira izbor, reproducibilno |
| `--instances a,b,c` | tačno te instance po ID-u (`astropy__astropy-12907,django__django-11039`) |
| `--repos o/r,o/r` | samo instance iz tih repoa (`psf/requests` — mali repo, brz checkout) |

Pravila:
- `--limit` i `--sample` se **isključuju**
- `--repos` se kombinuje sa `--sample`/`--limit`: `--sample 10 --repos django/django` = 10 random django instanci
- `--instances` je eksplicitna lista — ignoriše `--limit`/`--sample`/`--repos`

## Toolsets

| flag | default | opis |
|---|---|---|
| `--tools t1 t2 …` | `bash search str_replace read_file find_file` | *univerzum* alata; generiše **svaki** neprazan podskup koji sadrži `bash` → svaki podskup je jedna sesija |
| `--combo a,b` | — | eksplicitna kombinacija, ponovljivo (`--combo bash --combo bash,search`); **zaobilazi** `--tools` |

> Pažnja: default `--tools` (5 alata) → 2⁴ = **16 toolset-ova**. Uz `--repeats` i
> broj instanci to je mnogo run-ova. Za ablaciju obično suzi na par `--combo`.

`run_tests` nije u default univerzumu — v1 radi "na slepo" u `agent-sandbox` bez
zavisnosti repoa, pa `run_tests` nema smisla (vidi
`SWEBENCH_INTEGRATION_STATUS.md`).

## Run params

| flag | default | opis |
|---|---|---|
| `--max-turns N` | `40` | limit LLM poteza po run-u |
| `--run-timeout S` | `1800` | wall-clock sekundi po instanci; probijanje → `termination_reason=wall_timeout`, partial patch se čuva |
| `--max-workers N` | `4` | paralelizam **zvaničnog evaluatora** (ne agenta). Svaki eval kontejner traži 2+ GB RAM — spusti na `2` ako je memorija tesna |
| `--no-grade` | — | samo napravi `predictions.jsonl`, preskoči ocenjivanje |

Ocenjivanje traži pip paket: `uv sync --group swebench`. Prvi grade po repou
gradi/povlači Docker image (~1–2 GB, 20–40 GB diska ukupno za više repoa).

---

## Izlaz

```
artifacts/swebench/
  MANIFEST.jsonl                          # globalni append-only ledger, 1 linija po eksperimentu
  experiments/<timestamp>_<name|model>/
    manifest.json                         # config + totals + rollup po sesiji
    rows.jsonl                            # 1 run po redu (bogat: dict polja kao objekti)
    rows.csv                             # isto, ravno (dict polja kao JSON string)
    conversations/<sesija>__<instance>__<run>.md
    messages/<sesija>__<instance>__<run>.json   # tačan request payload (model, tools, messages) — za replay
    errors/<sesija>__<instance>__<run>.json     # pun detalj greške, SAMO ako je run pao (status_code, body, traceback…)
    predictions/<sesija>.jsonl            # zvanični SWE-bench format
    grading/<sesija>/…                    # izlaz run_evaluation (kad ima --grade)
  work/<exp_id>/…                         # glomazni checkout-ovi, van results stabla
```

Polja u redu: vidi `METRICS_SWE.md`. Agregatne metrike: `METRICS.md` + `summarize`
se ispiše na kraju svakog run-a.

### Dijagnostika `api_error` run-a

Kad `termination_reason` bude `api_error`, `errors/<run>.json` ima pravi razlog sa
API-ja (`status_code`, `request_id`, `body`, `response.text`). Da bi se to
ponovilo bez ponovnog pokretanja celog agenta, pošalji tačno taj payload
ponovo:

```
.venv/bin/python scripts/replay_request.py \
    artifacts/swebench/experiments/<exp>/messages/<sesija>__<instance>__<run>.json
```

`--bisect` binarnom pretragom nađe najkraći prefiks poruka koji i dalje pada
(nikad ne seče u sredini `tool_calls` bloka), `--prefix N` šalje samo prvih N
poruka ručno.

---

## Primeri

Najmanji dim-test (bez ocenjivanja, 1 instanca, bash):
```
.venv/bin/python scripts/run_swebench.py --limit 1 --combo bash --no-grade --name smoke
```

Brzi prolaz na dev skupu, dve kombinacije alata:
```
.venv/bin/python scripts/run_swebench.py --split dev --sample 5 \
    --combo bash --combo bash,search --name dev_check
```

Reprezentativni uzorak, pun default univerzum alata, sa ocenjivanjem:
```
.venv/bin/python scripts/run_swebench.py --sample 20 --seed 0 \
    --tools bash search str_replace --max-workers 2 --name ablation_s20
```

Sa reasoning-om:
```
.venv/bin/python scripts/run_swebench.py --sample 20 --seed 0 --combo bash \
    --reasoning-effort medium --name reason_med
```

Pun benchmark (svih 300, svi default toolset-ovi, 1 run svaki):
```
.venv/bin/python scripts/run_swebench.py --name full_run
```

---

## GUI helper

`scratch/swebench_cli_builder.html` (gitignored) — klikćeš polja, dole se ispiše
validna komanda, kopiraš u terminal. Ništa ne pokreće.
