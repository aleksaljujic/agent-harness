# Experiment lock — batch_300 (toolset ablacija, SWE-bench Lite)

Pre-registracija glavnog eksperimenta: šta se meri, hipoteze, plan statističke
analize, po kom pravilu se isključuju run-ovi, i kako se batch operativno vodi. Svrha je da odluke budu zapisane **pre**
nego što se vide rezultati — razlika između analize i naknadnog pravdanja.

Prati [RECOMMENDATION.md](../RECOMMENDATION.md) (spoljni review protokola) i
[../todo/ISSUES.md](../todo/ISSUES.md) (otvoreni bagovi). Zamenjuje
[../todo/EVAL_PREP.md](../todo/EVAL_PREP.md), koji je pisan za manji batch i pre
današnjih popravki.

---

## 1. Status

| | |
|---|---|
| eksperiment | `artifacts/swebench/experiments/20260915_120759_batch_300` |
| dizajn | 300 instanci × 4 toolset uslova = **1200 run-ova**, `repeats=1` |
| grading | **isključen** u ovoj fazi (`--no-grade`); ocenjuje se odvojeno, posle |
| procena | ~16-40 h sekvencijalno, ~$20-30 |

---

## 2. Zaključane odluke

### 2.1 Faktori

Jedan faktor se varira, sve ostalo je fiksno:

| uslov | alati |
|---|---|
| A (baseline) | `bash` |
| B | `bash`, `str_replace` |
| C | `bash`, `search`, `read_file`, `find_file` |
| D | `bash`, `search`, `read_file`, `find_file`, `str_replace` |

Kontrasti koji se izveštavaju: **efekat `str_replace`** (A→B i C→D) i **efekat
search/read/find grupe** (A→C i B→D). Ne izveštava se samo „D je najbolji".

`model` i `reasoning_effort` su u ovoj fazi fiksni (`gpt-5.4-nano`, reasoning
isključen) — druga dimenzija iz RECOMMENDATION.md tačke 8 ostaje za kasnije i
zahteva odvojene pozive (`run_pipeline` uzima po jedan `model`/`reasoning_effort`).

**Posledica koju treba priznati u radu:** interakcija alata sa modelom/reasoning
režimom (stara H2 iz RECOMMENDATION.md §13) ovim dizajnom se **ne testira** i ide u
„dalji rad". Važeće hipoteze su u §2.4 i zamenjuju formulaciju iz RECOMMENDATION.md.
Model se brani kao *namerno kontrolisana*
promenljiva, ne kao budžetsko ograničenje, uz otvoreno navedenu granicu
generalizacije: rezultat važi za mali model, gde je korist od alata verovatno
gornja a ne donja granica. Puna formulacija i jeftina delimična nadoknada
(drugi model na podskupu od 50 instanci, ~$13) su uz
[RECOMMENDATION.md](../RECOMMENDATION.md) tačku 8.

### 2.2 Ishodi

**Primarni**
- `resolved` (posle gradinga)
- **cost per resolved task** = ukupna cena ruke / broj rešenih u toj ruci —
  *ne* prosečna cena po run-u (RECOMMENDATION.md tačka 6)
- **stopa lokalizacije** = udeo run-ova u kojima patch agenta menja bar jedan fajl
  koji menja i gold patch (definicija u §2.5)

**Sekundarni** — `cost`/run, `prompt_tokens`, `completion_tokens`,
`reasoning_tokens`, `turns_used`, `calls`, `wall_time`, `llm_seconds`,
`tool_seconds`

**Dijagnostički** — `empty_patch`, `patch_applied`, `crashed`,
`tool_call_errors`, `termination_reason`, F2P/P2P brojevi, `patch_lines_changed`

Uloge su fiksirane sada da se posle ne bi lovili „zanimljivi" p-value-ovi po 30
kolona.

### 2.3 Pravilo isključivanja — **zaključano**

> **Primarna analiza:** `invalid_prompt` se tretira kao **ishod te ruke**, ne kao
> kvar. Stopa odbijanja po ruci se izveštava kao rezultat, uz eksplicitnu napomenu
> da je uzrok provajderov moderation klasifikator, a ne model.
>
> **Sensitivity analiza:** isto poređenje ponovljeno na podskupu instanci koje su
> završile u **svim** rukama (strogo pairwise-complete isključivanje).
>
> **`max_turns` se NE računa kao pad** — to je model koji je potrošio budžet i nije
> rešio zadatak, dakle rezultat. Isključuju se samo `api_error`, `harness_error`,
> `crash`.
>
> Jedinica isključivanja je **instanca, ne run.** Ako se isključuje po run-u,
> stohastika klasifikatora pravi nejednake `n` po ruci i vraća isti problem.

