# SWE-bench Lite — struktura dataseta

`SWE-bench/SWE-bench_Lite` je **benchmark**, ne skup za treniranje. Ništa se ne
fituje na njemu — model je zamrznut LLM, jedino što se "šteluje" je harness
(prompt, koji alati agent ima). Ovaj fajl objašnjava splitove i šta znači svaka
kolona u redu, kao dopunu `CLI.md` (koji objašnjava `--split` sa strane CLI-ja).

---

## Splitovi

| split | broj instanci | čemu služi |
|---|---|---|
| `test` | **300** | zvanični skup — na ovome se prijavljuju rezultati (diplomski brojevi idu odavde) |
| `dev` | **23** | mali skup sa strane, za razvoj harness-a (prompt, alati) bez čekanja na 300 i bez "overfit"-a na test probleme |

To je sve za **Lite**. Za poređenje:
- puni `SWE-bench` (ne-Lite) ima i `train` (~19k instanci) — koristi se za fine-tuning agenata u nekim radovima, Lite ga nema
- `SWE-bench_Verified` ima samo `test` (500, ručno provereno da su rešivi)

### Zašto se zove "test" ako se ne trenira

Naziv je nasleđen iz HuggingFace `datasets` konvencije gde se glavna particija
zove `test`. Za benchmark to prosto znači "zvanični set problema na kom se meri
rezultat". `dev` postoji da agent/harness ne bude prilagođavan (svesno ili ne)
baš na te 300 test instance dok se razvija.

### Kad koristiti koji

- **razvoj pipeline-a / provera da grading radi** → `--split dev` (23 instance, par repoa, mnogo brže, jeftinije)
- **diplomski brojevi, ablacija alata** → `--split test`

---

## Poreklo instanci

Svaki red = jedan pravi GitHub issue + PR koji ga je rešio, mineran iz 12
popularnih Python repoa: `django`, `sympy`, `scikit-learn`, `astropy`, `flask`,
`requests`, `xarray`, `pylint`, `pytest`, `sphinx`, `seaborn`, `matplotlib`.

**Lite** je kurirani podskup od 300 iz punog SWE-bench test skupa (~2.3k
instanci), filtriran na jasnije issue-e i manje/fokusiranije patch-eve — lakše
za agenta, jeftinije za evaluaciju.

---

## Kolone po redu

Podeljene po tome ko ih koristi u ovom harness-u (`evals/swebench/steps/dataset.py`
uzima samo prvih 6; ostatak čita zvanični evaluator direktno iz dataseta).

### Agent input (`INSTANCE_FIELDS`)

| kolona | opis |
|---|---|
| `instance_id` | jedinstveni id, `<repo_slug>-<broj>` (npr. `astropy__astropy-12907`) |
| `repo` | GitHub repo, `owner/name` |
| `base_commit` | commit **pre** fixa — stanje koda koje agent dobija |
| `problem_statement` | tekst issue-a — jedini opis problema koji agent vidi |
| `version` | verzija projekta u tom trenutku (za environment setup) |
| `image` | tag zvaničnog Docker image-a sa instaliranim zavisnostima za tu instancu (`swebench/sweb.eval.x86_64.<instance_id>`) |

### Scoring only — agent ovo NE sme da vidi

| kolona | opis |
|---|---|
| `patch` | zlatni fix — diff PR-a bez testova. Čisto referenca/oracle, nikad se ne prosleđuje agentu ni u prompt ni u mount |
| `test_patch` | testovi koje je PR dodao/izmenio da dokaže da je fix radi. Primenjuje se **tek posle** agenta, u grading fazi |
| `FAIL_TO_PASS` | lista test node-id-eva koji padaju pre fixa, moraju da prođu posle (dokaz da je bug rešen) |
| `PASS_TO_PASS` | lista testova koji već prolaze i moraju ostati da prolaze (regresiona zaštita) |
| `eval_script` | skripta koju zvanični evaluator pokreće da izvrši testove u kontejneru |
| `log_parser` | kako parsirati izlaz testova za taj projekat (svaki repo ima drugačiji test runner/format) |
| `environment_setup_commit` | commit sa kog se instalira okruženje (može se razlikovati od `base_commit`) |
| `created_at`, `difficulty`, `hints_text` | metapodaci — datum, procenjena težina, dodatni nagoveštaji iz diskusije na issue-u |

---

## Veza sa ostatkom harness-a

- `evals/swebench/steps/dataset.py::load_instances` čita samo agent-input kolone (§ gore) — `test_patch`/F2P/P2P nikad ne dolaze na host stranu koda koju agent može da dotakne (audit `AUDIT_REPORT.md` §1).
- `evals/swebench/steps/grade.py::grade` prosleđuje `--dataset_name SWE-bench/SWE-bench_Lite` zvaničnom evaluatoru, koji sam čita `test_patch`/F2P/P2P/`eval_script`/`log_parser` iz dataseta — harness ih nikad ne parsira ručno.
- `resolved` (glavna metrika, `METRICS_SWE.md`) = svi `FAIL_TO_PASS` prošli **i** svi `PASS_TO_PASS` i dalje prolaze, posle primene agentovog patcha + `test_patch`.
