# Agent Harness — Kompletna konverzacija

Transkript cele sesije, organizovan po fazama razvoja. Sačuvano za kasnije čitanje/referencu.

---

## 1. Uvod — šta je agent harness

**Pitanje:** Zelim da napravim sopstveni agent harness kako da pocenm?

Objašnjeno da je harness u suštini jedna petlja: pošalji poruke i tool definicije modelu → ako nema tool_use, ispiši tekst i završi → ako ima, izvrši svaki poziv i vrati rezultat nazad u kontekst → ponovi. Sve ostalo (sandbox, alati, evali) je ono što se dodaje oko te petlje.

Ključne preporuke:
- Krenuti od najprostijeg (bash + read/write fajlova), ne od 20 specijalizovanih alata
- Greške treba vraćati modelu kao tool_result, ne rušiti petlju
- Sandbox je obavezan pre puštanja agenta bez nadzora
- Stop uslovi (max iteracija, detekcija petlji) su nužni
- Upravljanje kontekstom (sažimanje starih poruka) postaje bitno na dužim sesijama

**Pitanje:** bash tool znaci da moram da ima dosta bash funkcija?

Ne — `bash` je JEDAN alat sa JEDNIM parametrom (`command`). Model piše komande, harness ih samo izvršava kroz `subprocess.run(command, shell=True, ...)`. Bez potrebe za posebnim `ls`, `grep`, `find` alatima — bash pokriva sve to kroz kompoziciju.

**Pitanje:** koliko je potrebno estimirano vreme, ima li kurs/rad, ili sam da probam intuitivno?

Preporučeno: praksa prva, evali kao merni instrument. Reference:
- Anthropic: *Building Effective Agents*, *Writing Tools for Agents*
- LangChain Terminal-Bench nalaz: promena harness-a (isti model) pomerila rezultat sa ~30. mesta u top 5
- Praktičan kurs: *Building a Coding Agent From Scratch*

Vremenska procena: prva petlja 2-4h, Docker sandbox pola dana-dan, solidan lični alat 2-4 nedelje part-time.

---

## 2. Docker sandbox

**Pitanje:** hocu docker sa cim da krenem?

Prvo testirati sandbox BEZ agenta (ručne `docker run`/`docker exec` komande), pa tek onda spajati sa petljom. Objašnjeno:
- `-v host:kontejner` = bind mount, preslikavanje putanje, ne kopiranje — fajlovi nastaju TRENUTNO na hostu jer su isti inode-ovi
- `--user $(id -u):$(id -g)` — da fajlovi ne budu root-ovi
- `--pids-limit`, `--memory` — zaštita od fork bombe
- Sandbox ≠ apstrakcija oko Docker-a, sandbox JE kontejner; klasa `Sandbox` je samo daljinski upravljač

**Ključna distinkcija (Claude Code vs. kontejner):**
- Claude Code radi BEZ Docker-a, direktno na hostu, sa eksplicitnim pitanjima pre svake destruktivne komande — "čovek je granica"
- Kontejner se koristi kad nema čoveka koji klikće "da" (CI, autonomni agenti, obrada nepoverljivog sadržaja) — "kernel je granica"
- Docker izolacija je selektivna: štiti od grešaka agenta unutar mount-a je NE štiti (to je dozvola koju si sam dao)

**Rešene greške tokom setupa:**
- `permission denied` na docker.sock → korisnik nije u `docker` grupi → `usermod -aG docker $USER` + puna odjava
- Fish shell vs bash sintaksa (`$(...)` ne radi u fish) → korišćenje `bash -c` za jednokratne komande
- Docker tiho pravi NEPOSTOJEĆI mount folder KAO ROOT → uzrok kasnijih "Permission denied" grešaka pri pisanju iz kontejnera → rešeno sa `os.makedirs(workdir, exist_ok=True)` u `Sandbox.__init__` PRE `docker run`
- `capture_output=True` uz `check=True` je skrivao pravu Docker grešku → dodata eksplicitna provera `if p.returncode != 0: raise RuntimeError(p.stderr)`

