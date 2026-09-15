# Metodologija

Sažet opis metodologije rada: arhitektura agenta, dizajn alata, okruženje za
izvršavanje i postupak evaluacije. Proveren prema kodu na dan 2026-09-15
(radno stablo na `feature/swe-benchmark`, nekomitovane izmene uključene).
Detalji su u dokumentima na koje se svaka sekcija poziva.

---

## Apstrakt

Rad ispituje kako skup alata dostupnih jezičkom modelu (*tool surface*) utiče na
uspešnost i cenu agenta za rešavanje softverskih zadataka, uz fiksiran model.
Za potrebe rada razvijen je minimalan harness: agentska petlja u kojoj model
putem *function calling* interfejsa poziva alate koji se izvršavaju u izolovanom
Docker kontejneru. Agent je evaluiran na SWE-bench Lite skupu (300 stvarnih
GitHub issue-a iz 12 Python repozitorijuma) u faktorskom dizajnu sa četiri
toolset uslova — samo `bash`, `bash` + `str_replace`, `bash` + alati za
pretragu/čitanje, i svi zajedno — nad istim instancama (uparen dizajn, 1200
run-ova). Ispravnost se utvrđuje zvaničnim SWE-bench evaluatorom (skriveni
FAIL_TO_PASS i PASS_TO_PASS testovi), a trošak kroz tokene, cenu i vreme po
run-u. Primarni ishodi su stopa rešenih zadataka i cena po rešenom zadatku.
Model (`gpt-5.4-nano`), sistemski prompt i ograničenja izvršavanja su identični
u svim uslovima, pa se razlike pripisuju isključivo dostupnim alatima.
*[Rezultati — nakon grading-a.]*

---

## 1. Arhitektura agenta

Agent je ReAct-stil petlja (`src/harness/agent.py`):

1. Model dobija istoriju poruka (sistemski prompt + opis zadatka + dosadašnji
   pozivi) i JSON šeme aktivnih alata.
2. Ako odgovor ne sadrži poziv alata → kraj (`completed`).
3. Inače se svaki poziv validira (Pydantic model argumenata), izvrši u
   sandbox-u, a rezultat vrati modelu kao `tool` poruka.
4. Ponavlja se do `max_turns` koraka (tada `termination_reason = max_turns`).

Ključne odluke:

- **Model ne izvršava ništa** — samo predlaže poziv; harness odlučuje i izvršava.
- **Greške su deo konverzacije.** Nevalidni argumenti ili nepoznat alat vraćaju
  se modelu kao `ERROR: ...` string, ne kao izuzetak — model može da reaguje.
  Izlaz alata se tretira kao prompt (NOTES §4).
- **Provajder je apstrahovan** (`LLMProvider` → `OpenAIProvider`, OpenAI i Azure).
  Poruka asistenta se ručno gradi kao čist dict, bez polja koja postoje samo u
  odgovoru API-ja.
- **Telemetrija u petlji** (`Usage`): prompt/completion/reasoning tokeni, cena
  (iz `MODEL_PRICING`), broj LLM poziva, LLM vs. tool vreme, broj poziva i
  grešaka po alatu.
- **Otpornost:** provajderov lažno pozitivan moderation odgovor
  (`invalid_prompt`) ponavlja se do 2 puta; svaki drugi 400 prekida run.
  Petlja ima kooperativni stop signal koji koristi spoljni wall-clock timeout.
- **Bez kompakcije konteksta** — istorija raste neograničeno; input tokeni rastu
  približno kvadratno sa brojem koraka, zbog čega je ograničavanje izlaza alata
  deo modela troškova (NOTES §6).

Detalji: [agent/NOTES.md](agent/NOTES.md) §1, §4, §6.

## 2. Dizajn alata

Svaki alat je `Tool(name, args_model, definition, handler)` u zasebnom modulu;
registar omogućava da se po run-u aktivira proizvoljan podskup
(`get_active_tools`) — to je mehanizam ablacije.

