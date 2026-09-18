# Izmene u radu posle ponovljene evaluacije uslova В и Г

Namenjeno pisanju rada (druga VS Code instanca). Sadrži: šta je ponovljeno, nove
slike i njihova imena, sve brojeve „staro → novo", i izmene po odeljcima
`Diplomski rad.tex`. Brojevi su dobijeni **istim zaključanim postupkom** kao
originalni (`scripts/hypotheses_h1_h3.py`, seme `20260915`, 10 000 butstrap
ponavljanja, ista pravila isključivanja iz `EXPERIMENT_LOCK.md` §2.3).

Izbor plana (dopunska analiza naspram kombinovanog kao glavnog) opisan je u
[PLAN_REEVALUACIJA.md](PLAN_REEVALUACIJA.md). Ovaj dokument daje materijal za
oba, ali je pisan za varijantu u kojoj kombinovani eksperiment postaje glavni.

---

## 0. Nalaz, ukratko

**Prvi `search` je bio loš i to je obaralo rezultate uslova sa pretragom.** Glob sa
putanjom nije radio, pa je oko polovine pretraga vraćalo grešku. Agent je te
pozive ponavljao, trošio korake i često završavao bez ijedne izmene: uslov Г je u
18,0% pokretanja iscrpeo svih 40 koraka, a u 52 od 300 zadataka ostao bez zakrpe.

**Posle ispravke alata i ponovnog pokretanja samo В и Г, rezultati su bolji:**

| | В pre → posle | Г pre → posle |
|---|---|---|
| rešeno | 105 (35,0%) → **112 (37,5%)** | 84 (28,0%) → **99 (33,1%)** |
| iscrpeo korake | 41 (13,7%) → **26 (8,7%)** | 54 (18,0%) → **18 (6,0%)** |
| prazna zakrpa | 38 → **24** | 52 → **21** |
| poziva alata po zadatku | 23,8 → **18,8** | 22,4 → **15,0** |
| trošak po rešenom | $0,1006 → **$0,0974** | $0,1111 → **$0,0821** |

**Ishodi hipoteza:**
- **H1 je prešla iz odbijene u potvrđenu** (granično): `str_replace` smanjuje
  trošak po rešenom za −$0,0077 (−10,0%), i to zahvaljujući redu sa pretragom
  (В→Г −$0,0152), dok u redu bez pretrage i dalje ne menja ništa (А→Б +$0,0022).
- **H3 ostaje potvrđena**, sa manjom razlikom: +6,69 п.п. umesto +11,67 п.п.
- **H2 ostaje odbijena**, i to je nalaz koji ispravka nije pomerila u suštini:
  alati za pretragu i dalje poskupljuju pokretanje (+$0,0098), a lokalizaciju ne
  poboljšavaju.

**Šta ovo znači za tvrdnje u radu.** Polazno očekivanje da alati za pronalaženje
neće pomoći malom modelu **ostaje potvrđeno i posle ispravke**, ali iskaz mora da
bude precizniji nego u prvoj verziji rada:

- **više ne važi:** „претрага смањује стопу локализације за 4,7 процентних поена"
  (sada −1,0 п.п., interval prelazi nulu, dakle nema razlike);
- **važi i dalje, čistije:** pretraga košta više po pokretanju, ne donosi bolju
  lokalizaciju, a uslov sa punim skupom alata i dalje rešava najmanje zadataka.

Drugim rečima, deo onoga što je u prvoj verziji izgledalo kao **šteta** od alata
za pretragu bio je defekt implementacije. Ono što ostaje posle ispravke nije
šteta, nego **odsustvo koristi uz veći trošak** — a to je i dalje dovoljno za
zaključak rada da minimalan skup (`bash` + `str_replace`) ima najbolji odnos cene
i učinka.

---

## 1. Šta je tačno ponovljeno

- **Ponovljeni su samo uslovi В (`+претрага`) и Г (`сви алати`)**, svih 300
  instanci, 17. septembra 2026, sa ispravljenim alatom `search` (commit
  `628978d`). Eksperiment: `20260917_154534_batch_300_search_fix`.
- **А и Б su preuzeti iz `batch_300` bez izmena.** Ne koriste `search`, a između
  verzije koja je dala `batch_300` i `628978d` izmenjeni su samo `search` i
  `read_file` (`git diff --stat 6d8505d 628978d -- src evals/swebench`).
- **Spojeni eksperiment:** `artifacts/swebench/experiments/20260915_120759_batch_300_combined`
  (1200 redova: А и Б stari, В и Г novi). Nad njim su računate sve nove vrednosti.