Finalna verzija `sandbox.py`:
```python
import os, subprocess, uuid

class Sandbox:
    def __init__(self, workdir):
        workdir = os.path.abspath(workdir)
        os.makedirs(workdir, exist_ok=True)
        if not os.access(workdir, os.W_OK):
            raise RuntimeError(f"workdir not writable: {workdir}")
        self.name = f"agent-{uuid.uuid4().hex[:8]}"
        p = subprocess.run([
            "docker", "run", "-d", "--name", self.name,
            "--memory", "2g", "--pids-limit", "256",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{workdir}:/work",
            "-w", "/work",
            "agent-sandbox", "sleep", "infinity"
        ], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"docker run fail:\n{p.stderr}")

    def run(self, command, timeout=60):
        try:
            p = subprocess.run(
                ["docker", "exec", self.name, "bash", "-lc", command],
                capture_output=True, text=True, timeout=timeout
            )
            return (p.stdout + p.stderr)[:8000] or f"(no output, exit={p.returncode})"
        except subprocess.TimeoutExpired:
            return f"Error: timed out after {timeout}s"

    def destroy(self):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
```

---

## 3. Prva petlja (Azure OpenAI)

**Pitanje:** koristim open ai azure za model.

Klijent:
```python
from openai import OpenAI
client = OpenAI(base_url=settings.azure_openai_endpoint, api_key=settings.azure_openai_api_key)
```

**Rešene greške:**
- 404 → endpoint sadržao dupli `/openai/` jer je korišćen `AzureOpenAI` klijent sa `/openai/v1` sufiksom već u URL-u → rešeno prelaskom na obični `OpenAI` klijent sa `base_url` = ceo Foundry `/openai/v1` endpoint
- 401 (satima) → `curl` sa `source .env` je radio, Python nije → uzrok: **stari API ključ zaglavljen u `.zshrc`/env varijabli**, koji je pregazio `.env` jer `pydantic-settings` daje prioritet pravim env varijablama nad `.env` fajlom. Lekcija zapisana u NOTES: kad `curl` radi a SDK ne sa istim izvorom, prva provera je `env | grep AZURE`, ne header format.

Prvi eval test: `run_agent(task, sandbox)` — petlja koja šalje `messages` + `tools`, čita `tool_calls`, dispečuje ka `bash`, vraća rezultat kao `role: tool` poruku.

---

## 4. Evali

**Princip:** provera MORA gledati stanje sandboxa (`sandbox.run("cat file")`), NIKAD tekst koji je model izjavio da je uradio.

Prvi set (9 zadataka): hello, numbers, fix-bug, merge-txt, count, pytest, syntax, no-network, missing-file, dont-delete, csv, refactor.

**Otkrivene greške u samim evalima (ne u modelu):**
- `refactor` provera gledala samo IZLAZ programa (`7`, `12`) — model je prošao a da NIJE ništa izmenio, jer je originalni kod već ispravno radio. Popravljeno dodavanjem provere da `"def "` postoji u fajlu.
- `pytest` je stalno padao jer `pytest` NIJE bio instaliran u Docker image-u — greška infrastrukture, ne modela. Rešeno Dockerfile-om.
- `no-network` test je "prolazio" jer mreža nije bila isključena — testirao je pogrešnu stvar.

**Varijansa:** isti kod, tri pokretanja → 8/9, 7/9, 8/9. Zaključak: jedan eval run ne znači ništa, treba 3+ ponavljanja i prosek.

---

## 5. str_replace alat

Motivacija: model dosledno koristi `cat > file <<EOF` za prepisivanje CELOG fajla čak i za izmenu od 2 reda — skupo (30k+ tokena za trivijalnu izmenu) i rizično (gubitak koda).

Implementacija — LITERALNO poređenje (ne regex), sa proverom jedinstvenosti:
```python
def do_str_replace(sandbox, path, old_str, new_str):
    payload = json.dumps({"path": path, "old": old_str, "new": new_str})
    return sandbox.run(f"printf %s {shlex.quote(payload)} | python3 /opt/agent-scripts/str_replace.py")
```

Skripta u kontejneru (`/opt/agent-scripts/str_replace.py`):
```python
d = json.loads(base64.b64decode(...))
n = src.count(d["old"])
if n == 0: print("ERROR: old_str not found...")
elif n > 1: print(f"ERROR: old_str appears {n} times, must be unique...")
else: ...write... ; print("OK: replaced")
```

**Ključna lekcija:** izlaz alata JE prompt. Poruka `"old_str appears 2 times, must be unique. Include more surrounding lines."` naveo je model da sam pročita kontekst i ispravi poziv — bez intervencije. Prazna/nejasna poruka (`"Without return, exit=0"`) izazivala je lutanje ili odustajanje od alata.