| Alat | Uloga | Implementacija |
|---|---|---|
| `bash` | ceo Linux userland; jedini obavezan alat | `docker exec` |
| `search` | regex pretraga sadržaja, max 50 pogodaka, bez `.git`/`node_modules` | `grep` u sandbox-u |
| `read_file` | čitanje sa brojevima linija i validiranim opsegom | Python skripta |
| `find_file` | pretraga po imenu/glob-u, sa brojem ukupnih pogodaka | Python skripta |
| `str_replace` | literalna zamena teksta; mora biti **jedinstven** pogodak (ili eksplicitno `replace_all` / `occurrence`) | Python skripta |
| `run_tests` | pytest sa strukturisanim JSON izlazom | Python skripta — **nije u SWE-bench eksperimentu** |

Principi:

- **Alati uglavnom ne dodaju sposobnost, već kontrolišu izlaz.** Sve osim
  `str_replace` `bash` već može; vrednost je ograničen, predvidljiv izlaz koji ne
  troši kontekst.
- **`str_replace` je izuzetak** — rešava ono što `sed` radi loše (višelinijski
  blokovi, escape-ovanje, tiha višestruka zamena). Provera jedinstvenosti je
  sigurnosno svojstvo; poruka greške navodi linije svih pogodaka i savetuje
  proširenje konteksta *naviše* (posledica stvarnog incidenta, NOTES §4).
- **Poruke grešaka i praznih rezultata su eksplicitne** (`No matches.`,
  `... [truncated N more chars]`) jer ih model čita kao instrukciju.
- Logika složenija od jedne shell komande živi u skriptama montiranim
  read-only u kontejner (`/opt/agent-scripts`), kojima se argumenti predaju kao
  JSON na stdin.

Detalji: [agent/TOOLS.md](agent/TOOLS.md), [agent/NOTES.md](agent/NOTES.md) §3.

## 3. Okruženje za izvršavanje

Svaki run dobija sopstveni, jednokratni Docker kontejner (`src/harness/sandbox.py`):

- Image `agent-sandbox` (`python:3.12-slim` + `pytest`, `ripgrep`) — **bez
  zavisnosti ciljanog repozitorijuma**, pa agent ne može da pokrene projektne
  testove ("blind" režim; zato je `run_tests` isključen).
- Kontejner se pokreće sa `sleep 3600` (samouništenje i ako harness padne) i
  prima komande preko `docker exec bash -lc`. Fajl sistem je perzistentan između
  poziva, **shell stanje nije** (to je navedeno i u promptu).
- Checkout repozitorijuma je bind-mount na `/work` — izmene su odmah vidljive
  na hostu, odakle se izvlači patch.
- Ograničenja: `--network none` (nema pristupa internetu ni upstream fix-u),
  `--memory 2g`, `--pids-limit 256`, `--user <uid>:<gid>`, skripte `:ro`.
- Izlaz komande je ograničen na 8000 karaktera sa eksplicitnim markerom;
  podrazumevani timeout komande 60 s.
- Po run-u: najviše 40 koraka i 1800 s wall-clock vremena.

Izolacija je granica, ne pravilo: sve van mount-a u kontejneru ne postoji
(NOTES §2).

## 4. Postupak evaluacije

### 4.1 Razvojna faza — toy zadaci

Tokom razvoja harness je proveravan na 12 malih zadataka (`evals/tasks.py`,
`TASKS1` + `TASKS2`) u svežem sandbox-u, sa proverom stanja fajl sistema posle
run-a, nikad iskaza modela. Ovi rezultati služe samo razvoju i nisu dokaz za
hipoteze (skup je korišćen za podešavanje, a REPL/toy prompt eksplicitno
nalaže `str_replace`). Detalji: [evals/EVALS.md](evals/EVALS.md).

### 4.2 Dataset

`SWE-bench/SWE-bench_Lite`, `test` split, **svih 300 instanci** (12 repozitorijuma;
django 114, sympy 77, …). Pošto se koristi ceo split, nema selekcije instanci.
Svaka instanca: repozitorijum, `base_commit`, tekst issue-a; skriveni testovi
(FAIL_TO_PASS, PASS_TO_PASS) agentu nisu dostupni. Detalji:
[swebench/DATASET.md](swebench/DATASET.md).