- **Uzrok ponavljanja:** prva verzija `search`-a slala je glob sa putanjom
  (`sympy/**/*.py`) komandi `grep` kao doslovnu putanju, pa je **49,5% poziva u В
  и 56,0% у Г** vraćalo grešku, koju brojač grešaka alata nije video. Detalji:
  `docs/todo/ISSUES.md` #11.
- **Ostale razlike u odnosu na `batch_300`**, sve zabeležene u `ISSUES.md` #12:
  - `git fetch` pre svakog checkout-a je preskočen (isti `base_commit`, bez mreže);
  - sandbox image je noviji i sadrži `ripgrep`; **izmereno: `rg` nije pozvan
    nijednom** u 600 novih pokretanja (u `batch_300` je pokušan u 43/300 В и 25/300 Г);
  - jedno pokretanje (`matplotlib__matplotlib-23476`, uslov В) palo je na
    `APITimeoutError`. Po §2.3 to je infrastrukturni kvar, pa **cela instanca
    ispada iz primarne analize: n = 299** (bilo 300). Analiza osetljivosti: n = 258
    (bilo 256).

---

## 2. Slike

Nove slike su u `docs/media/reeval/`, imenovane kao originalne uz sufiks `_v2`
(`h1_uslovi_v2.png`…). Prekopirati ih u `slike/` foldera rada.

| nova | zamenjuje | šta prikazuje | poruka se menja? |
|---|---|---|---|
| `h1_uslovi_v2.png` | `h1_uslovi.png` | trošak po rešenom po uslovu, sa CI | **da** — `str_replace` sada smanjuje trošak u redu sa pretragom |
| `h1_interval_v2.png` | `h1_interval.png` | interval razlike (Б+Г) − (А+В) | **da** — oba intervala ispod nule, H1 potvrđena |
| `h1_bootstrap_v2.png` | `h1_bootstrap.png` | butstrap raspodela za H1 | da (97,8% uzoraka ispod nule) |
| `h1_razlaganje_v2.png` | `h1_razlaganje.png` | trošak/pokretanje ÷ stopa rešenih | **da** — jeftinije pokretanje uz gotovo istu stopu |
| `h2_tradeoff_v2.png` | `h2_tradeoff.png` | trošak naspram lokalizacije | ne (poruka ista, tačke bliže) |
| `h2_interval_v2.png` | `h2_interval.png` | interval razlike lokalizacije | **da** — interval sada obuhvata nulu |
| `h3_stope_v2.png` | `h3_stope.png` | stope rešenih po uslovu | ne (razlika manja) |
| `h3_interval_v2.png` | `h3_interval.png` | neinferiornost, margina −5 п.п. | ne |
| `h3_bootstrap_v2.png` | `h3_bootstrap.png` | butstrap raspodela za H3 | ne |
| `h3_parovi_v2.png` | `h3_parovi.png` | Б наспрам Г по задацима | **da** — 36 naspram 16, i drugačiji ishodi Г |
| `h3_levak_v2.png` | `h3_levak.png` | razlaganje po fazama | **da** — Г više ne pada na praznim zakrpama |
| `h3_reprodukcija_v2.png` | `h3_reprodukcija.png` | pokretanja koda pre/posle izmene | delimično |
| `h3_repo_v2.png` | `h3_repo.png` | Б наспрам Г по repozitorijumu | **da** — Г sada nadmašuje Б u dva repoa |

Slike su generisane u `notebooks/h1_h3_figures_reeval.ipynb` i
`notebooks/h2_figures_reeval.ipynb` (kopije originalnih, sa `EXP` na spojeni
eksperiment). Naslovi slika su u njima već ažurirani, ali **`\caption{}` u radu
nije** — vidi odeljak 4.

---

## 3. Brojevi, staro → novo

### 3.1 Po uslovima (primarna analiza)

