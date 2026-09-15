# Препоруке за експериментални протокол (SWE-bench toolset аблација)

> Review донет као reviewer-ски пролаз кроз код (не само провера да ли pipeline
> ради) — фокус на то да ли експеримент заиста мери оно што мисли да мери, пре
> него што се потроши озбиљан новац на велики run.

## Моја оцена укратко

- **Инжењерски:** врло добро постављено.
- **За дипломски:** више него довољно озбиљно.
- **За будући paper:** потенцијално јако добро, али бих закључао experimental
  protocol пре великог run-а.

Највећа опасност тренутно није Docker, SWE-bench или telemetry. То је углавном
добро решено.

**Највећи ризик је да експеримент нехотице не измери нешто друго од онога што
мислиш да мериш.**

---

## 1. 🟥 Најважније: `str_replace` је тренутно експлицитно фаворизован prompt-ом

У `prompt.py` постоји:

```
When modifying an existing file you MUST use str_replace (if available)
```

и:

```
one call per change; do not rewrite whole files with cat.
```

Ово је стварно битно.

Ако је хипотеза:

> **H₁:** Додавање `str_replace` алата побољшава ефикасност агента.

онда тренутни експеримент није чисто:

> tool available vs. tool unavailable

него:

> tool available **+ agent instructed to use it** vs. tool unavailable.

То може бити потпуно легитиман експеримент, али мора да се назове правим
именом.

**Предлог за главни експеримент:**

Исти prompt за све услове:

> „Investigate the codebase with your tools, locate the cause, then make the
> smallest change to the source that resolves the issue.“

И ништа:

> `MUST use str_replace`

А онда само tool availability варира.

Још боље: ако је `str_replace` доступан, бележи се:

```
str_replace_available = true
str_replace_used = true/false
```

Онда се добијају две интересантне анализе:

- **intent-to-treat:** шта се деси када агенту дамо tool;
- **usage analysis:** шта се деси када га агент заиста користи.

Ово би стварно требало променити пре главног експеримента.

> **Урађено.** `evals/swebench/prompt.py` више не помиње `str_replace` — цела
> реченица је уклоњена, заједно са остатком `"one call per change; do not
> rewrite whole files with cat"`, који је сам по себи и даље био pristrasan
> (обесхрабрује баш bash-only путању, једину доступну у baseline услову) и уз то
> граматички одсечен. Prompt је сад идентичан за сва четири toolset услова, а у
> фајлу стоји коментар зашто, да се не врати "поправком". Остаје отворено оно
> што тражи нове колоне: `str_replace_available` / `str_replace_used` за
> раздвајање intent-to-treat од usage анализе (тачка 12).

---

## 2. 🟥 Много озбиљнији проблем ако се користи `repeats > 1`

Ово се примети тек кад се `pipeline.py` и `grade.py` погледају заједно.

У `pipeline.py` се праве више run-ова:

```
instance_id + run_index
```

што је супер. Али `Prediction` садржи само:

```
instance_id
model_name_or_path
model_patch
```

а `grade()` резултате враћа као:

```
dict[instance_id, dict]
```

То значи да ако постоје:

```
instance_123 / run 0
instance_123 / run 1
instance_123 / run 2
```

grader их концептуално види као исти `instance_id`.

А онда у pipeline-у:

```
r = results.get(row.instance_id)
```

и исти grade може бити backfill-ован у више run-ова.

- Ако `repeats=1` — нема проблема.
- Ако `repeats>1` — ово би требало решити пре било какве озбиљне статистике.

Јер циљ је:

```
instance 42, run 0 → resolved=True
instance 42, run 1 → resolved=False
```

а тренутна структура grader-а природно очекује један verdict по
`instance_id`.

**То је најважнија ствар коју треба проверити пре него што се пусте
репликације.**