### 4.3 Dizajn eksperimenta

Jedan faktor (toolset), četiri nivoa, uparen dizajn — svaka instanca prolazi kroz
sva četiri uslova:

| uslov | alati |
|---|---|
| A | `bash` |
| B | `bash`, `str_replace` |
| C | `bash`, `search`, `read_file`, `find_file` |
| D | `bash`, `search`, `read_file`, `find_file`, `str_replace` |

Kontrasti: efekat `str_replace` (A→B, C→D) i efekat grupe pretraga/čitanje
(A→C, B→D). `repeats = 1`.

Hipoteze (zaključane u [EXPERIMENT_LOCK.md](swebench/EXPERIMENT_LOCK.md) §2.4):

- **H1** — dostupnost `str_replace` smanjuje trošak po rešenom zadatku.
- **H2** — dostupnost grupe pretraga/čitanje povećava trošak po run-u, ali
  povećava stopu lokalizacije.
- **H3** — stopa rešenih u uslovu B nije niža od uslova D za više od 5 p.p.
  (neinferiornost).

Razlike po tipu zadatka i interakcija alata sa modelom su eksplorativne ili
dalji rad.

Kontrolisane promenljive (identične u svim uslovima): `gpt-5.4-nano`,
`temperature 0`, reasoning isključen, `max_turns 40`, `run_timeout 1800 s`, mreža
isključena, **isti sistemski prompt koji ne pominje nijedan alat** — da bi se
merio efekat alata, a ne "alat + instrukcija da se koristi".

### 4.4 Tok jednog run-a

1. **Provizioniranje** — checkout `<repo>@<base_commit>` na hostu iz keširanog
   mirror-a; istorija se briše i zamenjuje jednim `base` commit-om bez remote-a,
   pa agent ne može do upstream rešenja.
2. **Agent** — radi u sandbox-u nad checkout-om; zadatak je `problem_statement`.
3. **Predikcija** — `git add -A && git diff --cached HEAD` daje unified diff
   (+ dijagnostika: prazan patch, broj fajlova/linija). Zapisuje se odmah u
   `predictions/<session>.jsonl` u zvaničnom SWE-bench formatu.
4. **Ocenjivanje (odvojena faza)** — zvanični `swebench.harness.run_evaluation`
   primenjuje patch u instance-specifičnom Docker image-u i pokreće skrivene
   testove. Instanca je `resolved` ako prolaze svi FAIL_TO_PASS i PASS_TO_PASS
   testovi. `grade_error` beleži slučaj kada verdikt ne postoji (npr. image nije
   povučen) — takav red se ne sme čitati kao neuspeh.

Artefakti po run-u: red metrika (`rows.jsonl`), renderovana konverzacija, sirove
poruke za byte-exact replay, detalj greške. `harness_sha` se beleži po redu.
Detalji: [swebench/METRICS_SWE.md](swebench/METRICS_SWE.md),
[swebench/CLI.md](swebench/CLI.md).

### 4.5 Metrike

- **Primarne:** `resolved` rate; **cena po rešenom zadatku** = ukupna cena uslova /
  broj rešenih u tom uslovu; **stopa lokalizacije** = udeo run-ova čiji patch
  menja fajl koji menja gold patch (`scripts/localization.py`).
- **Sekundarne:** cena po run-u, prompt/completion tokeni, broj koraka i LLM
  poziva, wall/LLM/tool vreme.
- **Dijagnostičke:** prazan patch, `termination_reason`, greške alata, broj
  poziva po alatu (da li je dostupan alat stvarno korišćen), F2P/P2P brojevi,
  veličina patch-a.

Uloge metrika su fiksirane pre rezultata.

### 4.6 Pravilo isključivanja

- `invalid_prompt` (moderation false positive provajdera) je **ishod** te ruke u
  primarnoj analizi, a stopa se izveštava po uslovu.
- `max_turns` i `wall_timeout` su ishod (neuspeh), ne kvar.
- Isključuju se samo `harness_error` i `crash` (infrastruktura), i to **po
  instanci** (iz svih uslova), da `n` ostane jednak.