**Zašto ovako, a ne strogo od početka:** dataset primarne analize *sadrži* dataset
sensitivity analize — brisanje redova je uvek moguće naknadno, dodavanje run-ova
nije. Zato se unapred zaključava koja je **primarna**, ne koje se sve smeju
izračunati.

**Poznato ograničenje koje ide u rad:** stopa odbijanja nije nezavisna od tretmana.
U pilotu su svi `invalid_prompt` padovi bili u rukama **bez** `search` (4/4), jer
bez tih alata model sipa sirov izvorni kod kroz `cat`/`grep` i tako nakupi sadržaj
koji okida klasifikator. To znači da nedostajući podaci koreliraju sa nezavisnom
promenljivom — mora se prijaviti kao ograničenje merenja, ne prećutati kao šum.

**Pojašnjenje (dodato 2026-09-15, pre gradinga i pre računanja lokalizacije):**
rečenica „isključuju se `api_error`, `harness_error`, `crash`" odnosi se na
`api_error` koji **nije** `invalid_prompt` (npr. rate limit, pad konekcije,
provajderov 5xx) — to je infrastruktura. `api_error` sa `invalid_prompt` je ishod,
kako kaže primarno pravilo iznad. Razlikuje se po `error_message` koloni reda.

### 2.4 Hipoteze — **zaključano 2026-09-15**

Polazna teza: `bash` + `str_replace` daje najbolji odnos cene i uspešnosti, a pun
skup alata donosi prednost pre svega pri lociranju greške. Razložena na:

- **H1** — dostupnost `str_replace` smanjuje **trošak po rešenom zadatku**.
- **H2** — dostupnost grupe `search`/`read_file`/`find_file` **povećava trošak po
  run-u**, ali **povećava stopu lokalizacije**.
- **H3 (neinferiornost)** — stopa rešenih u uslovu B (`bash`, `str_replace`) nije
  niža od stope u uslovu D (svi alati) za više od **5 procentnih poena**.

H1 i H2 se proveravaju na glavnim efektima 2×2 dizajna, H3 poređenjem B–D. Razlike
po tipu zadatka (repo, veličina gold patch-a, broj F2P testova) i interakcija
faktora su **eksplorativne**, bez hipoteze.

**Vremenski trenutak zaključavanja, iskreno:** hipoteze i plan analize (§2.4–2.6)
upisani su **tokom** batch-a — uslov A završen (300/300), B delimično (~103/300),
C i D nisu pokrenuti — ali **pre bilo kakvog gradinga** (nijedan `resolved` nije
poznat) i **pre računanja lokalizacije**. Jedini viđeni brojevi su agregati iz §7
(stopa `api_error`, prosečna cena i vreme u A ruci). Protokol isključivanja (§2.3),
ishodi (§2.2) i konfiguracija (§3) zaključani su ranije, pre starta batch-a.
Lokalizacija je prvi put izračunata posle upisa ovog odeljka, kao test skripte nad
delimičnim podacima (A: 300, B: 110 run-ova).

### 2.5 Definicija lokalizacije — **zaključano**

- Fajlovi patch-a = putanje iz zaglavlja diff-a (`--- a/…`, `+++ b/…`), bez
  `/dev/null`; za gold patch koristi se kolona `patch` iz SWE-bench Lite (ne
  `test_patch`).
- Run je **lokalizovan** ako je presek fajlova patch-a agenta i gold patch-a
  neprazan.
- **Prazan patch = nelokalizovan.**
- Run sa `api_error` (`invalid_prompt`) ili `max_turns`/`wall_timeout` ocenjuje se
  po delimičnom patch-u koji je izvučen — dosledno §2.3 (to je ishod, ne kvar).
- Isključenja po instanci iz §2.3 važe i za lokalizaciju.
- Računa se skriptom `scripts/localization.py` nad `predictions/` — bez novih run-ova.

### 2.6 Plan statističke analize — **zaključano 2026-09-15**