**Problem koji je trajao satima:** model NIJE koristio str_replace uprkos postojanju alata → uzrok: opis alata kaže "Prefer this", ne "MUST use". System prompt ojačan:
```
When modifying an EXISTING file, you MUST use str_replace for each change.
Never rewrite a file that already exists. Multiple str_replace calls are
expected and preferred over one full rewrite.
```

**Bagovi usput:**
- Putanja skripte pomešana (host path + container path spojeni) → `python3: can't open file '.../scripts/opt/agent-scripts/str_replace.py'` → rešeno hardkodiranjem `/opt/agent-scripts/...` (container-side put) u `do_str_replace`, dok `settings.scripts` (host-side put) ostaje samo u `sandbox.py` za mount.
- `do_str_replace` vraćao `None` u nekim granama → `content: null` u OpenAI API-ju → 400 greška JEDAN poziv kasnije, daleko od uzroka → rešeno sa `str(out) if out is not None else "(no output)"` u petlji pre `messages.append`.

---

## 6. search alat

```python
def do_search(sandbox, pattern, glob=None):
    include = f"--include={shlex.quote(glob)}" if glob else ""
    cmd = f"grep -rn {include} --exclude-dir=.git --exclude-dir=node_modules -E {shlex.quote(pattern)} . | head -50"
    out = sandbox.run(cmd).strip()
    if not out: return "No matches."
    return out
```

Poenta: `search` ne dodaje SPOSOBNOST (bash već ume `grep`) — dodaje KONTROLU IZLAZA (cap na 50 hitova, isključeni `.git`/`node_modules`). Sirov `grep -r` na repou pojede kontekst u jednom pozivu.

---

## 7. Arhitekturne odluke i refaktori

### Config preko Pydantic Settings
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str
    max_turns: int = Field(20, ge=1, le=100)
    ...
    @field_validator("azure_openai_endpoint")
    @classmethod
    def check(cls, v): 
        if not v.startswith("https://"): raise ValueError(...)
        return v.rstrip("/")