| | А bash | Б +str_replace | В +pretraga | Г svi alati |
|---|---|---|---|---|
| rešeno, staro | 111 (37,00%) | 119 (39,67%) | 105 (35,00%) | 84 (28,00%) |
| **rešeno, novo** | **111 (37,12%)** | **119 (39,80%)** | **112 (37,46%)** | **99 (33,11%)** |
| 95% CI, novo | [31,44; 42,81] | [34,11; 45,48] | [32,11; 43,14] | [27,76; 38,46] |
| trošak po rešenom, staro | $0,0565 | $0,0585 | $0,1006 | $0,1111 |
| **trošak po rešenom, novo** | **$0,0561** | **$0,0583** | **$0,0974** | **$0,0821** |
| 95% CI, novo | [0,0461; 0,0686] | [0,0481; 0,0714] | [0,0793; 0,1200] | [0,0655; 0,1037] |
| Σ trošak, staro → novo | $6,27 → $6,23 | $6,97 → $6,94 | $10,56 → $10,90 | $9,34 → $8,13 |
| trošak po pokretanju, novo | $0,0208 | $0,0232 | $0,0365 | $0,0272 |
| lokalizacija, staro | 78,00% | 77,33% | 74,33% | 71,67% |
| **lokalizacija, novo** | **78,26%** | **77,59%** | **77,26%** | **76,59%** |
| `max_turns`, staro → novo | 4 → 4 | 6 → 6 | **41 → 26** | **54 → 18** |
| prazan patch, staro → novo | 22 → 22 | 31 → 31 | **38 → 24** | **52 → 21** |
| `invalid_prompt`, staro → novo | 23 → 23 | 29 → 29 | 6 → 1 | 3 → 2 |
| poziva alata po zadatku, staro → novo | 15,96 | 15,71 | **23,84 → 18,76** | **22,35 → 14,98** |
| ulaznih tokena po zadatku, novo | 94 683 | 107 486 | 173 639 | 130 135 |

### 3.2 H1 — `str_replace` smanjuje trošak po rešenom

| | staro | novo |
|---|---|---|
| (Б+Г) | $0,0803 | **$0,0691** |
| (А+В) | $0,0779 | **$0,0768** |
| razlika | +$0,0024 (+3,1%) | **−$0,0077 (−10,0%)** |
| 95% CI | [−0,0058; +0,0110] | **[−0,0154; −0,0001]** |
| udeo butstrap uzoraka < 0 | 28,8% | **97,8%** |
| **ishod** | **odbijena** | **potvrđena** |
| osetljivost (n = 258) | +$0,0002, CI [−0,0066; +0,0076] | **−$0,0073, CI [−0,0138; −0,0008], potvrđena** |
| Vilkokson po pokretanju | p = 0,0649 | **p = 2,91·10⁻⁸**, medijana −$0,00288, dᵢ<0 u 205/299 |

Razlaganje, novo: trošak po pokretanju ×0,880, stopa rešenih ×0,978, odnos
troška po rešenom ×0,900.

Efekat `str_replace` po redovima nacrta (eksplorativno):

| | staro | novo |
|---|---|---|
| А→Б | +$0,0021, CI [−0,0063; +0,0104] | +$0,0022, CI [−0,0062; +0,0105] |
| В→Г | +$0,0106, CI [−0,0057; +0,0303] | **−$0,0152, CI [−0,0299; −0,0003]** |
| interakcija | +$0,0085 | **−$0,0175, CI [−0,0350; −0,0001]** |

**Ovo je ključ nove priče za H1:** `str_replace` ne pomaže u redu bez pretrage
(А→Б nepromenjeno), ali jasno pomaže kad pretraga postoji.

### 3.3 H2 — pretraga poskupljuje pokretanje i poboljšava lokalizaciju

| | staro | novo |
|---|---|---|
| trošak po pokretanju (H2a) | +$0,0064, CI [+0,0050; +0,0084] ✓ | **+$0,0098, CI [+0,0075; +0,0123]** ✓ |
| lokalizacija (H2b) | **−4,70 п.п., CI [−8,33; −1,00]** ✗ | **−1,00 п.п., CI [−4,35; +2,34]** ✗ |
| **ishod** | odbijena | odbijena |

Tumačenje se menja: ranije je pretraga **statistički značajno smanjivala**
lokalizaciju, sada se lokalizacija **ne razlikuje** (interval obuhvata nulu).
Holm, primarna familija: `McNemar loc А–В` p = 0,755 i `loc Б–Г` p = 0,771 (oba padaju).

### 3.4 H3 — Б nije lošiji od Г za više od 5 п.п.

| | staro | novo |
|---|---|---|
| R_Б − R_Г | +11,67 п.п. | **+6,69 п.п.** |
| 95% CI | [+7,33; +16,00] | **[+2,01; +11,37]** |
| donja granica − margina | +12,33 п.п. | **+7,01 п.п.** |
| **ishod** | potvrđena | **potvrđena** |
| ceo CI iznad nule | da | da |
| 2×2 (oba / nijedan / samo Б / samo Г) | 78 / 175 / **41** / **6** | 83 / 164 / **36** / **16** |
| McNemar | p = 1,77·10⁻⁷ | **p = 7,79·10⁻³** |
| osetljivost | — | +9,30 п.п., CI [+4,65; +14,34], potvrđena |

Šta je Г radio na zadacima koje je rešio samo Б:

| | staro (41) | novo (36) |
|---|---|---|
| iscrpeo korake | **11** | **3** (prazna zakrpa: 2) |
| pogrešna datoteka | 7 | 9 |
| prava datoteka, pogrešna izmena | 23 | 24 |

Sekundarna familija (McNemar po parovima, Holm): staro su prolazili **Б–Г и В–Г**,
novo prolazi **samo Б–Г** (p = 0,0078). Par В–Г sada pada (p = 0,0789).

### 3.5 Razlaganje po fazama (`h3_levak_v2`)

| faza | А | Б | В (staro → novo) | Г (staro → novo) |
|---|---|---|---|---|
| zakrpa nije prazna | 92,6% | 89,6% | 87,3% → **92,0%** | 82,7% → **93,0%** |
| prava datoteka (ako ima zakrpe) | 84,5% | 86,6% | 85,1% → 84,0% | 86,7% → 82,4% |
| rešeno (ako je datoteka prava) | 45,3% | 49,1% | 45,7% → **46,8%** | 38,1% → **41,5%** |

Г više ne gubi na fazi „zakrpa nije prazna", što je bila glavna tačka pada.

### 3.6 Pokretanja koda (`h3_reprodukcija_v2`, eksplorativno)

| | А | Б | В | Г |
|---|---|---|---|---|
| pre prve izmene | 1,43 | 1,19 | 1,39 | **0,44** (bilo 0,74) |
| posle | 1,73 | 1,39 | 1,09 | 1,22 |
| ukupno | 3,16 | 2,58 | 2,49 | **1,66** (bilo 1,85) |