Opšte: α = 0.05, dvostrano; uparen dizajn, instanca je blok. Bootstrap = 10 000
ponavljanja, percentilni interval, fiksan seed `20260915`; resampling **instanci sa
vraćanjem**, instanca se uzima istovremeno u sva četiri uslova. Uz svaku p-vrednost
se izveštavaju veličina efekta i 95% CI.

| hipoteza | mera | test / interval | kriterijum potvrde |
|---|---|---|---|
| H1 | trošak po rešenom, (B+D) vs (A+C): Σcena / Σrešenih po grupi | bootstrap 95% CI razlike; dopunski Wilcoxon signed-rank nad dᵢ = mean(cenaB, cenaD) − mean(cenaA, cenaC) | ceo CI ispod 0 |
| H2a | trošak po run-u, (C+D) vs (A+B) | Wilcoxon signed-rank nad dᵢ = mean(C, D) − mean(A, B) | Holm-korigovano p < 0.05 i medijana dᵢ > 0 |
| H2b | stopa lokalizacije, (C+D) vs (A+B) | uparen bootstrap 95% CI razlike; egzaktni McNemar za A–C i B–D | ceo CI iznad 0 |
| H3 | Rᴮ − Rᴰ (stopa rešenih) | uparen bootstrap 95% CI | donja granica CI > −5 p.p. |

H2 je potvrđena samo ako važe **i** H2a **i** H2b.

- **Holm korekcija — primarna familija (4 testa):** Wilcoxon H1, Wilcoxon H2a,
  McNemar lokalizacije A–C, McNemar lokalizacije B–D.
- **`resolved` po kontrastima:** egzaktni McNemar za četiri kontrasta dizajna
  (A–B, C–D, A–C, B–D), kao zasebna familija sa sopstvenom Holm korekcijom;
  sekundarno, ne služi za potvrdu hipoteza.
- **Nedefinisan trošak po rešenom:** ako u bootstrap uzorku grupa ima 0 rešenih,
  uzorak se odbacuje i broj odbačenih se prijavljuje. Ako je odbačeno > 5% uzoraka,
  H1 se izveštava samo deskriptivno.
- **Sensitivity (§2.3):** sve iznad se ponavlja na instancama završenim bez
  `api_error` u sva četiri uslova; neslaganje sa primarnom analizom se prijavljuje,
  ne razrešava izborom.
- **Eksplorativno:** interakcija faktora (razlika razlika), podgrupe po repo-u,
  veličini gold patch-a i broju F2P testova — bez korekcije, označeno kao takvo.

**Poznato ograničenje mere troška:** `cost` se računa po listi cena ($0.20 / $1.25
po 1M tokena) nad **svim** prompt tokenima, bez popusta za keširan input (keširani
tokeni se ne beleže). Apsolutni iznosi su zato gornja granica stvarnog računa, a
poređenje uslova je tačno samo ako je udeo keširanja sličan među uslovima — što nije
zagarantovano (duže istorije → više keš pogodaka). Navodi se u radu kao ograničenje.

---

## 3. Zamrznuta konfiguracija

| | |
|---|---|
| model | `gpt-5.4-nano` |
| temperature | `0.0` (eksplicitno poslata) |
| reasoning_effort | isključen |
| `max_turns` | 40 |
| `run_timeout` | 1800 s |
| sandbox network | `none` (agent nema internet — ne može do upstream fixa) |
| dataset / split | `SWE-bench/SWE-bench_Lite` / `test`, `--limit 300` (ceo split) |
| `repeats` | 1 — **ne dizati** dok ISSUES #9 nije rešen |

**System prompt** (`evals/swebench/prompt.py`, sha256 `acf6e2e006a43645`):

```
You are a software engineer resolving a bug report in an existing repository.
The repository is already checked out at /work.
Investigate the codebase with your tools, locate the cause, then make the smallest
change to the source that resolves the issue.
Do NOT edit, add, or delete tests — the change is graded against a hidden test suite.
Each bash command is self-contained; chain with && since state does not carry
between calls. There is no network access.
Stop when the fix is complete — do not narrate a summary.
```

Prompt **ne sme** pominjati nijedan konkretan alat niti obeshrabrivati prepisivanje
fajla preko `cat`. Ranija verzija je sadržala `MUST use str_replace`, što je merilo
„alat + instrukcija da se koristi" umesto „alat" — vidi RECOMMENDATION.md tačku 1.
Identičan je za sva četiri uslova.

---

## 4. Provenijencija — nerešeno, uraditi pre nastavka

