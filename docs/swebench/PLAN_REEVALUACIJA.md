# Ponovljeni uslovi C i D — dva plana za rad

Odluka čeka profesora. Oba plana koriste iste podatke. Razlikuju se samo po tome
šta u radu ostaje primarni rezultat.

## Kontekst

- `batch_300` (`20260915_120759_batch_300`) je rađen sa `search` alatom koji nije
  podržavao glob sa putanjom (`sympy/**/*.py`). Posledica: 49,5% `search` poziva
  u C i 56,0% u D je vratilo grešku, a `tool_call_errors` to nije video. Detalji
  su u `docs/todo/ISSUES.md` #11, a obrasci u transkriptima u
  `artifacts/swebench/manual_review_analysis.md`.
- Ispravka je u commit-u `628978d`. Verzija alata iz `batch_300` je označena tagom
  `batch-300` (`3e3dc79`).
- **Ponovljeni su samo uslovi C i D** (`*_batch_300_search_fix`, 600 run-ova), na
  drugom računaru (Windows/WSL2).
- **A i B se ne ponavljaju.** Nemaju `search`, a između verzije iz `batch_300`
  (`6d8505d`) i `628978d` izmenjeni su samo `search` i `read_file`
  (`git diff --stat 6d8505d 628978d -- src evals/swebench`). `bash`, `str_replace`,
  agent, prompt, sandbox i model su isti.

Šta je u ponovljenom runu drugačije, osim ispravljenog `search`-a:

| razlika | utiče na agenta? | napomena |
|---|---|---|
| dan izvršavanja (Azure) | ne sistematski | model ni pri `temperature 0` nije potpuno deterministički; to je već navedeno u ograničenjima |
| `git fetch` izbačen iz `provision.py` (necommit-ovano, samo na udaljenom računaru) | ne | isti `base_commit`, isti checkout; zapisano u ISSUES #12 |
| sandbox image, **ako je pravljen iz trenutnog `Dockerfile`-a** | **da** | trenutni `Dockerfile` instalira `ripgrep`, a image iz `batch_300` (`b68fe1cfc70e`) ga nema. Ispravno je koristiti image prenet sa laptopa, vidi preduslov 1 |
| `read_file` ispravka (prazan fajl, `start_line` posle kraja) | praktično ne | u `batch_300` nijednom pogođeno (ISSUES #11) |

---

## Preduslovi, zajednički za oba plana

1. **Sandbox image identičan `batch_300`.** Na udaljenom računaru mora da važi:
   ```bash
   docker image ls agent-sandbox --format '{{.ID}}'                                  # b68fe1cfc70e
   docker run --rm agent-sandbox bash -lc "which rg || echo NEMA RG; python --version"   # NEMA RG, Python 3.12.14
   ```
   Ako run nije rađen sa tim image-om, ponoviti ga (`docker save` na laptopu → `docker load`).
2. **Run je kompletan i čist:** 600 redova, `crash` 0, `api_error` reda veličine
   `batch_300` (C 2,0%, D 1,0%; to je Azure filter sadržaja, `400 invalid_prompt`).
3. **Grading je urađen i proveren:** prazan `grade_error` samo uz prazan patch, a
   svih 300 eval image-a lokalno pre gradinga (ISSUES #6).
4. **Rezultati su preneti na laptop** (`tar` → AnyDesk) u `artifacts/swebench/experiments/`.
5. **Kombinovani eksperiment** (A i B iz `batch_300`, C i D iz ponovljenog runa),
   potreban za oba plana:
   ```bash
   cd artifacts/swebench/experiments
   OLD=20260915_120759_batch_300; NEW=$(ls -d *_batch_300_search_fix); CMB=20260915_120759_batch_300_combined
   mkdir -p $CMB/predictions $CMB/conversations $CMB/messages $CMB/errors
   for s in gpt-5.4-nano__bash gpt-5.4-nano__bash-str_replace; do
     grep "\"session_id\": \"$s\"" $OLD/rows.jsonl >> $CMB/rows.jsonl
     cp $OLD/predictions/$s.jsonl $CMB/predictions/
     cp $OLD/conversations/${s}__* $CMB/conversations/; cp $OLD/messages/${s}__* $CMB/messages/; cp $OLD/errors/${s}__* $CMB/errors/ 2>/dev/null
   done
   for s in gpt-5.4-nano__bash-find_file-read_file-search gpt-5.4-nano__bash-find_file-read_file-search-str_replace; do
     grep "\"session_id\": \"$s\"" $NEW/rows.jsonl >> $CMB/rows.jsonl
     cp $NEW/predictions/$s.jsonl $CMB/predictions/
     cp $NEW/conversations/${s}__* $CMB/conversations/; cp $NEW/messages/${s}__* $CMB/messages/; cp $NEW/errors/${s}__* $CMB/errors/ 2>/dev/null
   done
   wc -l $CMB/rows.jsonl        # 1200
   cd ../../..
   uv run scripts/localization.py artifacts/swebench/experiments/$CMB
   uv run scripts/hypotheses_h1_h3.py artifacts/swebench/experiments/$CMB | tee artifacts/swebench/experiments/$CMB/hypotheses.txt
   ```
   `grep "\"session_id\": ..."` hvata tačno jedan uslov, jer je `session_id` ceo string
   pod navodnicima. Pre analize proveri da `rows.jsonl` ima po 300 redova za svaki uslov.

Isti zaključani postupak (seed `20260915`, 10 000 bootstrap ponavljanja, isti kriterijumi)
važi u oba plana. Menja se samo ulazni folder.

---

## Plan 1 — Reevaluacija kao dopunska analiza

**Suština:** svi postojeći rezultati u radu ostaju primarni i nepromenjeni. Dodaje se
jedan odeljak koji pokazuje šta se dešava sa ispravljenim alatom.

**Kada izabrati:** ako profesor želi da unapred zaključan plan ostane netaknut, ili ako
je rok blizu. Najmanje posla, najmanji rizik.

### Izmene u radu (`Diplomski rad.tex`)

| mesto | izmena |
|---|---|
| Резултати, novi pododeljak posle „Провера хипотезе Х3" | „Поновљена евалуација услова В и Г": zašto (glob sa putanjom, otkriveno analizom transkripata), šta je ponovljeno i zašto A i B nisu, tabela sa 4 uslova (A, B originalni; C, D ponovljeni) i ishod H1–H3 originalno naspram ponovljeno, 2–3 rečenice tumačenja |
| Ограничења, stavka „Резултат важи за ову имплементацију алата" (~red 2049) | ukloniti tvrdnju „`search` и `find_file` нису вратили ниједну грешку у 8 467 позива" i „Мерења говоре против објашњења да су алати неисправни"; zameniti kvantifikovanim defektom i uputiti na novi pododeljak |
| Дискусија, pasus o mehanizmu H3 (~red 1938) | jedna rečenica: deo neuspeha Г na 41 zadatku „samo Б" prate neuspele pretrage i petlje, a ponovljena evaluacija pokazuje koliki je taj deo |
| Закључак → Ограничења | jedna klauzula da je `search` imao defekt i da je proveren ponovljenom evaluacijom |
| Закључак → Даљи рад | ukloniti ili preformulisati predlog za ponavljanje В и Г (urađeno je) |
| Практичне препоруке (opciono) | stavka o merenju grešaka alata nezavisno od prefiksa `ERROR` i o podršci za glob sa putanjom |

Apstrakt, H1–H3 pododeljci, sve postojeće slike i tabele ostaju isti.

### Izmene u `docs/`

- `docs/swebench/H2.md:178` i `docs/swebench/ZAKLJUCAK.md:77`: ukloniti tvrdnju da
  alati za pretragu rade ispravno / bez grešaka (ISSUES #11).
- Novi `docs/swebench/REEVALUACIJA.md`: brojevi iz `$CMB/hypotheses.txt` i poređenje
  sa `batch_300`.
- Nova slika (opciono): stope rešenih po uslovu, originalno i ponovljeno, jedna pored druge.

### Procena posla

Analiza oko 1 h, tekst 1–2 strane, jedna tabela, opciono jedna slika.

---

## Plan 2 — Kombinovani eksperiment kao glavna analiza

**Suština:** primarni rezultati u radu postaju A i B iz `batch_300` plus C i D iz
ponovljenog runa. Originalni C i D se navode kao prvobitno merenje sa defektnim alatom.

**Kada izabrati:** ako profesor želi da glavni zaključci opisuju ispravne alate.
Validno je, jer A i B nisu pogođeni defektom, ali mora biti transparentno. To je
odstupanje od zaključanog plana i mora biti napisano.

### Izmene u radu (`Diplomski rad.tex`)

| mesto | izmena |
|---|---|
| Апстракт (~red 306) | novi brojevi: stope rešenih, B−D, efekat pretrage na lokalizaciju i trošak |
| Методологија → Поставка експеримента | rečenica: услови В и Г поновљени су са исправљеним алатом `search` jer прва верзија није подржавала глоб са путањом; А и Б нису поновљени јер не користе претрагу, а остатак система није мењан |
| Резултати → Х1, мера локализације, Х2, Х3 | svi brojevi, intervali, tabele i slike iz `$CMB` |
| Резултати, novi kratak pododeljak ili prilog | originalni C i D (defektan alat) u jednoj tabeli, uz rečenicu šta se promenilo |
| Дискусија | ponovo proveriti svaki mehanizam (levak, reprodukcija, po repou), jer su izvedeni iz starih C i D |
| Ограничења | ukloniti tvrdnju o nula grešaka; dodati stavku o odstupanju od zaključanog plana (ponovljen deo uslova, drugi dan i računar, isti image) |
| Закључак → Главни налази, Тумачење, Ограничења, Даљи рад | uskladiti sa novim brojevima; iz Даљи рад ukloniti ponavljanje В и Г |

### Izmene u kodu i `docs/`

- Notebook-ovi `h1_h3_figures.ipynb`, `h2_figures.ipynb`, `toolset_agreement.ipynb`,
  `rezultati_i_uzorak.ipynb`: `EXP` → `$CMB`, zatim ponovo pokrenuti. **`assert` ćelije
  sa brojevima iz H1.md/H3.md će pasti i moraju se ažurirati.**
- Regenerisati sve slike u `docs/media/` (`h1_*`, `h3_*`, H2 slike) i proveriti da rad
  koristi nove.
- `docs/swebench/H1.md`, `H2.md`, `H3.md`, `ZAKLJUCAK.md`: novi brojevi.
- `docs/swebench/EXPERIMENT_LOCK.md`: dodatak „Odstupanje od plana" (šta je ponovljeno,
  zašto, kada, sa kojom verzijom, šta nije promenjeno).

### Procena posla

Ceo dan ili dva: sve slike, sve tabele, apstrakt, diskusija i zaključak.

---

## Poređenje

| | Plan 1: dopunska analiza | Plan 2: kombinovani kao glavni |
|---|---|---|
| primarni rezultat | originalni `batch_300` | A, B original + C, D ponovljeni |
| unapred zaključan plan | netaknut | odstupanje, mora biti opisano |
| šta glavni zaključci opisuju | alate sa defektom, uz proveru | ispravne alate |
| obim izmena u radu | 1 pododeljak + 4 rečenice | apstrakt, poglavlja 5 i 6, sve slike |
| rizik greške pri prepisivanju brojeva | mali | veći |
| pitanje na odbrani | „koliko je defekt uticao?" — odgovor u pododeljku | „zašto je plan menjan?" — odgovor u metodologiji |

U oba plana važi: rečenica o nula grešaka u `search`-u mora da se ukloni, i u radu
mora da piše da su В и Г ponovljeni i zašto.

**Očekivanje, pre gradinga** (procena iz scenarija, ne rezultat): formalni ishodi
(H1 odbijena, H2 odbijena, H3 potvrđena) najverovatnije ostaju isti. Menjaju se
veličine efekata: razlika B−D verovatno pada sa +11,7 pp na oko 5–10 pp, a tvrdnja
da pretraga *smanjuje* lokalizaciju verovatno više ne važi.