Mehanizam iz diskusije („Г najređe pokreće kod") **ostaje i pojačava se**, iako Г
sada rešava više zadataka.

### 3.7 Po repozitorijumima (`h3_repo_v2`)

Staro: Б ≥ Г u svih 12 repoa, strogo bolji u 9.
Novo: Б bolji u 5 (`django` 58:50, `sympy` 22:17, `scikit-learn` 12:6, `requests` 6:4,
`seaborn` 2:1), **Г bolji u 2** (`matplotlib` 8:7, `pytest` 5:4), izjednačeni u 5.
Tvrdnja „Б решио најмање онолико колико и Г у свих 12 репозиторијума" **više ne važi.**

---

## 4. Izmene po odeljcima u `Diplomski rad.tex`

Brojevi linija su iz verzije pre izmena i mogu se pomeriti.

| mesto | šta uraditi |
|---|---|
| **Апстракт** (~306) | Zameniti rezultate: Б 119/300 (39,7%), Г 99/300 (33,1%); „алати за претрагу повећали су трошак по покретању, али нису побољшали локализацију" — izbaciti „smanjili su je za 4,7 процентних поена"; dodati da je H1 potvrđena, granično. Zaključna rečenica ostaje ista (minimalan skup je najisplativiji). |
| **Методологија → Поставка експеримента** (~1522) | Dodati 3 rečenice o ponovljenoj evaluaciji В и Г (predlog teksta u odeljku 5 ovog dokumenta). |
| **Резултати → Х1** (1547–1637) | Novi brojevi iz 3.2; slike `h1_*_v2`; zaključak menja smer: hipoteza **potvrđena**, uz ogradu da je granična; dodati nalaz da efekat postoji samo u redu sa pretragom (В→Г). |
| **Резултати → Мера локализације** (1638–1699) | Nove stope: А 78,3%, Б 77,6%, В 77,3%, Г 76,6%; slika `h2_tradeoff_v2`. |
| **Резултати → Х2** (1700–1746) | −1,00 п.п., CI [−4,35; +2,34]; slika `h2_interval_v2`; hipoteza i dalje **odbijena**, ali zato što nema poboljšanja, a ne zato što ima pogoršanja. |
| **Резултати → Х3** (1747–1821) | +6,69 п.п., CI [+2,01; +11,37]; 2×2 83/164/36/16; McNemar p = 0,0078; slike `h3_stope_v2`–`h3_parovi_v2`; u sekundarnoj familiji sada prolazi samo Б–Г. |
| **Дискусија** (1822–1986) | Prepraviti mehanizam pada Г: `max_turns` 54 → 18, prazne zakrpe 52 → 21; ostaje nalaz da Г najređe pokreće kod (3.6); tvrdnju o svih 12 repoa zameniti sa 5/2/5 (3.7); dodati pasus o kvalitetu implementacije alata. |
| **Ограничења** (1987–2118) | Stavku „Резултат важи за ову имплементацију алата" (~2049) prepraviti: izbaciti „нису вратили ниједну грешку у 8 467 позива" i „Мерења говоре против објашњења да су алати неисправни"; navesti defekt i uputiti na novi pododeljak. Dodati stavku o odstupanju od zaključanog plana. |
| **Закључак → Главни налази** (2132) | H1 sada potvrđena (granično), H3 potvrđena, H2 odbijena; teza rada potvrđena sa dve od tri hipoteze. |
| **Закључак → Тумачење / Препоруке** (2159, 2181) | Dodati preporuku da alat za pretragu podržava glob sa putanjom i da greške alata treba meriti nezavisno od toga kako ih alat sam prijavljuje. |
| **Закључак → Даљи рад** (2209) | Izbaciti predlog da se В и Г ponove sa ispravljenim alatom (urađeno). |
| **`\caption{}` uz slike** | Prepraviti tri natpisa koji tvrde suprotno od novih rezultata: uz `h1_interval_v2` („оба интервала обухватају нулу" → „оба интервала леже испод нуле"), uz `h2_interval_v2` („интервал лежи цео испод" → „интервал обухвата нулу"), uz `h2_tradeoff_v2` (ako pominje „чист губитак"). |

---

## 5. Predlog teksta za nova mesta

**Metodologija, posle opisa postavke:**

> Након оцењивања, анализом транскрипата утврђено је да прва верзија алата
> \texttt{search} није подржавала глоб са путањом, због чега је око половине
> позива претраге у условима В и Г враћало грешку уместо резултата, а бројач
> грешака алата то није бележио. Алат је исправљен, а услови В и Г су поновљени
> у целости, са истим нацртом, истим задацима и истим поступком анализе. Услови
> А и Б нису поновљени, јер не користе алате за претрагу, а њихов део система
> није мењан. Резултати који следе односе се на ту комбинацију; првобитне
> вредности за В и Г наведене су у одељку~\ref{sec:defekt}.

**Novi pododeljak u rezultatima (predlog naslova „Утицај дефекта у алату
\texttt{search}", label `sec:defekt`):** tabela sa В и Г pre i posle (iz 3.1),
plus rečenica da se ishod H1 menja, a H3 ostaje.

**Diskusija, novi pasus:**

> Поређење две верзије истог услова показује да мера „ефекта алата" обухвата и
> квалитет његове имплементације. Са истим моделом, истим задацима и истим
> скупом алата, исправка једног дефекта подигла је стопу решених у услову Г са
> 28,0\% на 33,1\%, смањила удео покретања која исцрпе кораке са 18,0\% на
> 6,0\% и променила исход хипотезе Х1. Закључци о скуповима алата зато важе за
> дату имплементацију, што је у складу са налазом \textcite{yang2024sweagent}
> да нацрт интерфејса између агента и рачунара битно утиче на успешност.

---

## 6. Ograde koje moraju da budu napisane

1. **H1 je potvrđena tesno.** Gornja granica primarnog intervala je −$0,0001, a
   97,8% butstrap uzoraka je ispod nule. Analiza osetljivosti potvrđuje isti
   smer (CI [−0,0138; −0,0008]). Prikazati kao granični nalaz.
2. **n = 299 u primarnoj analizi** (jedna instanca isključena zbog
   `APITimeoutError` u uslovu В, po §2.3). Napomenuti pri prvom pominjanju.
3. **Дva pokretanja su spojena.** А и Б су od 15. septembra, В и Г од 17.
   septembra, sa istim modelom i postavkom; razlike su navedene u odeljku 1 ovog
   dokumenta.
4. **Sandbox image u ponovljenom runu sadrži `ripgrep`**, koji u 600 pokretanja
   nije pozvan nijednom. Navesti u fusnoti.
5. **`git fetch` pre checkout-a je preskočen** u ponovljenom runu; isti
   `base_commit`, bez uticaja na agenta.

---

## 7. Čeklista

- [ ] Prekopirati `docs/media/reeval/*.png` u `slike/` rada.
- [ ] Zameniti 13 `\includegraphics` putanja: `slike/h1_uslovi.png` → `slike/h1_uslovi_v2.png` itd.
- [ ] Prepraviti tri `\caption{}` koja tvrde suprotno od novih rezultata.
- [ ] Uneti brojeve iz odeljka 3 u Х1, локализацију, Х2 и Х3.
- [ ] Dodati pasus u metodologiji i novi pododeljak o defektu.
- [ ] Prepraviti apstrakt, diskusiju, ograničenja i zaključak.
- [ ] Proveriti da nigde nije ostalo „8 467 позива", „−4,7 процентних поена",
      „41 од 47", „свих 12 репозиторијума" i „n = 300" gde sada stoji 299.
