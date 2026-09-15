# SWE-bench evaluator — kompletna konverzacija

Nastavak [docs/research/REZIME.md](../research/REZIME.md) (koji pokriva izgradnju
osnovnog harness-a — petlja, sandbox, alati, toy evali) za deo koji taj fajl
izričito označava kao nepostojeći u trenutku pisanja: SWE-bench Lite integracija
(`evals/swebench/`). Ovaj fajl hvata kako je ta integracija zapravo puštena u rad —
dijagnoza, popravke, i šta je ostalo otvoreno — organizovano po fazama, istim stilom
kao original.

---

## 1. Prva dijagnoza — zašto je 15-run eksperiment vratio 0% resolved

**Pitanje:** kako su ovoliko loši rezultati?

Tri odvojena nalaza, ne jedan uzrok:

1. **`swebench` paket nije instaliran.** Deklarisan je kao poseban
   `dependency-group` u `pyproject.toml`, ne kao osnovna zavisnost — `uv sync` ga ne
   povlači po default-u. Bez njega `grade.grade()` poziva
   `python -m swebench.harness.run_evaluation` kao subprocess, koji odmah pukne
   (`ModuleNotFoundError`), pa `grade.grade()` tiho vraća `_blank()` za svaku
   instancu. `resolved=False`, `tests_*_total=0` svuda — nerazlučivo od modela koji
   je stvarno pao na svakom testu.
2. **`django__django-11630` i `scikit-learn__scikit-learn-14087` bacaju
   `BadRequestError`.** Prvobitna tvrdnja da padaju "kroz sva tri toolset-a" bila je
   pogrešna — provereno iz `rows.jsonl`: 3 pada / 15 run-ova, nedeterministički,
   nekorelisano sa veličinom payload-a (2,553-tokenski zahtev pao, 313,203-tokenski
   prošao negde drugde).
3. **`str_replace` ima visok error rate.** Svih 20 padova vratilo je identičnu
   poruku: `ERROR: old_str appears 2 times, must be unique. Include more
   surrounding lines.`

Sva tri su upisana u novo-napravljen `docs/todo/TODO.md` (kasnije preimenovan u
`ISSUES.md`) kao živi log nalaza — obrazac koji se zadržao kroz ceo ostatak rada:
svaka stavka nosi dokaz, root cause, i šta je konkretno urađeno, ne samo naslov.

---

## 2. BadRequestError istraga — plan mode i implementacija

**Problem:** root cause je bio **nedijagnostifikovljiv**. `_run_agent_bounded` u
`evals/swebench/pipeline.py` čuvao je samo `type(e).__name__` i bacao telo greške sa
servera; transkripti su bili renderovani markdown, ne payload spreman za replay.

Plan (odobren kroz plan mode) podeljen na tri dela:

**Deo A — učiniti 400 self-diagnosing:**
- `_run_agent_bounded` sad vraća pun detalj greške (`status_code`, `request_id`,
  `body`, `response.text`, traceback) — čuva se po run-u u `errors/<run>.json`,
  sažeto u novoj `RunRow.error_message` koloni.
- Ceo message-list svakog run-a se čuva u `messages/<run>.json` za byte-exact
  replay.
- Novi `scripts/replay_request.py` — ponovo šalje sačuvan payload
  (`--prefix N`, `--bisect` binarno pretražuje minimalni payload koji i dalje
  pada) i ispisuje serverov pravi odgovor.
- Usput nađen i popravljen stvaran bug, nezavisan od gornjeg: `agent.py:72` je
  appendovao sirov OpenAI SDK `ChatCompletionMessage` objekat nazad u
  `messages` umesto čistog `{role, content, tool_calls}` dict-a —
  response-only polja (`refusal`, `annotations`, `audio`, deprecated
  `function_call`) su se ehoovala nazad ka API-ju sledećeg poziva. Popravljeno
  kroz `providers/base.py` (`CompletionResult.assistant_message`),
  `providers/openai_provider.py` (gradi čist dict), `agent.py:72`.

