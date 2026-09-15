# Metrike u SWE-bench logovima

Objašnjenje svakog polja koje piše `evals/swebench/pipeline.py` u
`artifacts/swebench/{logs/*.json, tables/*.csv}`, i po čemu se razlikuje od
starog toy-task runnera (`evals/pipeline.py`).

Za dizajn eksperimenta i agregatne metrike vidi [`METRICS.md`](METRICS.md); ovaj
fajl opisuje **sirovi red** kakav stvarno izlazi.

---

## Referentni red

```json
{
  "run_id": "gpt-5.4-nano__bash/astropy__astropy-12907/0",
  "session_id": "gpt-5.4-nano__bash",
  "model": "gpt-5.4-nano",
  "tools": "bash",
  "toolset_condition": "bash",
  "instance_id": "astropy__astropy-12907",
  "repo": "astropy/astropy",
  "run_index": 0,
  "tests_fail_to_pass_total": 0,  "tests_fail_to_pass_passed": 0,
  "tests_pass_to_pass_total": 0,  "tests_pass_to_pass_passed": 0,
  "resolved": false,  "grade_error": "",
  "empty_patch": false,  "patch_applied": true,
  "patch_files_changed": 1,  "patch_lines_changed": 2,
  "prompt_tokens": 149444,  "completion_tokens": 1359,  "reasoning_tokens": 0,
  "cost": 0.03158755,  "wall_time": 40.86,
  "llm_seconds": 38.2,  "tool_seconds": 1.9,  "calls": 19,
  "crashed": false,  "error_type": "",  "error_message": "",
  "termination_reason": "completed",  "turns_used": 19,  "max_turns": 20,
  "tool_calls_breakdown": "{\"bash\": 18}",  "tool_call_errors": "{}",
  "temperature": 0.0,
  "harness_sha": "2bd7fbe…",  "dataset": "SWE-bench/SWE-bench_Lite",  "split": "test",
  "eval_image": "",  "network": "none",  "ts": 1789058431.69
}
```

> U ovom primeru je pokrenuto sa `--no-grade`, pa su sva `tests_*` polja i
> `resolved` ostala na default-u (grader ih nije popunio). `resolved: false` ovde
> **nije presuda** — znači "još neocenjeno".

---

## Razlike u odnosu na stari `evals` red

| stari `evals` | novi `swebench` | razlog |
|---|---|---|
| `task` | `instance_id` | ime SWE-bench instance umesto imena toy zadatka |
| `ok` (bool iz `check` lambde) | `resolved` | prava SWE-bench presuda umesto ad-hoc provere |
| `uses_bash` / `uses_search` / `uses_str_replace` | `tools`, `toolset_condition` | eksplicitna lista alata (sad ih ima 5+), ne 3 boola |
| `total_tokens` | — | izbačeno; računa se kao `prompt_tokens + completion_tokens` |
| — | sva ostala polja niže | nova |

---

## Ko puni koje polje

- **harness** (`pipeline.py`, pre/oko run-a): `run_id`, `session_id`, `model`,
  `tools`, `toolset_condition`, `instance_id`, `repo`, `run_index`,
  `temperature`, `harness_sha`, `dataset`, `split`, `network`, `ts`, `max_turns`.
- **agent** (`harness/agent.py`, tokom run-a): `prompt_tokens`,
  `completion_tokens`, `reasoning_tokens`, `cost`, `calls`, `turns_used`,
  `termination_reason`, `tool_calls_breakdown`, `tool_call_errors`, `wall_time`,
  `llm_seconds`, `tool_seconds`, `crashed`, `error_type`, `error_message`.
- **predict** (`predict.extract`, posle run-a): `empty_patch`, `patch_applied`,
  `patch_files_changed`, `patch_lines_changed`.
- **grader** (`grade.grade`, zvanični `swebench` evaluator): `resolved`,
  `tests_fail_to_pass_total`, `tests_fail_to_pass_passed`,
  `tests_pass_to_pass_total`, `tests_pass_to_pass_passed`, `eval_image`,
  `grade_error`.

---

## Polja po grupama

### Identitet / grupisanje

| polje | opis |
|---|---|
| `run_id` | jedinstven ključ reda: `<session_id>/<instance_id>/<run_index>`. Za spajanje sa rezultatima ocenjivanja i za pairing između uslova. |
| `session_id` | `<model>__<alati-sortirano-i-spojeno>`, npr. `gpt-5.4-nano__bash`. Jedan skup alata = jedna sesija. |
| `model` | ime modela (i ključ u `MODEL_PRICING`). |
| `tools` | alati dati agentu u ovom run-u, spojeni `+` (`bash+search+str_replace`). |
| `toolset_condition` | ista lista, sortirana — kratka labela uslova za tabele/grafiku. |
| `instance_id` | SWE-bench instance (`astropy__astropy-12907`). |
| `repo` | GitHub repo instance (`astropy/astropy`). Omogućava presek "resolve rate po projektu". |
| `run_index` | redni broj ponavljanja (`0..repeats-1`); za pass@k i varijansu. |

### Ishod — testovi (puni grader)

