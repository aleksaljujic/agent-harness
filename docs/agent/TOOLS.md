# Alati dostupni agentu

Detaljan opis svakog tool-a koji `Agent` (`src/harness/agent.py`) može da
zove preko OpenAI function-calling interfejsa. Za mehanizam registracije i
dispatch-a (kako `HANDLERS["bash"]` postaje pozivljiva funkcija) vidi
`src/harness/tools/__init__.py` i `src/harness/tools/base.py`.

---

## 4.2 Алати агента — текст за рад

> **Напомена (није део текста рада).** Опис одговара коду алата у верзији са
> којом је покренут експеримент `20260915_120759_batch_300` (`harness_sha`
> `6d8505d`; `src/harness/tools/`, `src/harness/scripts/` и
> `src/harness/sandbox.py` од тада нису мењани). Пуне JSON шеме су у
> [прилогу на крају документа](#прилог--пуне-json-шеме-алата).
>
> **Мерење колоне „шема".** Сваки број је измерен директно на моделу
> `gpt-5.4-nano`, а не процењен: исти минимални захтев (једна корисничка порука)
> послат је без алата и са алатима, а резултат је разлика у `prompt_tokens`.
> Када је присутан бар један алат, модел плаћа и фиксних **98 токена** за оквир
> листе алата. Тај износ се рачуна једном по позиву, без обзира на то колико је
> алата у листи. Појединачни алати мерени сами дају 98 + маргинални износ
> (`bash` 135, `str_replace` 321, `search` 141, `read_file` 189, `find_file`
> 203), а збирови по условима се поклапају са мерењем целих листи (А 135, Б 358,
> В 374, Г 597). Бројање JSON текста шеме токенизатором `o200k_base` даје друге
> вредности (84 / 310 / 87 / 148 / 154), јер модел шему не види као JSON. Зато су
> у табели вредности са API-ја.

Агент у експерименту има на располагању највише пет алата. Модел сваки алат
види као опис функције са шемом параметара, а та шема се шаље уз **сваки** позив
модела, без обзира на то да ли ће алат у том кораку бити употребљен. Пре
извршавања харнес проверава аргументе према шеми. Неисправни аргументи или
непознат алат не прекидају рад: грешка се враћа моделу као обичан текстуални
резултат, на који он може да реагује у следећем кораку.

Сви алати раде у истом изолованом контејнеру, у директоријуму `/work`, у коме се
налази изворни код пројекта. Контејнер у експерименту нема приступ мрежи. Алати
`bash` и `search` се своде на једну команду љуске, а `str_replace`, `read_file`
и `find_file` у контејнеру покрећу кратку скрипту. Излаз сваког алата ограничен
је на 8000 знакова. Дужи излаз се сече и на крај се додаје напомена да је
приказ непотпун.

| алат | намена | обавезни параметри | опциони параметри | ограничење излаза | шема (токени) |
|---|---|---|---|---|---:|
| `bash` | произвољна команда љуске | команда, образложење | — | 8000 знакова, 60 s | 37 |
| `str_replace` | измена постојеће датотеке | путања, стари текст, нови текст | све појаве, редни број појаве | — | 223 |
| `search` | претрага садржаја по регуларном изразу | образац | филтер датотека | 50 погодака | 43 |
| `read_file` | читање датотеке са бројевима линија | путања | почетна и завршна линија | 8000 знакова | 91 |
| `find_file` | претрага датотека по имену | образац | највећи број резултата (100) | 100 резултата | 105 |

Колона „шема" даје број улазних токена које опис алата додаје сваком позиву
модела. Кад је у листи бар један алат, томе се једном додаје још 98 токена за
оквир листе. Услови из нацрта 2×2 тако носе по позиву: А (`bash`) 135, Б (уз
`str_replace`) 358, В (уз групу за претрагу) 374 и Г (сви алати) 597 токена.
Сам `str_replace` (223) кошта скоро колико цела група `search`, `read_file` и
`find_file` заједно (239), јер његов опис садржи упутства за случај
вишеструког поклапања. Харнес има и шести алат, `run_tests`, за покретање
тестова са структурисаним резултатом. Он није био део експеримента, јер у овој
поставци агент ради без покретања тестова пројекта.

### 4.2.1 `bash`

`bash` је основни алат и једини који је присутан у сваком услову. Сам по себи
довољан је за решавање задатка: кроз њега агент може да претражује, чита и мења
датотеке, али без икакве контроле над обликом и обимом излаза. Алат прима
команду љуске и враћа спојен стандардни излаз и излаз за грешке.

Шема има два обавезна параметра: саму команду и поље за образложење. У то поље
модел пре сваког позива кратко наводи зашто покреће команду. Харнес образложење
не користи при извршавању. Оно ипак остаје у историји разговора, па га модел
види у наредним корацима, а сачувано је и у транскриптима покретања.

Свака команда се извршава као нов процес љуске у `/work`. Стање попут промене
директоријума или променљивих окружења зато се не преноси из једног позива у
други, па модел зависне кораке мора да споји у једну команду.

Излаз дужи од 8000 знакова се сече. На крај се додаје напомена о томе колико је
знакова изостављено, уз савет да се команда сузи, како модел непотпун приказ не
би схватио као целину. Команда која траје дуже од 60 секунди се прекида, а модел
добија поруку о истеку времена. Ако команда не произведе никакав излаз, враћа се
само њен излазни код. Тако се празан резултат разликује од грешке, а модел зна
да ли је тиха команда успела.

### 4.2.2 `str_replace`

`str_replace` мења постојећу датотеку тако што тачно наведени текст замени
новим, без поновног генерисања целе датотеке. Обавезни параметри су путања,
стари и нови текст. Поклапање је дословно, а не по регуларном изразу, па знакови
који су у коду чести (тачка, звездица, заграде) не морају да се означавају.

Подразумевано, стари текст мора да се појави **тачно једном**. Ако га нема,
модел добија грешку са саветом да прочита датотеку и препише текст заједно са
увлачењем. Ако се појављује више пута, измена се не врши, а порука наводи број
појава и број линије сваке од њих. Порука уз то саветује да се стари текст
прошири **навише**, до претходног коментара или дефиниције функције или класе,
јер су поновљени блокови кода обично једнаки и испод, па ширење наниже ретко
разрешава двосмисленост. Ова провера је безбедносно својство алата: без ње би
измена тихо погодила погрешно место.

За намерно вишеструке измене постоје два опциона параметра. Један мења све
појаве, а други само N-ту појаву по редоследу у датотеци (бројано од 1). Они се
међусобно искључују. Њихова комбинација, као и редни број ван опсега, враћа
грешку са стварним бројем појава. После успешне измене модел добија број
замењених појава и линије на којима су биле.

Алат постоји зато што је ово једина операција коју `bash` ради лоше. `sed` ради
ред по ред, па не може да обухвати блок од више линија. Сваки посебан знак из
кода мора да се означи. Над обрасцем који се јавља више пута `sed` тихо мења све
појаве, без упозорења.

### 4.2.3 `search`

`search` претражује садржај датотека у целом пројекту по проширеном регуларном
изразу. Обавезан параметар је образац. Опциони филтер има два значења. Ако не
садржи косу црту, тумачи се као образац имена датотеке (на пример, све Python
датотеке). Ако садржи косу црту, тумачи се као путања датотеке или
директоријума на коју се претрага ограничава. Ова подела постоји зато што се
филтер по имену пореди само са основним именом датотеке, па би путања као
филтер тихо промашила све датотеке.

Сваки погодак се враћа у једном реду: путања, број линије и садржај линије. Тај
облик је непосредно употребљив за `read_file` и `str_replace`. Директоријуми са
историјом верзија (`.git`) и инсталираним зависностима (`node_modules`) се
прескачу, јер у њима нема кода који агент треба да мења, а стварају много шума.

Алат враћа највише **50 погодака**, редоследом обиласка датотечног система, а не
по релевантности. Када погодака има више, остали се одбацују **без икакве
назнаке**: модел не добија ни укупан број погодака ни ознаку да је листа
скраћена. По томе се `search` разликује од `find_file`. Уз то важи и општа
граница од 8000 знакова, па дугачке линије могу да пресеку излаз и пре 50.
погодка, овај пут уз напомену. Када нема погодака, модел добија изричиту поруку
уместо празног излаза. Неисправан регуларни израз враћа поруку о грешци.

Алат не даје агенту ништа што `bash` већ не може. Његова вредност је у
ограничавању излаза: необуздана рекурзивна претрага над правим репозиторијумом
може једним позивом да попуни контекст.

### 4.2.4 `read_file`

`read_file` чита датотеку и враћа њен садржај са бројевима линија. Обавезан
параметар је путања. Опциони су почетна и завршна линија, које се броје од 1 и
улазе у опсег. Без њих се враћа цела датотека.

Сваки ред излаза почиње бројем линије и табулатором. Бројеви линија повезују
алате: погоци из `search` и грешке из `str_replace` наводе линије, па агент може
одмах да затражи тачан опсег. Број линије није део датотеке, па опис
`str_replace` изричито упозорава да се тај префикс уклони пре него што се текст
препише у стари текст. У супротном тражени текст неће бити пронађен.

Опсег се проверава пре читања. Грешку враћају почетна линија мања од 1, почетна
линија после завршне и почетна линија после краја датотеке. Порука у последњем
случају наводи и колико линија датотека има. Завршна линија после краја
датотеке није грешка: тихо се своди на последњу линију, јер „читај до краја" је
уобичајена намера. У томе је разлика у односу на `bash`: исечак датотеке са
погрешним опсегом тамо не враћа ништа осим излазног кода, а овде грешку по којој модел може
да поступи.

Посебне поруке постоје и за непостојећу датотеку, за директоријум и за
датотеку која није у кодирању UTF-8. Празна датотека даје изричиту поруку да је
празна. Алат нема сопствено ограничење броја линија, па важи општа граница од
8000 знакова. Велика датотека прочитана без опсега се сече уз напомену, и агент
тада треба да је чита по деловима.

### 4.2.5 `find_file`

`find_file` тражи датотеке по имену или путањи, а не по садржају, за шта служи
`search`. Обавезан параметар је образац. Опциони параметар одређује највећи
број резултата и подразумевано износи 100.

Ако образац садржи џокер знакове (звездицу, упитник или угласту заграду),
тумачи се као глоб. Пореди се и са именом датотеке и са њеном путањом у односу
на корен пројекта, па раде и обрасци по имену (све Python датотеке) и обрасци
по путањи (тестови у одређеном поддиректоријуму). Образац без џокер знакова
тумачи се као део имена датотеке, уз разликовање великих и малих слова. Враћају
се само датотеке, не и директоријуми. Као и код `search`, прескачу се `.git` и
`node_modules`.

Резултат је списак релативних путања, по једна у реду, **абецедно уређен**, па
исти упит увек даје исти редослед. Када погодака има више од граничне
вредности, приказује се првих N, а на крају се додаје ред са **укупним бројем
погодака** („приказано првих N од M"). За разлику од `search`, модел тако зна
да је списак непотпун и колико треба да сузи образац. Када погодака нема, модел
добија изричиту поруку.

Као и `search`, овај алат не доноси нову могућност, јер исто може да се уради
кроз `bash`. Разлика је у облику излаза: `find` има заставице које модел мора
сваки пут да погоди, и излаз му није ограничен. `find_file` уместо тога увек
даје исти, ограничен и уређен облик резултата.

---

## Arhitektura tool-a

Svaki tool je definisan u svom fajlu pod `src/harness/tools/<name>.py` i
sastoji se od četiri dela, spakovanih u `Tool` dataclass
(`src/harness/tools/base.py`):

```python
@dataclass(frozen=True)
class Tool:
    name: str            # ime kojim ga model zove
    args_model: Type[BaseModel]   # pydantic model za validaciju argumenata
    definition: dict      # OpenAI function-calling JSON schema
    handler: Callable     # (sandbox, args) -> str
```

`src/harness/tools/__init__.py` skuplja sve `TOOL` objekte u `_TOOLS`, pa
pravi tri rečnika po imenu: `REGISTRY`, `SCHEMAS`, `HANDLERS`. `agent.py`
koristi `SCHEMAS` da validira argumente koje model pošalje (`model_validate_json`)
i `HANDLERS` da pozove pravu funkciju (`_dispatch`, `agent.py:96-110`).

Dva obrasca izvršavanja:
- **Direktno u sandbox-u** (`bash`, `search`) — handler sastavi shell komandu
  i pozove `sandbox.run(cmd)` direktno.
- **Preko `run_script`** (`str_replace`, `read_file`, `find_file`, `run_tests`) —
  handler serijalizuje argumente u JSON, `run_script()` (`base.py`) ga piše
  na stdin Python skripte unutar kontejnera
  (`/opt/agent-scripts/<script>.py`), i vraća njen stdout kao string. Ovaj
  obrazac koristi se kad je logika composnija od jedne shell komande
  (parsiranje, offset-based replace, JSON izlaz).

Svaki handler takođe ispisuje `rich.Panel` na host-side konzolu (za praćenje
uživo tokom run-a) pre nego što vrati rezultat modelu — to je čisto UX, ne
utiče na ono što model vidi.

---

## `bash`

**Fajl:** `src/harness/tools/bash.py` — nema prateću skriptu, radi direktno
preko `sandbox.run()`.

Izvršava proizvoljnu bash komandu u `/work` unutar sandbox kontejnera i
vraća `stdout + stderr` kombinovano.

| Argument | Tip | Obavezan | Opis |
|---|---|---|---|
| `thought` | string | da (u schema-i) | Zašto se komanda pokreće — **napomena:** postoji u JSON schema-i i označen je `required`, ali `BashArgs` (pydantic model) **nema** `thought` polje. Pydantic po default-u ignoriše nepoznata polja (nema `extra="forbid"`), pa se `thought` tiho odbaci pri `model_validate_json` — model ga mora poslati (schema to zahteva), ali handler ga ne koristi. Ostaje ipak u `arguments` tool call-a, pa je deo istorije poruka (model ga vidi u narednim koracima) i sačuvan je u `messages/*.json` transkriptima. |
| `command` | string | da | Bash komanda za izvršavanje. |

**Ponašanje:**
- Output se odseca na `MAX_OUTPUT = 8000` karaktera (`sandbox.py`); preko
  toga se dodaje `... [truncated N more chars; narrow the command]` da model
  zna da je pogled nepotpun.
- Nema built-in retry ni timeout specifičan za ovaj tool — koristi default
  iz `sandbox.run()`.
- Ovo je jedini tool koji je uvek prisutan — `all_tool_combinations`
  (`evals/pipeline.py:16`) zahteva `bash` u svakoj generisanoj kombinaciji.

---

## `search`

**Fajl:** `src/harness/tools/search.py` — bez prateće skripte, wrapper oko
`grep -rn`.

Pretražuje sadržaj fajlova po regex-u; vraća redove oblika
`path:line:content`, max 50 pogodaka.

| Argument | Tip | Obavezan | Opis |
|---|---|---|---|
| `pattern` | string | da | Regex (prosleđuje se `grep -E`). |
| `glob` | string, opciono | ne | Filter fajlova, npr. `*.py`. |

**Ponašanje / poznati detalji (vidi [ISSUES.md #3](../todo/ISSUES.md)):**
- Ako `glob` **sadrži `/`** (npr. pun path `sphinx/ext/autodoc/__init__.py`),
  koristi se kao **cilj pretrage** (`grep ... {target}`) umesto kao
  `--include` filter — jer `--include` poredi samo basename fajla, pa bi
  glob sa `/` inače tiho promašio sve.
- Ako `glob` **nema `/`** (npr. `*.py`), koristi se kao `--include=<glob>`
  filter nad pretragom celog stabla (`.`).
- Prazan rezultat (ili sandbox-ov string za "nema izlaza",
  `"Without return..."`) se normalizuje u `"No matches."` — model ne vidi
  interne sandbox stringove.
- Isključuje `.git` i `node_modules` (`--exclude-dir`).
- Rezultat je hard-capped na 50 linija (`| head -50`) — nema signala modelu
  koliko je ukupno pogodaka postojalo iznad tog limita (za razliku od
  `find_file`, koji eksplicitno piše "truncated, showing first N of M").

---

## `str_replace`

**Fajl:** `src/harness/tools/str_replace.py` + skripta
`src/harness/scripts/str_replace.py`.

Menja tačan string u fajlu. Osnovni mod zahteva da `old_str` bude jedinstven
u fajlu; opciono može da promeni sve pojave ili tačno određenu.

| Argument | Tip | Obavezan | Opis |
|---|---|---|---|
| `path` | string | da | Putanja fajla. |
| `old_str` | string | da | Tačan tekst za zamenu, uključujući whitespace. |
| `new_str` | string | da | Tekst zamene. |
| `replace_all` | bool, default `false` | ne | Zameni **sve** pojave `old_str`. |
| `occurrence` | int, opciono, 1-indexed | ne | Zameni samo N-tu pojavu (po redosledu u fajlu). |

`replace_all` i `occurrence` su **međusobno isključivi** — validacija postoji
na dva mesta: pydantic `model_validator` (`StrReplaceArgs`, host-side, pre
slanja u sandbox) i ponovo u samoj skripti (`str_replace.py:18`, u
kontejneru) kao odbrambena provera.

**Algoritam skripte** (`src/harness/scripts/str_replace.py`):
1. Nađe **sve** offsete pojavljivanja `old_str` (`src.find` u petlji, ne
   samo `src.count`) — potrebno da bi se izračunali brojevi linija za svaku
   pojavu.
2. Ako `old_str` nije nađen → `"ERROR: old_str not found..."`.
3. Ako `occurrence` van opsega → greška sa tačnim brojem pojava.
4. Ako ima **>1 pojava** i nije prosleđen ni `replace_all` ni `occurrence` →
   vrati grešku koja **imenuje broj linije svake pojave** i savetuje
   proširivanje `old_str` **naviše** (jer su duplikati u kodu tipično
   identični i ispod, pa širenje nadole nikad ne razrešava dvosmislenost —
   vidi [ISSUES.md #3](../todo/ISSUES.md) za incident koji je ovo motivisao).
5. Zamena se vrši **od kraja fajla ka početku** (`for o in reversed(targets)`)
   da ranije izračunati offseti ostanu validni dok se kasniji zamenjuju.
6. Uspeh: `"OK: replaced N occurrence(s) in <path> (lines ...)"`.

**Napomena o `read_file` interakciji:** `read_file` vraća sadržaj sa
prefiksom broja linije (`"%6d\t"`); ako se taj prefiks slučajno kopira u
`old_str`, pretraga neće naći tekst (`ERROR: old_str not found`). Ovo je
eksplicitno navedeno u `DEFINITION.description` da bi model znao da ga
skine.

---

## `read_file`

**Fajl:** `src/harness/tools/read_file.py` + skripta
`src/harness/scripts/read_file.py`.

Čita fajl i vraća sadržaj sa brojevima linija (kao `cat -n`), opciono
ograničen na opseg.

| Argument | Tip | Obavezan | Opis |
|---|---|---|---|
| `path` | string | da | Putanja fajla. |
| `start_line` | int, opciono | ne | Prva linija (1-indexed, inclusive). |
| `end_line` | int, opciono | ne | Poslednja linija (inclusive). |

**Ponašanje:**
- Format izlaza: `f"{i:6d}\t{lines[i-1]}"` po liniji — 6-cifreni broj linije,
  tab, sadržaj.
- Validacije, redom: `start_line`/`end_line` moraju biti int → `start_line >= 1`
  → `start_line <= end_line` → `start_line` ne sme biti posle kraja fajla.
  `end_line` preko kraja fajla se tiho skraćuje na `total` (nije greška).
- Prazan fajl vraća `"OK: <path> is empty"` umesto praznog stringa (da se
  razlikuje od greške/no-op-a).
- Greške: `FileNotFoundError`, `UnicodeDecodeError` (non-UTF-8 fajl),
  `IsADirectoryError`, generički `OSError` — svaka sa specifičnom porukom.

---

## `find_file`

**Fajl:** `src/harness/tools/find_file.py` + skripta
`src/harness/scripts/find_file.py`.

Traži fajlove po **imenu/putanji**, ne po sadržaju (za sadržaj koristi
`search`).

| Argument | Tip | Obavezan | Opis |
|---|---|---|---|
| `pattern` | string | da | Glob (`*.py`, `src/**/test_*.py`) ili substring imena fajla ako nema glob karaktera. |
| `limit` | int, opciono | ne | Max broj rezultata, default 100. |

**Ponašanje:**
- Detektuje da li `pattern` sadrži glob karaktere (`*`, `?`, `[`) —
  ako da, poredi i `fnmatch(name, pattern)` (samo basename) i
  `fnmatch(rel, pattern)` (pun relativni path), pa hvata i `*.py` i
  `src/**/test_*.py` stilove. Ako ne, tretira `pattern` kao **substring**
  imena fajla (case-sensitive).
- Isključuje `.git` i `node_modules`.
- Rezultati sortirani alfabetski, ograničeni na `limit`; ako ih ima više,
  dodaje `"... (truncated, showing first N of M)"` — za razliku od
  `search`, ovde model **vidi** ukupan broj pogodaka.
- Nema pogodaka → `"No files found."`.

---

## `run_tests`

**Fajl:** `src/harness/tools/run_tests.py` + skripta
`src/harness/scripts/run_tests.py`.

Pokreće `pytest` i vraća **strukturisan** JSON rezultat (ne sirovi stdout).

| Argument | Tip | Obavezan | Opis |
|---|---|---|---|
| `tests` | list[string] | da | Test node id-jevi (`"test_math.py::test_add"`), ili `["all"]` da pokrene sve pod `path`. |
| `path` | string, default `"."` | ne | Root za kolekciju kad je `tests == ["all"]`. |

Pydantic validator (`_nonempty`) odbija praznu listu ili listu koja sadrži
ne-string/prazan element, sa porukom koja podseća na `["all"]` konvenciju.

**Ponašanje skripte:**
- Pokreće `pytest -q --no-header -p no:cacheprovider --tb=short --junit-xml <tmp>`
  sa `subprocess.run`, **timeout 280s** internog pytest poziva
  (`PYTEST_TIMEOUT`), dok je **spoljni** sandbox exec timeout za ovaj tool
  postavljen na **300s** (`DOCKER_EXEC_TIMEOUT` u `run_tests.py` tool
  wrapperu — override-uje sandbox-ov default od 60s, jer test suite-ovi
  mogu biti spori).
- Ako pytest padne sa exit kodom `2/3/4` (interna greška, ne test failure)
  ili XML report nije napisan → vraća `collection_error` sa poslednjih 25
  linija stdout+stderr (npr. import error, syntax error u test fajlu).
- Inače parsira JUnit XML: `passed`/`failed`/`errors`/`skipped` liste
  node-id-jeva, plus `failure_details` — **jedna linija** po padu (prva
  linija `message` atributa, ili poslednja linija teksta elementa, capped na
  300 karaktera) da model ne dobije ogroman traceback po testu.
- `summary` uključuje `duration_seconds` (zbir `time` atributa svih
  `<testsuite>` elemenata).
- Timeout na nivou subprocess-a (280s prekoračeno) → `{"error": "pytest timed out after 280s"}`,
  bez ijednog test rezultata.

---

## Sažetak: koji tool ide preko `run_script`

| Tool | Direktno u sandbox-u | Preko `run_script` (skripta u kontejneru) |
|---|---|---|
| `bash` | ✅ | |
| `search` | ✅ (grep) | |
| `str_replace` | | ✅ `str_replace.py` |
| `read_file` | | ✅ `read_file.py` |
| `find_file` | | ✅ `find_file.py` |
| `run_tests` | | ✅ `run_tests.py` (sa produženim timeout-om) |

Za listu alata koje agent stvarno koristi u datom run-u (i njihovu
kombinaciju) vidi `--combo` u `scripts/run_swebench.py` i
`get_active_tools()` u `src/harness/tools/__init__.py`.

---

## Прилог — пуне JSON шеме алата

Шеме тачно онако како се шаљу моделу (`TOOL.definition` из `src/harness/tools/<алат>.py`), за пет алата из експеримента.

### `bash`

```json
{
  "type": "function",
  "function": {
    "name": "bash",
    "description": "Executing bash command in /work and return stdout+stderr.",
    "parameters": {
      "type": "object",
      "properties": {
        "thought": {
          "type": "string",
          "description": "Why you run this command."
        },
        "command": {
          "type": "string"
        }
      },
      "required": [
        "thought",
        "command"
      ]
    }
  }
}
```

### `str_replace`

```json
{
  "type": "function",
  "function": {
    "name": "str_replace",
    "description": "Replace an exact string in a file. old_str must include exact indentation. By default old_str must appear exactly once; if it appears more than once, the error reports the line number of every match. Note: read_file output is prefixed with '<line>\\t' — strip that prefix before using its text as old_str. Duplicated code blocks are often identical below as well as above, so if old_str isn't unique, prefer extending it UPWARD (the preceding comment/def/class line) rather than downward. Pass replace_all=true to change every occurrence, or occurrence=N (1-based, in file order) to target one specific match. Prefer this over rewriting whole files.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "File path, e.g. utils.py"
        },
        "old_str": {
          "type": "string",
          "description": "Exact text to replace, including whitespace"
        },
        "new_str": {
          "type": "string",
          "description": "Replacement text"
        },
        "replace_all": {
          "type": "boolean",
          "description": "Replace every occurrence of old_str instead of requiring a unique match."
        },
        "occurrence": {
          "type": "integer",
          "description": "1-based index (in file order) of the specific occurrence to replace."
        }
      },
      "required": [
        "path",
        "old_str",
        "new_str"
      ]
    }
  }
}
```

### `search`

```json
{
  "type": "function",
  "function": {
    "name": "search",
    "description": "Search files by regex. Returns path:line:content, max 50 hits.",
    "parameters": {
      "type": "object",
      "properties": {
        "pattern": {
          "type": "string"
        },
        "glob": {
          "type": "string",
          "description": "e.g. *.py, optional"
        }
      },
      "required": [
        "pattern"
      ]
    }
  }
}
```

### `read_file`

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file and return line-numbered content (like `cat -n`). Optionally restrict to a 1-indexed inclusive line range via start_line and/or end_line.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "File path, e.g. utils.py"
        },
        "start_line": {
          "type": "integer",
          "description": "First line to read, 1-indexed, optional"
        },
        "end_line": {
          "type": "integer",
          "description": "Last line to read, inclusive, optional"
        }
      },
      "required": [
        "path"
      ]
    }
  }
}
```

### `find_file`

```json
{
  "type": "function",
  "function": {
    "name": "find_file",
    "description": "Find files by name or path, not by contents (use search for contents). pattern is a glob (e.g. *.py, src/**/test_*.py); if it has no glob characters it is matched as a substring of the filename. Returns matching relative paths, one per line, capped at 100 (override with limit).",
    "parameters": {
      "type": "object",
      "properties": {
        "pattern": {
          "type": "string",
          "description": "Glob like *.py, or a filename substring"
        },
        "limit": {
          "type": "integer",
          "description": "Max results, default 100"
        }
      },
      "required": [
        "pattern"
      ]
    }
  }
}
```