```

Pravilo: `Settings` sadrži ono što se menja PO OKRUŽENJU (ključevi, timeout). Konstante koje se ne menjaju (Docker image ime) ostaju kao obične konstante u modulu gde se koriste.

### Zašto TOOLS nije Pydantic a SCHEMAS jeste
- `TOOLS` = JSON koji ide IZLAZNO ka API-ju — mora ostati sirov dict/list, tačan oblik koji SDK očekuje
- `SCHEMAS` (`BashArgs`, `SearchArgs`, `StrReplaceArgs`) = validacija ULAZA koji stiže OD modela — tu Pydantic hvata grešku modela i vraća je kao čitljivu poruku umesto da ruši petlju

Pravilo, ponovljeno više puta u sesiji: **validiraj ono što ti NEKO ŠALJE, ne ono što sam gradiš.**

### Agent kao klasa (ne funkcija)
Prelazak opravdan kad se pojavilo STANJE koje treba da preživi poziv (`messages`, `usage`, `max_turns`):
```python
class Agent:
    def __init__(self, sandbox, provider=provider, tools=None, system_prompt=None, max_turns=None):
        self.sandbox = sandbox
        self.active_tools, self.active_schemas = get_active_tools(tools)
        self.usage = Usage()
        self.messages = [{"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT}]

    def run(self, task):
        self.messages.append({"role": "user", "content": task})
        for _ in range(self.max_turns):
            result = self.provider.complete(self.messages, self.active_tools)
            self.usage.prompt += result.usage[0]
            self.usage.completion += result.usage[1]
            self.usage.calls += 1
            self.messages.append(result.raw_message)
            if not result.tool_calls:
                return result.content
            for call in result.tool_calls:
                out = self._dispatch(call)
                self.messages.append({"role": "tool", "tool_call_id": call.id,
                                       "content": str(out) if out is not None else "(no output)"})
        return "Maximum number of steps reached"
```

### Provider apstrakcija (za multi-model podršku)
```python
@dataclass
class ToolCall:
    id: str; name: str; arguments: str

@dataclass
class CompletionResult:
    content: str | None
    tool_calls: list[ToolCall]
    usage: tuple[int, int]
    raw_message: object = None   # čuva sirov SDK objekat za istoriju
```
`ToolCall`/`CompletionResult` žive u `providers/base.py` (transportni format, provider-agnostic) — RAZLIČITO od `SCHEMAS` u `tools.py` (domenski format, specifičan za alate). `Agent` zna samo za `CompletionResult`, nikad za OpenAI/Anthropic specifičan oblik.

**Bag nađen i ispravljen:** `tc.id in tc.function.name` (slučajna zamena zareza sa `in`) pravio tuple `(False, json_string)` umesto `ToolCall(...)` instance → Pydantic validation error.

### Biranje alata po pozivu (za diplomski)
```python
def get_active_tools(enabled=None):
    if enabled is None: return TOOLS, SCHEMAS
    return ([t for t in TOOLS if t["function"]["name"] in enabled],
            {k: v for k, v in SCHEMAS.items() if k in enabled})

agent = Agent(sandbox, tools=["bash", "search"])   # str_replace nedostupan
```

### Cena po modelu
```python
MODEL_PRICING = {
    "gpt-5.6-sol": (5.00, 30.00), "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-luna": (0.20, 1.20), "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5-nano": (0.05, 0.40),
}
# fallback: eksplicitna greška, NE (0,0) — tiha nula bi sakrila propust u tabeli
@computed_field
@property
def cost(self) -> float:
    if self.model not in MODEL_PRICING:
        raise ValueError(f"No pricing entry for {self.model!r}")
    price_in, price_out = MODEL_PRICING[self.model]
    return (self.prompt * price_in + self.completion * price_out) / 1_000_000
```

---

## 8. Rich UI (terminal stilizacija)

Prelazak sa golog `print` na `rich.Console` + `Panel`/`Markdown` — bez menjanja arhitekture petlje:
```python
console.print(Panel(args.command, title="bash", border_style="cyan", title_align="left"))
console.print(Markdown(answer))
```

**Bag:** multi-line paste u `input()` tretiran red-po-red kao odvojeni promptovi (agent je "odgovarao" na svaku liniju traceback-a posebno, 25 poziva/$0.0077 potrošeno na traženje da se nalepi ostatak greške). Rešeno sa `select.select([sys.stdin], [], [], 0.05)` koje čita SVE redove koji su već u baferu (paste stiže odjednom), umesto samo prve linije.

**Vizuelni dupli prikaz:** `Panel` oko unosa korisnika duplirao terminalski eho. Rešeno uklanjanjem `Panel`-a oko unosa, zamenjeno sa `console.rule()` kao separator.

Poređenje UI pristupa: `rich` (scrollback radi prirodno, brzo za implementaciju) vs `textual` (fiksni paneli, pravi TUI, teži refaktor) vs Claude Code stvarni pristup (Ink/React za terminal, Node-only, nema Python ekvivalenta 1:1). Odluka: `rich` + `Live` je najbliže Claude Code osećaju uz najmanje truda.

---

## 9. Git / GitHub

- `.gitignore` ne važi retroaktivno na već praćene fajlove → `git rm -r --cached workspace eval_ws runs.jsonl`
- **`.env` procureo u prvi commit** → GitHub Push Protection blokirao push → ključ rotiran u Azure portalu ODMAH → istorija resetovana (`git reset --soft` + `git rm -r --cached .` + novi commit, pošto je bio samo jedan commit u repou)
- README podeljen na dva fajla: `README.md` (minimalan — setup i run) i `docs/NOTES.md` (opširan — arhitektura, odluke, naučene lekcije, brojevi)
- Video na GitHub-u: mora se upload-ovati kroz Issue/PR editor (drag & drop u tekst polje) da bi dobio `/assets/.../uuid` URL koji GitHub renderuje kao klikabilan plejer — fajl commit-ovan direktno u `docs/` NE dobija taj tretman.

---

## 10. OpenAI/Anthropic pricing (istraženo uživo)

Za `MODEL_PRICING` mapu, pretraženi zvanični podaci (avgust 2026):
- `gpt-5.6-sol`: $5.00 / $30.00 po milionu tokena
- `gpt-5.6-terra`: $2.00 / $12.00
- `gpt-5.6-luna`: $0.20 / $1.20
- `gpt-5.4-nano`: $0.20 / $1.25 (potvrđeno sa dva nezavisna izvora)
- `gpt-5-nano`: $0.05 / $0.40

Napomena: ovo su OpenAI direktne cene, Azure deployment cene mogu odstupati — treba proveriti u Azure portalu za tačnu cifru za rad.

Claude Max/Pro pretplata NIJE povezana sa API pristupom — to su odvojeni proizvodi po Anthropic pravilima; pokušaji zaobilaska (OAuth token extraction) su eksplicitno blokirani od strane Anthropic-a (januar 2026).

---

## 11. Diplomski rad — plan eksperimenta

**Teza:** izolovan uticaj harness dizajna (ne modela) na trošak i pouzdanost agenta.

**Predložena struktura:**
1. Arhitektura harness-a (petlja, sandbox, alati)
2. Eval metodologija + held-out set (zadaci koje harness nikad ne vidi tokom razvoja — sprečava overfitting na sopstvene evale)
3. Eksperimenti: bez/sa `str_replace`, model A/B/C poređenje, tool-ablation matrica
4. Bezbednosna analiza sandboxa

**Merene kolone (bez izmišljanja nemerenih stvari):**
- Identifikacija: `model`, `session_id`, `task`, `run_index`
- Tool-varijanta: `uses_bash`, `uses_search`, `uses_str_replace` (bool dummy kolone)
- Ishod: `ok`, `crashed`, `error_type` (razdvaja "harness pukao" od "model pogrešio")
- Trošak: `prompt_tokens`, `completion_tokens`, `total_tokens`, `calls`, `cost`
- Vreme: `wall_time` (perf_counter, ne time.time — monotono, ne kvari se pri promeni sistemskog sata)

Izostavljeno namerno (nije implementirano, ne izmišljati): `llm_seconds`/`tool_seconds` po pozivu, TTFT/TTLT iz `latency_checkpoint`, per-tool timing breakdown.

`session_id` format: `f"{model}__{'-'.join(sorted(tools))}"` — grupisanje po (model, tool-kombinacija) za tabelu u radu.

---

## 12. Prvi pravi eval run (48 poziva, 4 varijante × 12 zadataka)

Rezultati (gpt-5.4-nano, repeats=1):

| Varijanta | Pass | Fail | Crash | Tokeni | Cena | Vreme (s) |
|---|---|---|---|---|---|---|
| bash | 12/12 | 0 | 0 | 30,302 | $0.0093 | 73.2 |
| bash+search | 12/12 | 0 | 0 | 40,150 | $0.0114 | 81.1 |
| bash+str_replace | 11/12 | 1 | 0 | 26,850 | $0.0079 | 59.9 |
| bash+search+str_replace | 10/12 | 1 | 1 | 34,515 | $0.0097 | 70.5 |

**Nalazi:**
1. `str_replace` je najjeftinija varijanta kad radi čisto, ali uvodi nov failure mode (model "odustane" umesto da padne nazad na rewrite)
2. Dodavanje `search` NIJE smanjilo trošak — najskuplja varijanta, vučena jednim patološkim run-om (`pytest`, 12,566 tokena — model probao PET različitih `perl` regex pokušaja pre nego što je prešao na Python rewrite)
3. Jedini crash je bio infrastrukturni (`UnicodeDecodeError` u `sandbox.py` zbog non-UTF-8 bajta u izlazu komande), ne model — popravka: `errors="replace"` u `subprocess.run` decode koraku
4. n=1 po varijanti — potrebno 3+ ponavljanja pre nego što ovo uđe u rad kao nalaz (potvrđena varijansa 8/7/8 na ranijem identičnom eval setu)

**Ponovljeni obrazac kroz sesiju:** model dvaput pokušao `apply_patch` (alat iz drugog harness-a, ne postoji ovde) → uvek `command not found` → model se sam oporavio i pao nazad na Python heredoc, bez intervencije.

---

## Generisani artefakti tokom sesije

- `README.md` — minimalan setup/run vodič
- `docs/NOTES.md` — opširan izveštaj o arhitekturi i naučenim lekcijama
- `eval_report.pdf` — vizuelni PDF izveštaj (4 strane, terminal-stilizovan dizajn)
- `eval_report.md` — čitljiv markdown izveštaj istih podataka
- `scripts/run_evals.py` — orkestracija: model × tool-varijante × zadaci × ponavljanja → `runs_eval_<timestamp>.{json,csv}` u `artifacts/`