**Deo B — `str_replace` da može da razreši dvosmislenost:**
Root cause potvrđen: u `sphinx/ext/autodoc/__init__.py`, `DataDocumenter` (~1704) i
`AttributeDocumenter` (~2095) drže bajt-identične ~14-linijske blokove. Stara
poruka greške nije imenovala brojeve linija i savetovala je proširivanje
**nadole** — što nikad ne razrešava dvosmislenost jer je duplirani blok
identičan i ispod. Model je petljao isti poziv do `max_turns`, 20 puta.

Popravljeno u `src/harness/scripts/str_replace.py` +
`src/harness/tools/str_replace.py`: poruka sad imenuje broj linije svakog
pogotka i savetuje proširivanje **naviše**; dodati opcioni `replace_all` i
`occurrence` argumenti da model ima izlaz koji ne zavisi od pronalaska
jedinstvenog anchor-a.

**Deo C — susedni bugovi koji su gladovali model informacijama:**
- `src/harness/tools/search.py` — `grep --include` poredi samo basename, pa
  glob sa `/` (pun path fajla) tiho nije pogađao ništa; sad se glob sa `/`
  koristi kao meta pretrage umesto kao `--include`.
- Isti fajl — prazan rezultat prijave garda nikad nije pogađao stvarni string
  koji `sandbox.run` vraća za čist prazan match (`"Without return, exit = N"`),
  pa je to curilo modelu umesto `"No matches."`.
- `src/harness/sandbox.py` — izlaz komande se tiho sekao na 8000 karaktera bez
  markera; sad dodaje `... [truncated N more chars; narrow the command]`.

