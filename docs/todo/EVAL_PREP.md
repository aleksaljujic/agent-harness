# Plan pripreme za veću SWE-bench evaluaciju (50+ instanci)

> **Zastarelo za agent-run fazu.** Pisano pre `batch_300` i pre popravki od
> 2026-09-14/15 (neutralan prompt, `invalid_prompt` retry, Unicode fix, resume,
> brisanje `work/` checkout-a). Aktuelna pre-registracija i runbook su u
> [../swebench/EXPERIMENT_LOCK.md](../swebench/EXPERIMENT_LOCK.md).
> Deo o **gradingu u talasima** (tačke 2 i 4 niže) i dalje važi — grading još nije
> rađen za `batch_300`.

Kontekst: dosad su rađeni samo pojedinačni smoke-testovi (1 instanca po run-u).
Sledeći korak je run preko više instanci (npr. 50, pa eventualno svih 300 iz
SWE-bench Lite). Ovaj fajl je plan pripreme, ne izveštaj o gotovom radu — vidi
[ISSUES.md](ISSUES.md) za već rešene/otvorene bugove koje ovaj plan uzima u
obzir.

---

## 1. Odluka: koji toolset kombo

Bez eksplicitnog `--combo`, `run_swebench.py` generiše **sve kombinacije
alata** koje sadrže `bash` (`all_tool_combinations`, `evals/pipeline.py:16`) —
`TOOL_UNIVERSE` ima 5 alata (`bash, search, str_replace, read_file,
find_file`), pa je to **16 kombinacija po instanci**. Za 50 instanci bez
`--combo` to je 800 run-ova, ne 50.

**Odluka:** koristiti eksplicitno `--combo bash` (ili konkretnu listu, npr.
`--combo bash,search,str_replace`) dok ne odlučimo da nam treba puna
ablacija. Puna ablacija (16 kombinacija × N instanci) čuvati za kad je
harness stabilan i disk/vreme budžet jasan.

## 2. Disk provera pre grading faze

Trenutno stanje (proverено `docker system df -v`): **31GB slobodno** na `/`.
Svaki *nov* eval image (po instanci, ne po repo-u) nosi ~2-4GB unikatnog
sloja + ~2.2GB deljenog. Za 50 novih instanci to je grubo **100-200GB** —
prelazi raspoloživi prostor.

Plan:
- Ne grade-ovati svih 50 odjednom bez nadzora nad diskom.
- Grade-ovati u talasima (npr. po 10), sa `docker system prune -a` (ili
  ciljano `docker rmi` starijih eval image-a koji više nisu potrebni) između
  talasa.
- Alternativa: prebaciti grading fazu na drugi laptop sa više prostora (vidi
  #5 ispod) i ovde raditi samo `--no-grade`.
- Vezano za [ISSUES.md #6/#7](ISSUES.md) (cold-pull timeout, pre-warm
  odluka) — ako ostane neurađeno, svaki nov repo/instanca u ovom batch-u
  može dodatno usporiti prvi susret sa tim repo-om.

## 3. Faza 1 — jeftin `--no-grade` run nad N instanci

Bez gradinga nema Docker image rizika, samo agent + API troškovi. Ovo je
sledeći konkretan korak:

```bash
.venv/bin/python scripts/run_swebench.py \
  --limit 50 \
  --combo bash \
  --no-grade \
  --name batch_50
```

Procena (na osnovu post-fix smoke-test uzoraka, prosek ~32s/run, ~$0.0154/
run, sekvencijalno — agent-run petlja nije paralelizovana,
`evals/swebench/pipeline.py:275`):
- **Vreme:** ~25-30 min (okvir 20-45 min, zavisno od težine instanci —
  poznato da str_replace-loop pre fixa dizao prosek na 227s/run, sad bi
  trebalo da bude redak slučaj)
- **Cena:** ~$0.75-$1

Ishod ove faze: `predictions/*.jsonl` za svih 50, plus `error_message`/
`errors/*.json` za sve koje padnu (očekuj poneki `invalid_prompt`, vidi
[ISSUES.md #2](ISSUES.md)).

## 4. Faza 2 — grading u talasima

Posle faze 1, grade-ovati postojeće predikcije (ne pokreće agenta ponovo,
nema dodatnih API troškova) — u manjim grupama radi kontrole diska. Trenutno
nema `--grade-only <predictions.jsonl>` ulazne tačke u `run_swebench.py`
(pomenuto u planu iz plan-mode-a kao posebna, još neurađena stavka) —
grading je dostupan samo kroz pun `run_pipeline()`. Ako se ovaj plan
sprovodi, vredi prvo dodati `--grade-only` da bi se faza 2 mogla ponavljati
bez ponovnog trošenja API poziva ili čekanja agent-run petlje.

Prati [ISSUES.md #8](ISSUES.md) tokom ovoga — evaluator je već jednom
lažno prijavio "Image not found" za image koji je stvarno postojao lokalno i
zaglavio se bez greške; ako se ponovi u talasima, ubiti proces i probati
ponovo pre nego što se pretpostavi da je image stvarno nedostupan.

## 5. Opcija: split rada preko dva laptopa

Ideja: agent-run (jeftin, bez diskovnog rizika) ovde; grading (diskovno
skup) na drugom laptopu sa više prostora.

Za ovo je dovoljno preneti `predictions/*.jsonl` iz `artifacts/swebench/
experiments/<exp>/predictions/` na drugi laptop i tamo pokrenuti grading
nad njima (opet čeka na `--grade-only` ulaznu tačku iz koraka 4, ili ručni
poziv `swebench.harness.run_evaluation` sa istim `predictions_path`).
Ne treba prenositi git mirror keš (`~/.cache/agent-harness/repos/`) — to je
samo za agentov sandbox, grading kontejner ima svoj repo checkout zapečen u
Docker image-u (vidi objašnjenje u ISSUES.md diskusiji o astropy-12907
rezultatu — grading ne dira host-side git keš uopšte).

## 6. Otvoreno / odluke koje treba doneti pre pokretanja

- [ ] Da li raditi `--grade-only` CLI opciju pre faze 2, ili prihvatiti
      ponovno pokretanje pune `run_pipeline()` (agent bi se preskočio jer
      predictions već postoje? — **proveriti**: trenutno `run_one()` uvek
      pokreće agenta, nema cache-by-predictions logike, pa bez
      `--grade-only` bi puni re-run **ponovo platio API pozive**).
- [ ] Konačan broj instanci za prvi veći batch — 50 kao probni krug, ili
      manje (npr. 20) da se prvo potvrdi da faza 2 (grading talasi + disk
      prune) radi glatko pre nego što se ide na 50+.
- [ ] Da li čekati na [ISSUES.md #6/#7](ISSUES.md) (pre-pull/pre-warm eval
      image-a) pre ovog batch-a, ili ići sad i tolerisati poneki spor prvi
      susret sa novim repo-om.