> **Ажурирано после провере кода (види [ISSUES.md #9](todo/ISSUES.md)):** механизам
> је потврђен и гори је него што делује на први поглед. Проблем није само у
> нашем `pipeline.py` — сам званични `swebench` пакет учитава
> `predictions.jsonl` и ради `{pred["instance_id"]: pred for pred in
> predictions}` (`swebench/harness/run_evaluation.py:743`). Dict comprehension
> над листом са дуплираним кључевима задржава само **последњи** ред по
> `instance_id` — значи да се patch-еви run-ова 0 и 1 (при `repeats=3`)
> **никад стварно не евалуирају**, не само да добију исти verdict. Наш
> `pipeline.py:316` (`results.get(row.instance_id)`) онда тај један verdict
> backfill-ује на сва три реда.
>
> Тренутно нема ризика — сваки run до сада користио је default `repeats=1`
> (`evals/swebench/config.py:31`), где колизије нема. **Препорука: остати на
> `repeats=1` за предстојећи 50-instance batch**, а прави fix (одвојен
> `run_evaluation` позив по `run_index`-у, спајање по `(instance_id,
> run_index)`) урадити тек кад заиста затреба pass@k.

---

## 3. 🟡 Sandbox/provisioning изгледа добро

У `provision.py`:

- cache-ован mirror репозиторијума;
- checkout тачно на `base_commit`;
- уклања се `.git`;
- прави се нови git repo;
- прави се један base commit;
- уклања се remote.

То је баш добар потез за експеримент јер смањује могућност да агент дође до
upstream history-а или solution commit-а.

А `predict.py` онда узима стварни diff радног tree-а према том base commit-у.

Ово би требало оставити како јесте.

---

## 4. 🟢 Званични SWE-bench grader је велики плус

Ово је једна од најбољих ствари у setup-у.

Не каже се:

> „Ако се agent заврши без exception-а, успешан је.“

него се стварно покреће:

```
python -m swebench.harness.run_evaluation
```

и извлачи се:

- `resolved`
- `FAIL_TO_PASS`
- `PASS_TO_PASS`

Ово јако појачава методологију.

Посебно је добро што се чувају:

- `tests_fail_to_pass_total`
- `tests_fail_to_pass_passed`
- `tests_pass_to_pass_total`
- `tests_pass_to_pass_passed`

јер онда може да се каже не само да ли је task решен, него и шта се десило са
тестовима.

---

## 5. 🟢 Telemetry је стварно добра

По run-у већ постоји:

- prompt tokens
- completion tokens
- reasoning tokens
- cost
- wall time
- LLM time
- tool time
- calls
- tool breakdown
- tool errors
- turns
- termination reason
- patch size
- empty patch
- crash/error info

То значи да може да се одговори на много интересантније питање од:

> „Који agent је имао највећи accuracy?“

него:

> „Како различити toolsets мењају computational trajectory агента?“

То је права научна вредност овог benchmark-а.

---

## 6. 🟡 Cost не треба да буде једини efficiency metric

За главни резултат:

**Primary**
- Resolved rate
- Cost per resolved task

Ово друго је посебно битно. Не:

```
average cost / run
```

него:

```
total cost / number of resolved tasks
```

Јер ако један toolset кошта $0.05 по task-у и решава 20%, а други $0.08 и
решава 60%, први није нужно „ефикаснији“.

**Secondary**
- cost/run
- prompt tokens
- reasoning tokens
- completion tokens
- turns
- tool calls
- wall time

**Diagnostic**
- empty patch
- crash
- tool errors
- termination reason
- F2P/P2P
- patch size

Све ово се већ мери. Само треба унапред дефинисати улоге метрика, да после
не се лове „занимљиви“ p-value-ови по 30 колона.

---

## 7. 🟢 Четири harness-а су сасвим добра идеја

Ако је главни експеримент:

| Condition | Bash | Find/Read/Search | String replace |
|---|---|---|---|
| A | ✓ | – | – |
| B | ✓ | – | ✓ |
| C | ✓ | ✓ | – |
| D | ✓ | ✓ | ✓ |

онда може да се раздвоји:

**Ефекат str_replace**
- A → B
- C → D

**Ефекат search/read/find toolset-а**
- A → C
- B → D

То је много јаче од једног закључка „D је најбољи“, јер онда постоји
incremental contribution сваке групе алата.

---

## 8. 🟢 Model × reasoning даје још једну лепу димензију

Ако се стварно ради:

```
2 модела × 2 reasoning режима × 4 toolset-а = 16 услова
```

исти benchmark instance може да буде блок кроз свих 16.

То је одлично за анализу — само треба избећи да се каже „имамо 16 независних
експеримената“, него говорити о **factorial experimental design** са
факторима:

- model
- reasoning effort
- toolset

и interaction-има ако има довољно података.

Може да се добије нешто занимљиво, нпр:

> str_replace помаже Nano-у, али скоро ништа не мења код Mini-ја.

То је много интересантнији резултат него само „str_replace је добар“.

> **Одлука за `batch_300` (види [EXPERIMENT_LOCK.md](swebench/EXPERIMENT_LOCK.md)):**
> главни експеримент вара **само toolset** — `gpt-5.4-nano`, `temperature 0`,
> reasoning искључен, 300 инстанци × 4 услова. Последица коју треба признати
> отворено: **H2 овим дизајном није тестирана** и мора или да изађе из рада или да
> се премести у „даљи рад“. H1 и H3 јесу (H3 кроз пресеке по репоу, величини
> patch-а, броју F2P тестова).
>
> **Како то бранити — дизајнерски, не буџетски.** Цео batch кошта ~$30, па
> „нисам имао ресурсе“ позива на питање „па зашто онда не и други модел?“.
> Јача формулација:
>
> > Модел је контролисана променљива, фиксирана намерно. Предмет рада је утицај
> > harness-а и tool surface-а, не поређење модела — увођење другог модела додаје
> > фактор који није истраживачко питање и троши статистичку снагу на интеракцију
> > уместо на главни ефекат.
>
> Уз то иде поштено наведена граница генерализације: резултат важи за
> `gpt-5.4-nano`, а пошто је то мали модел, могуће је да је корист од алата **већа**
> него што би била код јачег — слаб модел има више користи од скеле. Боље то сам
> написати него чекати да буде постављено као питање.
>
> **Јефтина делимична надокнада, ако се нађе времена:** други модел на
> **подскупу** — 50 инстанци × 4 услова = 200 run-ова, ~$13 и ~7 h са `mini`
> (`--sample 50 --seed 42`). Није пун факторски дизајн, али претвара „H2 није
> тестирана“ у „прелиминарни налаз о H2 на подскупу“.

---

## 9. 🟡 50–100 instance-а је прихватљиво за дипломски

Не треба 300 — нема потребе.

Са ограниченим буџетом, боље:

> 50 добро одабраних instances × 16 conditions

него:

> 100 instances × лошији/неуједначени дизајн.

То је 800 run-ова за 50 instances, што већ није мало. И ако после pilot-а
variance испадне огроман, може да се прошири.

---

## 10. 🟥 Али не треба бирати 50 instances „јер су првих 50“

Ово треба озбиљно размислити. Ако је могуће, унапред дефинисати sampling
strategy — нпр:

- различити репозиторијуми;
- различите тежине;
- различити типови bugfix-а;
- различите величине patch-а;
- различити бројеви F2P тестова.

Не мора да буде савршен stratified sample, али мора да може да се каже:

> „Instances су изабране пре експеримента по овом критеријуму.“

То штити од selection bias-а.

---

## 11. 🟢 Чување `harness_sha` је баш добра ствар

Мала ствар, али научно веома добра. У сваком run-у се чува commit SHA, а и
manifest га бележи. То значи да ако се за два месеца промени `prompt.py` или
`tools.py`, може да се зна којом верзијом је run добијен.

Ово не треба дирати. Вредело би додати и versioning за:

- model identifier;
- evaluation package/version;
- prompt version/hash;
- configuration hash.

Али SHA је већ одличан почетак.

---

## 12. Једна ствар коју би требало додати: `tool_usage`

Већ постоји `tool_calls_breakdown`, што је супер. Али за главну хипотезу
требало би експлицитно извести:

```
str_replace_available
str_replace_used
str_replace_calls
str_replace_successes
str_replace_errors
```

и исто за остале tools.

Онда може да се направи један баш леп резултат:

> Among runs where str_replace was available, agents invoked it in X% of
> tasks; when invoked, median tool calls were Y and median cost was Z.

И може да се види да ли је алат стварно коришћен или само постојао у tool
schema-у.

---

## 13. Шта би требало да буде главна хипотеза

Не:

> „String replace је оптималан.“

То је превише јако и тешко је бранити.

Него нешто као:

> **H1:** Providing a specialized deterministic text-replacement tool reduces
> the inference and interaction cost of software-engineering agents while
> maintaining or improving task resolution performance compared with
> shell-only tooling.

И secondary:

> **H2:** The benefit of specialized text-editing tools varies across model
> capability and reasoning configuration.

И чак:

> **H3:** The benefit of specialized tools is task-dependent and is greater
> for tasks requiring localized source-code modifications.

H3 је посебно занимљива.

---

## 14. Шта би reviewer напао на одбрани

Ако би се глумио строг професор:

**„Како знаш да је benefit од str_replace, а не од prompt-а?“**
→ Зато треба решити оно са `MUST use` (тачка 1).

**„Како знаш да резултат није специфичан за SWE-bench Lite?“**
→ Не зна се. И не треба да се тврди да јесте. Каже се да важи у оквиру
benchmark-а.

**„Зашто баш 50 instances?“**
→ Предефинисани sampling + budget constraint + paired design.

**„Зашто баш ова 4 toolset-а?“**
→ Они представљају baseline и incremental addition-е.

**„Зашто само један модел? Зар резултат није специфичан за њега?“**
→ Модел је намерно контролисана променљива — предмет рада је tool surface, не
поређење модела. Јесте ограничење генерализације и наведено је као такво: важи за
`gpt-5.4-nano`, и пошто је мали модел, корист од алата је вероватно горња, не доња
граница. Не тврдити више од тога. (Види проширење уз тачку 8.)

**„Зашто ти је cost важнији од accuracy?“**
→ Није. Resolution је primary; cost per resolved је efficiency metric.

**„Шта ако је разлика статистички значајна, али мала?“**
→ Извештавају се effect size и CI, не само p-value.

**„Шта ако string_replace смањи cost, али смањи и resolution?“**
→ Онда је trade-off, а не победа.

И то је добар научни одговор.

---

## Коначна препорука пре великог run-а

Пре него што се потроши и један долар више, направити мали **„experiment
lock“** документ од једне странице:

```
Research question
H1 / H2 / H3

Dataset
Sampling strategy
N instances

Factors
- toolset: 4 levels
- model: 2 levels
- reasoning: 2 levels

Primary outcomes
- resolved
- cost per resolved

Secondary outcomes
- tokens
- reasoning tokens
- turns
- calls
- wall time

Statistical analysis
- paired/block design
- binary outcome test/model
- cost: median + CI
- effect sizes
- multiple-comparison correction

Exclusion rules
- API failure
- infrastructure failure
- evaluator failure

Prompt
[exact frozen version]

Code
[harness SHA]
```

И онда се не мења protocol кад се виде први резултати.

Ово је последњи велики корак који недостаје да ово пређе из „веома доброг
дипломског engineering пројекта“ у озбиљан експеримент који касније може да
се претвори у paper.

**Приоритет пре главне евалуације:** тачка 2 (repeats/grading issue) и тачка
1 (`MUST use str_replace`) — обе су много лакше за исправку сада него када
већ постоји 1.000 скупих run-ова.