**Usput uklonjeno:** nepraćen, pokvaren duplikat `evals/swebench/` sedeo je na
root-u repo-a kao `swebench/` (sopstveni `pipeline.py`, `grade.py`, itd.,
uvozeći module koji ne postoje). Pošto je imao `__init__.py` (pravi paket, ne
namespace paket) na root-u, a `scripts/run_swebench.py` eksplicitno dodaje root
na `sys.path`, taj direktorijum bi **zasenio pravi pip `swebench` evaluator** za
svaki proces — što bi držalo TODO #1 pokvarenim čak i posle `uv sync --group
swebench`. Obrisan uz odobrenje.

---

## 3. Prvi pravi graded run — dva nova nalaza infrastrukture

Posle `uv sync --group swebench` (korisnik ga instalirao ručno), prvi run sa
uključenim gradingom (`20260912_031417_smoke_test`) otkrio je:

**Grading "radi", ali instanca ostaje neocenjena bez ijedne vidljive greške u
`rows.csv`:**

```
03:15:04 - Image not found locally, attempting to pull...
03:25:16 - ERROR - Image swebench/sweb.eval.x86_64.astropy_1776_astropy-12907 not found
```

Image postoji na registry-ju (potvrđeno `docker manifest inspect`) — samo je
**4.16 GB**, a evaluatorov interni pull je odustao tačno posle 10 minuta. Ručnim
pull-om i ponovnim gradingom nad istim predikcijama dobijen je pravi verdikt
(F2P 0/2, P2P 13/13). Upisano kao TODO #6 (kasnije proširen u #7, #8 — vidi
niže).

**`grade_error` je računat ali odbačen.** `grade.py`'s `_blank()` je računao
razlog, ali `RunRow.GRADE_FIELDS` (šta se kopira sa gradera na red) to polje
nije sadržao, i `RunRow` (pydantic, `extra="forbid"`) ga nije ni imao —
neocenjen run je izgledao identično kao run koji je stvarno pao na svim
testovima. Dodato: `RunRow.grade_error`, `GRADE_FIELDS` unos, i
`_instance_log_error()` koji izvlači prvu `ERROR` liniju iz evaluatorovog
`run_instance.log` kad `report.json` ne postoji.

---

## 4. Pravi uzrok BadRequestError-a — provider-side moderation false positive

**Pitanje:** deluje kao da je i dalje loše?

Re-run sveže `django-16816` instance na build-u koji već sadrži `agent.py`
echo-fix iz Dela A i dalje je pukao sa `api_error`. Novo uhvaćen
`errors/<run>.json` je otkrio pravi uzrok:

```
status_code: 400, code: "invalid_prompt"
message: "Invalid prompt: your prompt was flagged as potentially violating
our usage policy."
```

Znači: teorija o sirovom SDK echo-u **nije bila** (jedini) uzrok — reprodukovala
se na već popravljenom kodu. Inspekcija cele konverzacije do padajuće poruke
otkrila je samo običan Django kod i stack trace (`FieldDoesNotExist`,
`ManyToManyField`) — ništa što liči na stvarno kršenje pravila. Najbolje
tumačenje: lažno pozitivan rezultat, verovatno okinut gustinom
`raise`/`Exception`/traceback obrazaca pomešanih sa instrukcijama tipa
"locate the cause... resolve the issue", koji mogu da liče na
prompt-injection heuristike koje klasifikator traži.

Ovo je provider-side i nije nešto što se popravlja u harness kodu direktno.
Otvoreno: da li je nedeterminističko (probati identičan sačuvan payload
ponovo preko `replay_request.py`), i da li pipeline treba auto-retry baš za
`code == "invalid_prompt"` (za razliku od pravog 400, koji je deterministički
i ne sme se retry-ovati — vidi Deo A5 plana).

**Kako se proverava zašto prompt krši pravila** (objašnjeno naknadno):
`replay_request.py --bisect` izoluje koja tačno poruka okida flag; ta poruka
se onda može poslati na poseban `/v1/moderations` endpoint koji (za razliku od
completions endpoint-a) vraća kategorije i skorove; identičan payload poslat
više puta potvrđuje ili obara non-determinizam.

---

## 5. Kloniranje repo-a i Docker disk analiza

Da bi se testiralo preko više repo-a, otkriveno je da se git mirror-i
repo-a keširaju automatski (`evals/swebench/steps/provision.py::_mirror`) u
`~/.cache/agent-harness/repos/` — prvi susret sa repo-om klonira
(`git clone --mirror`), svaki sledeći samo `fetch`.

Provereno preko `datasets.load_dataset("SWE-bench/SWE-bench_Lite")`: **300
instanci, 12 unikatnih repo-a** (django 114, sympy 77, matplotlib 23,
scikit-learn 23, pytest 17, sphinx 16, astropy/requests/pylint 6, xarray 5,
seaborn 4, flask 3). Svih 12 klonirano (ukupno ~4.1GB izvornog koda — jeftino).

**Bitna distinkcija, otkrivena kroz pitanje "da li grading koristi lokalni
repo":** git mirror keš služi **samo** agentovom sandbox-u tokom same agentove
sesije. Grading Docker kontejner ima **svoj sopstveni** checkout zapečen u
image-u, potpuno odvojen od host filesystem-a — kloniranje repo-a ne utiče
uopšte na ispravnost grading rezultata. Ovo je potvrđeno pregledom celog
`run_instance.log` za `astropy__astropy-12907`: `Git diff before/after`
pokazuje agentov patch primenjen unutar kontejnera, `Test runtime: 66.04
seconds` sa konkretnim imenima testova — stvarno izvršeni testovi, ne keširan
rezultat.

Docker eval image je odvojen po **instanci**, ne po repo-u (svaka instanca
nosi ~2-4GB unikatan sloj + ~2.2GB deljen). Sa samo ~31GB slobodnog prostora,
50 novih instanci bi tražilo grubo 100-200GB — upisano kao TODO #7 (pre-warm
odluka).

---

## 6. Lažni "Image not found" — TODO #8

Tokom smoke-testa `scikit-learn__scikit-learn-10297`, evaluator je prijavio
`Image not found locally, attempting to pull...` i ostao zaglavljen na toj
liniji 12+ minuta — bez greške, bez napretka. `docker system df -v` je
pokazao da image **stvarno postoji lokalno** (5.34GB, star 4 nedelje).
Procesi ubijeni ručno (`kill`).

Ovo je gore od TODO #6 (hladan pull koji samo sporo traje) — ovde detekcija
samog evaluatora daje lažan negativan rezultat, pa pre-pull možda ne bi ni
pomogao ako je problem u samoj detekciji, ne u odsustvu image-a. Ostalo
otvoreno: da li se ponavlja, i da li je u pitanju naming/tag mismatch u
evaluatorovoj proveri.

---

## 7. Plan za veći batch — `EVAL_PREP.md`

Pre pokretanja preko 50 instanci, napravljen `docs/todo/EVAL_PREP.md` sa
planom u 6 koraka: eksplicitni `--combo` (bez njega, `all_tool_combinations`
generiše **16 kombinacija** po instanci umesto 1 — `TOOL_UNIVERSE` ima 5
alata, 2⁴ podskupova koji sadrže `bash`), disk provera pre gradinga,
`--no-grade` prva faza (jeftino, ~$0.0154/run, ~32s/run na osnovu post-fix
uzoraka), grading u talasima sa `docker prune` između, opcija split-a preko
dva laptopa (agent ovde, grading tamo gde ima diska), i lista otvorenih
odluka — uključujući da trenutno **ne postoji** `--grade-only` CLI opcija, pa
bi ponovno pokretanje pune pipeline bez nje ponovo platilo API pozive.

---

## 8. Dokumentacija alata — `TOOLS.md`

Napisan `docs/agent/TOOLS.md` sa detaljnim opisom svih 6 alata (`bash`,
`search`, `str_replace`, `read_file`, `find_file`, `run_tests`) — argumenti,
tačno ponašanje handlera, greške. Usput primećeno: `bash`-ov `DEFINITION`
traži `thought` kao obavezan JSON parametar, ali `BashArgs` pydantic model to
polje nema — pydantic ga tiho odbacuje (nema `extra="forbid"`), model ga mora
poslati jer schema to zahteva, ali harness ga nigde ne koristi.

---

## 9. Eksterni review — `RECOMMENDATION.md`

Pre glavnog eksperimenta, spoljni review protokola (sačuvan u
`docs/RECOMMENDATION.md`) identifikovao je dva kritična rizika, oba naknadno
**potvrđena** čitanjem koda:

**🟥 `str_replace` je eksplicitno favorizovan sistemskim promptom.**
`evals/swebench/prompt.py:8` doslovno sadrži `"...you MUST use str_replace (if
available), one call per change..."`. Ako je hipoteza "dodavanje str_replace
poboljšava efikasnost", trenutni eksperiment ne meri `tool available vs.
unavailable` nego `tool available + instructed to use it vs. unavailable` —
legitiman eksperiment, ali mora se tako i zvati. Predlog: isti prompt za sve
uslove, bez `MUST use`, plus beleženje `str_replace_available` /
`str_replace_used` za intent-to-treat i usage analizu odvojeno.

**🟥 `repeats > 1` tiho baca sve repeate osim poslednjeg.** Root-caused do
tačne linije **u samom pip-installed `swebench` paketu**, ne samo u našem
kodu: `evals/swebench/steps/predict.write_predictions` piše po jedan red za
svaki `(instance_id, run_index)`, pa `predictions.jsonl` sa `repeats=3` ima 3
reda sa istim `instance_id`. `swebench/harness/run_evaluation.py:743` radi:

```python
predictions = {pred["instance_id"]: pred for pred in predictions}
```

Dict comprehension nad listom sa dupliranim ključevima zadržava samo
**poslednji** — patch-evi run-ova 0 i 1 se **nikad stvarno ne evaluiraju**,
ne samo da dobiju isti verdikt. Naš `pipeline.py:316`
(`results.get(row.instance_id)`) onda taj jedan verdikt backfill-uje na sva
tri reda. Upisano kao ISSUES.md #9. Stopgap: `repeats=1` (default, sve dosad
pokrenuto tako) — kolizije nema. Pravi fix: odvojen `run_evaluation` poziv po
`run_index`-u, spajanje po `(instance_id, run_index)` umesto po
`instance_id`.

Ostale tačke review-a (🟢/🟡, ne blokirajuće): sandbox/provisioning dizajn je
dobar (base_commit checkout, `.git` uklonjen, remote uklonjen — sprečava
pristup upstream history-ju); zvanični SWE-bench grader je velik plus u
odnosu na ad-hoc proveru; telemetrija je već bogata (tokeni, cost, wall/LLM/
tool time, tool breakdown); predlaže se `cost per resolved task` kao primarna
efficiency metrika umesto `avg cost/run`; 4-uslovni toolset dizajn
(bash / +str_replace / +search / +oba) dozvoljava razdvajanje incremental
contribution-a svake grupe alata; `harness_sha` po run-u već postoji i treba
ga zadržati; predložen `tool_usage` breakdown (`str_replace_available/used/
calls/successes/errors`) za jasniji rezultat o tome da li je alat stvarno
korišćen.

---

## 10. Razmatranje sweep-a preko modela i reasoning nivoa

**Pitanje:** da li bi mogla evaluacija da se pokrene nad gpt-5.4-mini i nano
sa reasoning on/off na low, za 100 instanci?

Provereno pre odgovora: `run_pipeline()` uzima jedan `model` i jedan
`reasoning_effort` po pozivu — sweep preko 2 modela × 2 reasoning nivoa traži
**4 odvojena CLI poziva** (isti `--seed` u sva četiri za paired design).
Pregled svih dosadašnjih `manifest.json` fajlova pokazao je da je **svaki**
dosadašnji run bio `gpt-5.4-nano`, `reasoning_effort: None` — nema nijednog
merenja za mini ili za reasoning-on, pa bi bilo koja cena/vreme za ta tri
uslova bila čista ekstrapolacija iz `MODEL_PRICING` tabele (nano
$0.20/$1.25, mini $0.75/$4.50 po milion tokena — mini ~3.6-3.75× skuplji), ne
merenje. Disk rizik za 100×4=400 grading run-ova je i veći nego već rizičan
50-instance scenario. Predlog (neizvršen do kraja ove sesije): mali pilot od
5-10 instanci kroz sva 4 uslova pre commitovanja na puni batch.

---

## 11. `NOTES.md` — lekcije upisane nazad u dizajn-dokument

Na kraju, `docs/agent/NOTES.md` (dizajn-racionale za harness, ne za SWE-bench
specifično) dopunjen nalazima koji su generalizovali van SWE-bench konteksta:

- §3 — tabela alata proširena sa 3 na 6; svaki dodatak i dalje u duhu
  "kontrola izlaza, ne nova moć".
- §4 — str_replace primer zamenjen stvarnim sphinx incidentom: jasna poruka
  greške nije dovoljna ako savet u njoj pokazuje u pogrešnom smeru
  (nadole umesto naviše).
- §7 — `MUST use str_replace` rečenica, iako neophodna za usvajanje alata,
  postaje confound za bilo koji toolset-ablation eksperiment koji pokušava
  da izmeri efekat samog alata.
- §8 — čuvanje samo `type(e).__name__` (umesto `status_code`/`body`)
  pretvara dijagnostifikovljiv problem u nedijagnostifikovljiv —
  BadRequestError/moderation-flag nalaz kao konkretan dokaz.

---

## Generisani/izmenjeni artefakti tokom ove faze

- `docs/todo/ISSUES.md` (bivši `TODO.md`) — živi log nalaza, 9 stavki
- `docs/todo/EVAL_PREP.md` — plan pripreme za 50-instance batch
- `docs/RECOMMENDATION.md` — sačuvan eksterni review protokola
- `docs/agent/TOOLS.md` — detaljna referenca svih 6 alata
- `docs/agent/NOTES.md` — dopunjen novim lekcijama (§3, §4, §7, §8)
- `scripts/replay_request.py` — replay sačuvanog payload-a (`--prefix`, `--bisect`)
- `evals/swebench/pipeline.py`, `schemas.py`, `steps/grade.py` — puna greška,
  `error_message`, `llm_seconds`/`tool_seconds`, `grade_error`,
  `messages/`/`errors/` artefakti
- `src/harness/scripts/str_replace.py`, `tools/str_replace.py` — brojevi
  linija, `replace_all`/`occurrence`
- `src/harness/tools/search.py`, `sandbox.py` — glob-sa-slash fix, truncation
  marker
- `src/harness/providers/base.py`, `openai_provider.py`, `agent.py` — čist
  `assistant_message` dict umesto sirovog SDK objekta
- `~/.cache/agent-harness/repos/` — svih 12 SWE-bench Lite repo-a klonirano
- Obrisan: nepraćen root-level `swebench/` direktorijum (shadowing rizik)
