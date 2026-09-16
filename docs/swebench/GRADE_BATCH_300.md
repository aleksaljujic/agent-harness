# Ocenjivanje `batch_300` na drugom računaru (Windows, preko AnyDesk-a)

Uputstvo za ocenjivanje već završenog eksperimenta
`20260915_120759_batch_300` na jačoj Windows mašini (64 GB RAM, i5-14600K,
2 TB NVMe), kojom se upravlja preko AnyDesk-a.
Radi se samo ocenjivanje: agent se **ne** pokreće ponovo i nema API troška.

- 300 instanci × 4 toolset-a = 1200 predikcija, sve već u `predictions/`
- `--resume` preskače svih 1200 run-ova i samo pokreće evaluator, pa rezultate
  upiše nazad u `rows.jsonl` / `rows.csv` / `manifest.json`. Provereno lokalno:
  sa istim flag-ovima i `--no-grade` prepoznato je svih 1200 run-ova, bez ijednog
  novog.

**Procena:** ~4–6 h ukupno. Skidanje ~100 GB image-a zavisi od interneta, a
grading sa 8 worker-a traje ~2 h. Na disku treba **~200–270 GB** slobodno.

Sve komande osim onih označenih sa **PowerShell** kucaju se u **WSL Ubuntu**
terminalu. Evaluator (`swebench`) ne podržava Windows direktno.

---

## 0. Priprema Windows-a (jednom)

### 0.1 WSL2 + Ubuntu

Preduslov: virtualizacija mora biti uključena u BIOS-u (Intel VT-x). Proverava se
u Task Manager → Performance → CPU, gde treba da piše „Virtualization: Enabled“.
Ako piše Disabled, `wsl --install` i Docker neće raditi.

**PowerShell (kao Administrator):**

```powershell
wsl --install -d Ubuntu
```

Restart računara. AnyDesk se posle restarta sam vraća samo ako je podešen
*Unattended Access* (lozinka). Inače neko mora da prihvati konekciju.
Posle restarta otvoriti „Ubuntu“ iz Start menija i napraviti korisnika.

### 0.2 Docker Desktop

