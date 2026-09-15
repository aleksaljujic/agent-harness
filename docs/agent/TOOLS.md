# Alati dostupni agentu

Detaljan opis svakog tool-a koji `Agent` (`src/harness/agent.py`) može da
zove preko OpenAI function-calling interfejsa. Za mehanizam registracije i
dispatch-a (kako `HANDLERS["bash"]` postaje pozivljiva funkcija) vidi
`src/harness/tools/__init__.py` i `src/harness/tools/base.py`.

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
| `thought` | string | da (u schema-i) | Zašto se komanda pokreće — **napomena:** postoji u JSON schema-i i označen je `required`, ali `BashArgs` (pydantic model) **nema** `thought` polje. Pydantic po default-u ignoriše nepoznata polja (nema `extra="forbid"`), pa se `thought` tiho odbaci pri `model_validate_json` — model ga mora poslati (schema to zahteva), ali harness ga nigde ne koristi niti loguje. |
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