- **Sensitivity analiza:** isto poređenje na instancama koje su završile bez
  API greške u sva četiri uslova.

Detalji i obrazloženje: [swebench/EXPERIMENT_LOCK.md](swebench/EXPERIMENT_LOCK.md) §2.3.

### 4.7 Statistička analiza

Zaključano u [EXPERIMENT_LOCK.md](swebench/EXPERIMENT_LOCK.md) §2.6 (pre gradinga):

- H1: uparen bootstrap CI razlike troška po rešenom (B+D vs A+C), dopunski Wilcoxon.
- H2: Wilcoxon za trošak po run-u; bootstrap CI za razliku lokalizacije, McNemar A–C i B–D.
- H3: uparen bootstrap CI za Rᴮ − Rᴰ, donja granica > −5 p.p.
- `resolved` po kontrastima: egzaktni McNemar; Holm korekcija; uvek veličina efekta i CI.
- Podgrupe i interakcija faktora — eksplorativno.

## 5. Ograničenja (za rad)

- **Jedan model** (`gpt-5.4-nano`) — rezultat ne generalizuje na jače modele;
  korist od alata je verovatno gornja granica.
- **Nedostajući podaci verovatno nisu nezavisni od tretmana:** u pilotu su svi
  `invalid_prompt` padovi bili u uslovima bez `search` (4/4) — model više sirovog
  koda propušta kroz `cat`/`grep`. Proveriti na punom batch-u (C/D još nisu pokrenuti).
- **`repeats = 1`** — nema procene varijanse unutar instance; `repeats > 1` je
  trenutno nemoguće jer grader zadržava samo poslednju predikciju po instanci
  (ISSUES #9).
- **Blind režim** — agent ne može da pokrene testove projekta.
- **SWE-bench Lite kvalitet** — curenje rešenja i slabi testovi (SWE-Bench+);
  rezultat važi u okviru benchmark-a.
- **Provenijencija:** batch je pokrenut sa nekomitovanim izmenama, pa
  `harness_sha` pokazuje `5c4bd06`; izmene tokom batch-a su samo
  knjigovodstvene (EXPERIMENT_LOCK §4).

---

## Dodatak: šta je u postojećim docs zastarelo

Provereno prema kodu; ovaj dokument već koristi ispravno stanje.

| dokument | zastarelo | stvarno stanje |
|---|---|---|
| NOTES §2 | kontejner radi `sleep infinity`, "stanje se čuva između poziva" | `sleep 3600` + `--rm`; čuva se samo fajl sistem, ne shell stanje |
| NOTES §7 | sistemski prompt sa `MUST use str_replace` | važi samo za REPL/toy prompt (`harness/prompt.py`); SWE-bench prompt ne pominje alate |
| NOTES §5 | "nine tasks" | 12 (`TASKS1` 3 + `TASKS2` 9) |
| NOTES §10 | predlaže retry | retry postoji samo za `invalid_prompt`; 429 i dalje nije obrađen |
| ISSUES #10 | otvoren | popravljeno u kodu (`Agent.stop`, `STOP_GRACE_SECONDS`); nije uživo okinuto |
| RECOMMENDATION §8–9 | 16 uslova, 50–100 instanci | zaključano: 4 uslova × 300 instanci, jedan model |
| RECOMMENDATION §12 | predlaže `str_replace_used` kolone | nisu dodate; izvodi se iz `tool_calls_breakdown` |
| TOOLS.md | `bash` šema traži `thought`, Pydantic ga ne čuva | i dalje tačno — nije popravljeno |
| EXPERIMENT_LOCK §7 | 125 bash run-ova, 8.0% `invalid_prompt` | 402 reda: bash ruka završena, 23/300 = 7.7% `api_error`; `bash+str_replace` 8/103 |
| EXPERIMENT_LOCK | nema plana statističke analize | dopunjeno 2026-09-15 (§2.4–2.6) |
| docs/README.md | ne navodi TOOLS, EXPERIMENT_LOCK, RECOMMENDATION, ISSUES | — |