1. Instalirati [Docker Desktop](https://www.docker.com/products/docker-desktop/),
   sa uključenim „Use WSL 2 based engine“.
2. Settings → Resources → **WSL integration** → uključiti za `Ubuntu`.
3. Settings → Resources → Advanced:
   - **Disk image location**: particija sa 300+ GB slobodnog prostora (Docker
     sve image-e drži u jednom `.vhdx` fajlu tamo).
   - **Virtual disk limit**: bar 350 GB.
4. Provera u Ubuntu terminalu: `docker run --rm hello-world`.

WSL2 po defaultu dobija pola RAM-a (32 GB), što je dovoljno za 8 worker-a i ne
treba ga menjati.

### 0.3 Da se ne ugasi usred rada

Grading traje satima, a AnyDesk sesija ne mora ostati otvorena. Računar i
Docker Desktop moraju ostati upaljeni:

- Windows Settings → System → Power → **Sleep: Never** (i za ekran je svejedno).
- Windows Update → **Pause updates** (npr. 1 nedelja), da ne restartuje noću.
- Docker Desktop ne gasiti. Zatvaranje prozora je ok, ali „Quit“ nije.

## 1. Setup repoa (u Ubuntu terminalu)

```bash
sudo apt update && sudo apt install -y git tmux
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

cd ~                                   # Linux home, NE /mnt/c/... (višestruko sporije)
git clone https://github.com/aleksaljujic/agent-harness.git
cd agent-harness
git checkout feature/swe-benchmark
uv sync --group swebench               # bez --group swebench grading tiho ne radi ništa
```

`.env`: API se ne poziva, ali `Settings` traži sva polja, pa su lažne vrednosti
dovoljne (pravi ključ **ne** treba kopirati):

```bash
cat > .env <<'EOF'
ENDPOINT=https://unused.example
API_KEY=unused
MODEL=gpt-5.4-nano
PROVIDER=openai
EOF
```

`agent-sandbox` image **nije** potreban, jer se agent ne pokreće.

## 2. Prebaciti eksperiment (~95 MB)

`artifacts/` je u `.gitignore`, pa folder treba preneti ručno.

Na laptopu napraviti arhivu:

```bash
tar czf batch_300.tgz -C artifacts/swebench/experiments 20260915_120759_batch_300
```

Preneti `batch_300.tgz` preko AnyDesk-a (dugme **File Transfer** u traci, ili
copy-paste fajla kroz sesiju), npr. u `C:\Users\<korisnik>\Downloads`.

U Ubuntu terminalu na drugom računaru:

```bash
cd ~/agent-harness
mkdir -p artifacts/swebench/experiments
tar xzf /mnt/c/Users/<korisnik>/Downloads/batch_300.tgz -C artifacts/swebench/experiments
ls artifacts/swebench/experiments/20260915_120759_batch_300/predictions   # 4 .jsonl fajla
```

## 3. Unapred skinuti eval image-e

**Obavezno.** Evaluator odustaje od pull-a posle 10 minuta i instanca tada dobije
lažni `0/0` (ISSUES.md #6). Kad su image-i već lokalno, evaluator ih samo koristi.

Pre toga proveriti slobodan prostor na particiji iz koraka 0.2 (Windows
Explorer → This PC). `df` u WSL-u ne pokazuje prostor koji Docker Desktop
stvarno ima.

```bash
cd ~/agent-harness
docker login        # besplatan Docker Hub nalog: 300 pull-ova probija limit za anonimne

E=artifacts/swebench/experiments/20260915_120759_batch_300
python3 -c "
import json
for l in open('$E/predictions/gpt-5.4-nano__bash.jsonl'):
    i = json.loads(l)['instance_id'].replace('__', '_1776_').lower()
    print(f'swebench/sweb.eval.x86_64.{i}:latest')
" > images.txt
wc -l images.txt                                   # 300

tmux new -s pull
xargs -P 4 -n 1 docker pull < images.txt 2>&1 | tee pull.log
```

Provera da je svih 300 tu. Ako fali neki, ponoviti isti `xargs`: već skinuti se
preskaču za par sekundi.

```bash
while read img; do docker image inspect "$img" >/dev/null 2>&1 || echo "FALI $img"; done < images.txt
```

Kad ništa ne fali, zatvoriti `pull` sesiju komandom `exit`, da se sledeći `tmux`
ne otvori unutar nje.

## 4. Grading

Pokrenuti u `tmux`-u. Tako proces nastavlja i ako se zatvori Ubuntu prozor ili
AnyDesk sesija.

```bash
cd ~/agent-harness
tmux new -s grade

uv run scripts/run_swebench.py \
    --limit 300 \
    --combo bash \
    --combo bash,str_replace \
    --combo bash,find_file,read_file,search \
    --combo bash,find_file,read_file,search,str_replace \
    --max-workers 8 \
    --resume artifacts/swebench/experiments/20260915_120759_batch_300 \
    2>&1 | tee grade.log
```

- `--limit 300` i četiri `--combo` moraju biti **tačno** ovakvi, jer tako
  `--resume` pronalazi postojeće run-ove. Na početku mora pisati
  `resuming 20260915_120759_batch_300: 1200 run(s) already done`. **Ako piše manje
  od 1200, odmah prekinuti (Ctrl+C)**, inače agent kreće da radi nove run-ove.
- Ocenjuje se toolset po toolset (4 poziva evaluatora, po 300 instanci).
- `tmux` detach: `Ctrl+B` pa `D`. Povratak (i posle nove AnyDesk sesije):
  otvoriti Ubuntu terminal, pa `tmux attach -t grade`.
- Ako je RAM tesan (Task Manager → `VmmemWSL` blizu 32 GB), prekinuti i spustiti
  na `--max-workers 4`.

### Praćenje napretka

Izlaz evaluatora se ne ispisuje dok radi. `grade.log` pokaže
`grading gpt-5.4-nano__<toolset> (300 predictions) …` i onda **ćuti** dok taj
toolset ne završi (~30 min). To nije zaglavljeno. Stvaran napredak je broj
gotovih instanci:

```bash
cd ~/agent-harness
E=artifacts/swebench/experiments/20260915_120759_batch_300
for d in $E/grading/*/; do echo "$(find "$d" -name report.json | wc -l)  $(basename "$d")"; done
docker ps --filter name=sweb.eval --format '{{.Names}}' | wc -l      # trenutno aktivnih, ~8
```

Maksimum po toolset-u nije 300, nego broj predikcija sa patch-om:
`bash` 278, `bash-str_replace` 269, `bash-find_file-read_file-search` 262,
`bash-find_file-read_file-search-str_replace` 248. Evaluator instance bez
patch-a uopšte ne pokreće.

### Ako se prekine

Ako se prekine zbog Ctrl+C, restarta, gašenja Docker Desktop-a ili nečeg sličnog,
treba samo pokrenuti **istu komandu ponovo** (posle restarta prvo upaliti Docker
Desktop). Evaluator preskače instance koje već imaju `report.json`
(„N instances already run, skipping...“), pa se gotov posao ne ponavlja.

## 5. Provera rezultata

Pre bilo kakvog zaključka: prazan `grade_error` znači da je evaluator stvarno dao
verdikt. `0/0` bez njega nije rezultat.

```bash
cd ~/agent-harness
python3 - <<'EOF'
import json, collections
rows = [json.loads(l) for l in open("artifacts/swebench/experiments/20260915_120759_batch_300/rows.jsonl")]
by = collections.defaultdict(lambda: [0, 0, 0])
for r in rows:
    s = by[r["session_id"]]
    s[0] += 1; s[1] += bool(r["resolved"]); s[2] += bool(r.get("grade_error"))
for k, (n, res, err) in sorted(by.items()):
    print(f"{k:60s} n={n} resolved={res} grade_error={err}")
errs = collections.Counter(r["grade_error"][:80] for r in rows if r.get("grade_error"))
for e, c in errs.most_common(10):
    print(f"{c:4d}  {e}")
EOF
```

Očekivani `grade_error` su instance bez patch-a, jer ih evaluator preskače i
dobiju `no report: no run_instance.log`. Njih ima tačno **22** (`bash`), **31**
(`bash-str_replace`), **38** (`bash-find_file-read_file-search`) i **52**
(`bash-find_file-read_file-search-str_replace`). Sve preko tih brojeva je
sumnjivo, posebno greške tipa „Image ... not found“ ili „evaluator exited“.
Takve instance treba ponovo pull-ovati i pokrenuti istu komandu iz koraka 4.
Već ocenjene instance se preskaču.

## 6. Vratiti rezultate na laptop

```bash
cd ~/agent-harness
tar czf /mnt/c/Users/<korisnik>/Downloads/batch_300_graded.tgz \
    -C artifacts/swebench/experiments 20260915_120759_batch_300
```

Preneti `batch_300_graded.tgz` nazad preko AnyDesk File Transfer-a. Na laptopu:

```bash
tar xzf batch_300_graded.tgz -C artifacts/swebench/experiments
```

Po želji ručno dodati poslednju liniju iz `artifacts/swebench/MANIFEST.jsonl`
sa drugog računara u lokalni ledger.

## 7. Posle: oslobađanje ~250 GB

`docker rmi` sam po sebi **ne** vraća prostor Windows-u, jer `.vhdx` fajl ne
može sam da se smanji. Najjednostavnije je iz Docker Desktop-a:
Troubleshoot (ikonica bube) → **Clean / Purge data** → WSL 2. To briše
**sve** Docker podatke na tom računaru, pa prvo proveriti da drug nema svoje
image-e/kontejnere koji mu trebaju.

Ako ima, obrisati samo ove image-e i kompaktirati disk:

```bash
xargs docker rmi < images.txt
```

**PowerShell (kao Administrator)**, sa ugašenim Docker Desktop-om:

```powershell
wsl --shutdown
Optimize-VHD -Path "<Disk image location>\docker_data.vhdx" -Mode Full
```

(`Optimize-VHD` traži Hyper-V modul. Bez njega isto radi `diskpart`:
`select vdisk file="...\docker_data.vhdx"`, `attach vdisk readonly`,
`compact vdisk`, `detach vdisk`.)