| polje | opis |
|---|---|
| `tests_fail_to_pass_total` | broj testova u `FAIL_TO_PASS` skupu — testovi koji su crveni pre fixa, treba da pozelene. |
| `tests_fail_to_pass_passed` | koliko njih je prošlo posle agentovog patcha (+ skrivenog `test_patch`). |
| `tests_pass_to_pass_total` | broj testova u `PASS_TO_PASS` — bili zeleni, moraju ostati zeleni (regresija-check). |
| `tests_pass_to_pass_passed` | koliko njih je i dalje prošlo. |
| `resolved` | **glavna metrika.** `true` samo ako `fail_to_pass_passed == fail_to_pass_total` **i** `pass_to_pass_passed == pass_to_pass_total`. |
| `grade_error` | prazno kad je evaluator stvarno ocenio instancu. Kad nije — razlog (prva `ERROR` linija iz evaluatorovog `run_instance.log`, npr. `Image sweb.eval.… not found`). **Bez ovoga se run koji nikad nije ocenjen ne razlikuje od run-a koji je pao na svim testovima** — oba izgledaju kao `0/0` + `resolved: false`. Uvek proveri ovo polje pre nego što `0/0` protumačiš kao presudu. |

### Patch — šta je agent proizveo (puni `predict`)

| polje | opis |
|---|---|
| `empty_patch` | `git diff` prazan — agent nije napravio nijednu izmenu. Odvaja "nije ni pokušao" od "pokušao pa promašio". |
| `patch_applied` | da li se generisani diff čisto primenjuje (`git apply --check`); hvata malformisan patch. |
| `patch_files_changed` | broj izmenjenih fajlova. |
| `patch_lines_changed` | dodate + obrisane linije; signal veličine izmene. |

### Troškovi izvršavanja (puni agent)

| polje | opis |
|---|---|
| `prompt_tokens` | ulazni tokeni, zbir preko svih LLM poziva u run-u. |
| `completion_tokens` | izlazni tokeni. |
| `reasoning_tokens` | reasoning tokeni; 0 za modele bez vidljivog reasoninga, bitno pri poređenju sa većim modelima. |
| `cost` | USD, iz `MODEL_PRICING` (`prompt·in + completion·out`). |
| `wall_time` | sekunde od početka `run_one` do kraja (uklj. checkout i sandbox). |
| `llm_seconds` | od toga, sekunde provedene čekajući LLM completion pozive (`agent.usage.llm_time_seconds`). |
| `tool_seconds` | od toga, sekunde provedene izvršavajući tool pozive u sandboxu. |
| `calls` | broj LLM completion poziva. |

### Terminacija / stabilnost

| polje | opis |
|---|---|
| `termination_reason` | `completed` (model sam prestao da zove alate), `max_turns` (potrošen limit poteza), `wall_timeout` (probijen `--run-timeout`), `api_error` (provider odbio / rate limit — partial patch se svejedno čuva), `crash` (pao checkout/sandbox setup). |
| `turns_used` | koliko LLM poteza je stvarno potrošeno. |
| `max_turns` | limit poteza koji je važio (`--max-turns` ili `settings.swebench_max_turns`). |
| `crashed` | `true` samo za grešku u setup-u harness-a; `api_error` **nije** `crashed`. |
| `error_type` | ime izuzetka (`BadRequestError`, `RuntimeError`, …), inače `""`. |
| `error_message` | jedan red sažetka prave greške (status kod + poruka sa API-ja, obrezano na ~300 karaktera). Pun detalj (status_code, request_id, `body`, `response.text`, traceback) ide u `errors/<session_id>__<instance_id>__<run_index>.json`, samo ako je nešto stvarno palo. |
| `invalid_prompt_retries` | koliko puta je provider-ov moderation klasifikator odbio prompt (`code: "invalid_prompt"`) koji je zatim **nepromenjen** ponovo poslat i prošao. `0` = klasifikator se nije ni oglasio; `>0` = run je završen **samo zahvaljujući** retry-ju. Run koji je retry-ovao pa ipak pao nema red sa rezultatom, pa svoj broj pokušaja nosi u `errors/<run>.json` (isto ime polja). Zbirno preko ove kolone i tih fajlova dobija se odgovor na otvoreno pitanje iz [ISSUES.md](../todo/ISSUES.md) #2 — da li je flag nedeterminističan: ako retry često prolazi, jeste; ako nikad ne prolazi, sadržaj je tvrdo blokiran. |

### Ponašanje alata (poenta ablacije)

| polje | opis |
|---|---|
| `tool_calls_breakdown` | JSON string, broj poziva po alatu: `{"bash": 18}`. |
| `tool_call_errors` | JSON string, broj poziva po alatu koji su vratili grešku (`ERROR…` / `Unknown tool`). |

### Proveniencija (konstanta po sesiji, ali se loguje po redu)

| polje | opis |
|---|---|
| `temperature` | sampling temperatura zaista poslata API-ju preko `--temperature`; `null`/prazno znači da parametar **nije poslat uopšte** (provider koristi svoj default), ne da je poslato 0.0 — to dvoje je namerno razdvojeno u koloni. Uvek `null` kad je `reasoning_effort` postavljen (reasoning modeli odbijaju ovaj parametar). |
| `harness_sha` | `git rev-parse HEAD` harness-a u trenutku run-a — reproducibilnost. |
| `dataset` | `SWE-bench/SWE-bench_Lite`. |
| `split` | `test`. |
| `eval_image` | Docker image koji je grader koristio za instance (npr. `swebench/sweb.eval.x86_64.astropy_1776_astropy-12907`); prazno dok se ne ocenjuje. |
| `network` | mrežna politika sandboxa; `none` = agent nema internet (da ne nađe upstream fix). |
| `ts` | unix vreme upisa reda. |