`harness_sha` u svim dosadašnjim redovima je `5c4bd06…`, ali radno stablo ima **17
izmenjenih fajlova** koji nisu komitovani. Kolona koja treba da kaže „kojom
verzijom je ovo dobijeno" pokazuje pogrešnu verziju.

**Uraditi:** komitovati izmene pre (nastavka) batch-a, da `harness_sha` od tog
trenutka bude tačan.

**Da li je mešanje starih i novih redova validno:** jeste, i to je važna razlika.
Izmene napravljene *tokom* batch-a su čisto knjigovodstvene — perzistencija
predikcija po run-u, brisanje `work/` checkout-a, `--resume`. Nijedna ne menja
ponašanje agenta. Izmene koje *jesu* menjale ponašanje (Unicode fix u `sandbox.py`,
`invalid_prompt` retry, stop event, temperature flag) ušle su **pre** starta ovog
batch-a, pa su svi redovi behaviorally uporedivi. To treba eksplicitno napisati u
radu umesto da se ćuti o neusklađenom SHA-u.

---

## 5. Runbook

### 5.1 Pokretanje / nastavak

```bash
.venv/bin/python scripts/run_swebench.py \
  --limit 300 \
  --temperature 0 \
  --no-grade \
  --resume artifacts/swebench/experiments/20260915_120759_batch_300 \
  --combo bash \
  --combo bash,str_replace \
  --combo bash,search,read_file,find_file \
  --combo bash,search,str_replace,read_file,find_file
```

`--limit 300` i sva četiri `--combo` moraju biti **identična** originalu — resume
preskače po `run_id`-u, ali petlja i dalje prolazi kroz istu listu instanci i
kombinacija. Izostavi `--resume` samo za potpuno nov eksperiment.

### 5.2 Prekid i nastavak

Batch se sme prekinuti u bilo kom trenutku (`pkill -f "run_swebench.py --limit 300"`).
Posle prekida:

- `rows.jsonl` — kompletan do poslednjeg završenog run-a (piše se posle svakog)
- `predictions/<session>.jsonl` — isto, po run-u
- `--resume` nastavlja od prvog `run_id`-a kojeg nema u `rows.jsonl`

### 5.3 Monitoring

```bash
watch -n 30 'wc -l < artifacts/swebench/experiments/20260915_120759_batch_300/rows.jsonl; df -h / | tail -1'
```

Prati i slobodan prostor: svaki run pravi ~80 MB checkout koji se briše čim je patch
izvađen, ali ako se pokrene sa `--keep-work`, 1200 run-ova traži ~100 GB.

### 5.4 Spasavanje predikcija iz starijih eksperimenata

Eksperimenti napravljeni pre per-run perzistencije imaju patch-eve samo u
`work/` folderima:

```bash
.venv/bin/python scripts/salvage_predictions.py \
  artifacts/swebench/experiments/<exp_id> [--dry-run]
```

### 5.5 Grading (posle, odvojeno)

Grading je namerno odvojen od ove faze — predikcije su već na disku i ocenjivanje ne
troši nijedan API poziv. Vidi ISSUES #6/#7/#8 za Docker image probleme
(~4 GB po instanci, 10-min pull timeout, lažni „image not found") i EVAL_PREP.md za
plan u talasima sa `docker rmi` između.

---

## 6. Poznati problemi koje unosimo u batch

| # | problem | status u ovom batch-u |
|---|---|---|
| ISSUES #2 | `invalid_prompt` moderation false positive | retry ugrađen (2 pokušaja); merimo stopu kao ishod |
| ISSUES #9 | `repeats>1` tiho baca sve osim poslednjeg | zaobiđeno — `repeats=1` |
| ISSUES #10 | nit posle `wall_timeout` | popravljeno (stop event), ali nije uživo okinuto |
| — | nema 429/rate-limit handling | relevantno ako se uvede paralelizacija |

---

## 7. Izmereno do sad (bash ruka, prvih 125 run-ova)

| | |
|---|---|
| `api_error` (`invalid_prompt`) | 10/125 = **8.0%** |
| mean wall time | 47 s/run |
| mean cena | $0.0172/run |

Pilot od 5 instanci je davao 60% u ovoj ruci — 8% na 125 run-ova pokazuje koliko je
procena sa `n=5` bila nepouzdana, i zašto je vredelo pustiti veći uzorak pre nego
što se dizajn menja zbog te stope.
