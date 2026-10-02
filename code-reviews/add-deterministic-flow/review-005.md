# Review-005 — поставка 05 (срез 3): gate_runner + provenance + m10 + audit

- **Ревьюер:** независимый code-reviewer (review-001–004 — мои; автор поставки — dev, не я)
- **Дата:** 2026-10-02
- **База:** ветка `deterministic-flow`, коммиты `8ec19fe` (gate_runner.py + provenance в flow_transition.py + audit JSONL) и `f49f494` (контракт §7 — долг m10)
- **Диф ревью:** `83c60bf..f49f494` — 5 файлов, +1822/−13 (scripts/gate_runner.py нов., scripts/flow_transition.py +203, tests +911, contracts +11/−2)
- **Метод:** чтение ТЗ/контракта/спеки + 244 тестов + **собственные live-пробы** на клоне реального репо (клон в /tmp, само репо не мутировано; мусор от проб удален, `git status` чист)
- **История ревью:** append-only; пятая запись (review-001…004 не изменялись)

---

## Вердикт: **RETURN**

Ядро поставки сделано добротно и по ТЗ: GateReport со всеми полями, digest-check с STALE, адаптеры-subprocess с cwd/timeout, sidecar-провенанс с DENY на self-review/чужой SHA/change, легаси-compat без ретроактивной криминализации, m10 закрыт корректно, 244 теста green. Но найден **1 blocker**: конфигурационная ошибка обязательного gate (`pm_bounds_check` без явного режима) дает `SKIPPED` и **overall PASS с exit 0** — обязательный gate молча «считается пройденным», что прямо противоречит ТЗ 05 («SKIPPED не считается пройденным»; «отсутствующий gate блокирует переход»). Плюс 3 major и 3 minor.

---

## 1. Таблица замечаний

| № | Место | Серьезность | Замечание и рекомендация |
|---|---|---|---|
| B1 | scripts/gate_runner.py:439–445, 270–273, 356–359; tests/test_gate_runner.py:296–309 | **blocker** | **Обязательный gate с конфигурационной ошибкой не блокирует: SKIPPED → overall PASS, exit 0.** `adapter_pm_bounds` без `--pm-mode` возвращает skip_reason («...запуск без явного режима запрещен (ТЗ 05), ERROR» — текст сам говорит ERROR), но `run_gate` превращает любой `skip_reason` в `SKIPPED`, а `run_gates` считает только ERROR/FAIL — при единственном gate `pm_bounds_check` отчет **overall=PASS, exit 0** (live-проба M1). Это «отсутствующий gate, который не блокирует» — прямой запрет ТЗ 05 и приемки («падающий, отсутствующий и зависший gate блокируют переход с разными кодами»). SKIPPED легален только для pr_validate без PR-контекста (правило неприменимости задано в ТЗ); незаданный режим — ошибка конфигурации запускающего, а не неприменимость gate. Тест автора (`test_pm_bounds_requires_explicit_mode`) маскирует дефект: он вручную ставит `report["overall"] = STATUS_FAIL` и проверяет exit 1 — т.е. автор знал, что SKIPPED не блокирует, и «починил» это в тесте, а не в коде; сама строка `overall` в тесте — свидетельство расхождения кода с комментарием. → В `run_gates`: SKIPPED разрешен только по явному правилу неприменимости (признак от адаптера, например кортеж `(skip_reason, applicable_by_rule: bool)`); конфигурационные ошибки → ERROR. Минимум — SKIPPED-гейты в pre_accept/pre_merge/ci должны делать overall ≥ FAIL (не PASS) и exit ≥ 1. Негативный тест: «run --scope pre_accept без --pm-mode → exit ≥ 1, overall ≠ PASS». |
| M1 | scripts/flow_transition.py:480–495 (`load_review_provenance`), 653–658 (`provenance_findings`, блок task_ids) | **major** | **Выбор sidecar по файлу не согласован с проверкой task_ids: sidecar чужой задачи тихо отбрасывается вместо DENY.** `load_review_provenance` пропускает (`continue`) sidecar, чьи `task_ids` не покрывают задачу; если под задачу sidecar нет вовсе, `provenance_findings` не видит «чужой» sidecar и выдает legacy-UNKNOWN («sidecar не найден»), а не DENY «approve другой задачи» (live-проба I: sidecar с tasks=9.9 → UNKNOWN, не DENY). ТЗ 05: «ложный approve для другого SHA/task отклоняется» — отклонение сильнее UNKNOWN. Тест `test_approve_other_task_rejected` проходит только потому, что в фикстуре рядом лежит второй sidecar, покрывающий задачу. → Не отбрасывать чужой sidecar молча: если под change есть sidecar, не покрывающий task_id, — это самостоятельный DENY/MISSING_INPUT-финдинг («approve не покрывает задачу X»), а не невидимость. |
| M2 | scripts/gate_runner.py:301–308 (`run_gate`, PASS-ветка) | **major** | **`pr_validate` с exit 0 при отсутствии PR-артефактов неотличим от пройденного, а «не считается пройденным» для SKIPPED не закреплено в overall.** Два Related момента. (a) ТЗ приемка: «pr_validate не запускается без PR-контекста **и не считается пройденным**» — сейчас SKIPPED-гейт в общем PASS-отчете выглядит пройденным (см. B1; для чистого pr_validate это спорно-допустимо, но в совокупности с B1 отчет «все PASS» вводит в заблуждение). (b) `diagnostics` PASS-гейта берется «последняя строка stdout» — у pr_validate это может быть произвольная строка; приемка «Отчёт показывает, какие gates **реально выполнены**» выполняется не до конца: поля `executed: true/false` или отдельный учет SKIPPED в `overall` отсутствуют. → Поле `executed` в GateReport gate-элементе + правило: SKIPPED-гейты перечислены в отчете отдельно, pre_merge с SKIPPED pr_validate не может давать «overall=PASS» без явной пометки «не все gates выполнены». |
| M3 | scripts/flow_transition.py:492–540 (`provenance_findings`), 543–552 (`_git_diff_for_head`) | **major** | **diff_digest сверяется только когда оба присутствуют — частичная провенанс дает ALLOW без digest.** `record-review` делает `--diff-digest` опциональным; `provenance_findings` проверяет digest лишь при `if diff_digest and head`. Sidecar с task/change/SHA и независимой ролью, но **без** diff_digest → ALLOW (live-проба C2: ALLOW). При этом Contract §9: UNKNOWN обязателен, когда проверка невозможна; спека требует соответствие «task/change/SHA/**diff**». Digest — не украшение, а единственная защита от approve «того же SHA, другой content» (history rewrite, force-push). → Без diff_digest — UNKNOWN-финдинг (как для отсутствующего SHA), либо требовать digest обязателен в record-review. Тест на «sidecar без diff_digest → не ALLOW». |
| m1 | scripts/gate_runner.py:484–485 (`is_stale`) | minor | Условие `return bool(head) and report.get("repo_head") not in (head, None) or (head is None and ...)` — приоритет `and`/`or` делает вторую ветку верной для любого report без repo_head при head=None... фактически корректно, но читается как ловушка; отчет без repo_head при валидном HEAD считается **не** STALE (`repo_head in (head,None)` → False→not STALE), т.е. поврежденный отчет (без repo_head) проходит как свежий. → Явные скобки + «отчет без repo_head» = STALE/UNKNOWN, не PASS. |
| m2 | scripts/gate_runner.py:521–561 (`write_review_provenance`) | minor | Sidecar пишется без проверки, что `reviewed_commit_sha` вообще существует в repo и что `verdict` в самом .md совпадает с verdict в sidecar: `record-review --verdict approve` на файл с вердиктом RETURN создаст sidecar-approve поверх RETURN-ревью (расхождение человекочитаемого и машинного доказательств). Проверка вердикта по файлу есть ниже по потоку (parse_verdict → INVALID_GATE), но sidecar при этом остается «согласованным» для других задач/изменений. → При record-review сверять `parse_verdict(review_path)` c `--verdict` и с SHA в репо; расхождение → exit 2. |
| m3 | scripts/flow_transition.py:473–477 (`load_review_provenance`, rev-парс) | minor | `re.search(r"review-(\d{3})-", pf.name)` для ревизии предполагает формат `review-NNN-*`; файл `review-5.1-probe.md` (task-first формат, легальный по flow_check.py:20–22) получает rev=0 и любые такие sidecar сравниваются по имени — порядок «последний sidecar» для task-first имен не определен. → Единый парс ревизии с `flow_check.REVIEW_FILE_*` (переиспользование, D1), не второй regex. |

---

## 2. Что проверено и подтверждено (оси ТЗ → live-пробы)

**Ось 1 — GateReport (ТЗ 05 §Gate Runner; контракт §11).** Все поля ТЗ присутствуют: `gate_id, scope, command, adapter_version, input_head, input_digest, started_at, duration, exit_code, status, log_path, diagnostics` (dataclass GateReport:192–207; тест `test_report_fields`). Digest включает HEAD репо **и** sha самих скриптов-ворот (`compute_input_digest`:217–234 — `repo_head` + `gate_script_sha` для flow_check/pm_bounds/pr_validate) — изменение скрипта ворот инвалидирует прежний PASS, требование ТЗ выполнено. STALE после нового коммита: **live-проба S** — run на клоне @f49f494, новый коммит → `status` показывает `STALE: HEAD репо изменился`, exit 1 ✓. exit-маппинг: 0→PASS, 1→FAIL, прочее/timeout/missing→ERROR (тесты + live FAIL по flow_check) ✓.

**Ось 2 — адаптеры.** Все адаптеры — subprocess с `cwd=str(repo)` и `timeout` (`run_gate`:277–279); timeout→ERROR (`test_timeout_is_error_and_blocking`), missing executable→ERROR (`test_missing_executable_is_error`), exit 2/7 (parse error)→ERROR (`test_parse_error_exit7_is_error`) ✓. SKIPPED только для pr_validate без PR-контекста — по явному правилу ТЗ ✓ (но см. B1 про pm_bounds). pm_bounds_check без явного режима не запускается и `--all-projects` в адаптере **отсутствует** как доказательство ✓ (grep по дифу; режимы commits/sessions/product-commits с обязательными аргументами; live-проба pm-mode=sessions — реальный запуск с exit 1 по отсутствующему реестру, честный FAIL).

**Ось 3 — provenance.** Sidecar `review-provenance/1` со всеми полями ТЗ (schema_version, project, change, task_ids, author/reviewer delegation, reviewed_commit_sha, diff_digest, verdict, timestamp, review_path) — `write_review_provenance` ✓. .md не переписывается ✓. Live-пробы на клоне реального репо:
- **self-review → DENY (WRONG_ROLE)** ✓ (проба A: author==reviewer → DENY с внятной деталью);
- **чужой SHA → DENY (STALE_EVIDENCE)** ✓ (проба B: sidecar на 8ec19fe при HEAD f49f494 → «approve зафиксирован для SHA… повторное review обязательно»);
- **чужой change → DENY (MISSING_INPUT)** ✓ (проба H);
- **согласованный sidecar → ALLOW** ✓ (проба C2: accept_review ALLOW при task/change/SHA/роли согласованы; merge_task — UNKNOWN только из-за EXTERNAL_ENFORCEMENT_UNKNOWN, что честно);
- **легаси (review .md без sidecar) → UNKNOWN/STALE_EVIDENCE «legacy evidence», merge не разрешен** ✓ (пробы E/F); тест `test_historic_merges_not_outlawed` — старые merge задним числом незаконными не объявлены ✓;
- **битый sidecar → UNKNOWN (AMBIGUOUS_STATE)** ✓ (проба G), не молчаливый пропуск;
- accept_review теперь ALLOW при согласованном sidecar — **сверено со спекой**: строгий режим поставки 05 активирован корректно, scenarios «Approve устарел» (DENY/STALE_EVIDENCE) и «Автор ревьюит себя» (DENY/WRONG_ROLE) выполняются живьем ✓. Но см. M1/M3 — два обходных пути к слишком мягкому вердикту.

**Ось 4 — audit JSONL.** Append-only (`open("a")`, тест `test_append_only_no_secrets` проверяет и неизменность прежних строк, и отказ на `password=`/`stdout=`) ✓; типы событий = списку ТЗ ✓; в записи — факты и ссылки (digest, log_path), stdout не копируется (live-проверка /tmp/audit-005.jsonl: только request/gate_report с digest) ✓; gate-логи отдельными файлами с усечением 128KB (`_write_log`) ✓; JSONL не единственное доказательство — состояние по-прежнему из Git/файлов ✓ (контракт §13 не сломан).

**Ось 5 — m10 (контракт §7).** `git show f49f494`: единственный файл `contracts/flow_control_contract.md`, +9/−2 ✓. archive_change = **sa** (решение 3.3-А, shadow-R6 S7 — цитата и дата приведены, формат решения Заказчика соблюден) + порядок 3.2-Б «archive_change → release» зафиксирован; в `STAGE_TABLE` (flow_transition.py:1030) sa добавлена первой ролью archive_change, dev_lead/integrator сохранены как допустимые — расхождений графа и таблицы нет ✓. Проверка решения по docs/shadow-r6-scenario.md: 3.3-А и 3.2-Б процитированы дословно ✓.

**Ось 6 — границы.** `git diff 83c60bf..f49f494 --name-only`: flow_check.py, pm_bounds_check.py, pr_validate.py, flow_state.py, session_check.py **не тронуты** (5 файлов: контракт, flow_transition, gate_runner, 2 тест-файла) ✓. Огр. 2 (00-README: не заменять ворота заглушками, не менять exit codes/режимы) соблюдено ✓.

**Ось 7 — тесты.** Полный прогон: **244 passed** (мой запуск, 2026-10-02, 24.9s); из них 48 в tests/test_gate_runner.py + tests/test_provenance.py. Негативные на месте: ERROR (timeout/missing/parse), SKIPPED (pr_validate), STALE (`test_stale_after_new_commit`, `test_status_cli_stale_exit1`, `test_input_digest_changes_with_head`), provenance-негативы (self-review, чужой SHA/task/change, битый sidecar, return-вердикт, legacy). Пробел: негатива «обязательный gate SKIPPED → отчет не PASS» нет (см. B1 — потому дефект и прошел).

**Live-проба FAIL flow_check на реальном репо — честность GateReport подтверждена.** `gate_runner run --repo . --scope post_agent` → FAIL, exit 1, диагностика: «15 закрытых dev-задач без code-review (J10): 0.1…4.4». Это **правда и честный FAIL**: approve-файлы review-001…004 не привязаны к задачам tasks.md ни именем (`review-004.md` не содержит task-id; `approved_review_tasks` парсит task-id из имени файла), ни sidecar (его в репо нет). GateReport не приукрашивает: ворота говорят «доказательства нет» — что соответствует принципу «самоотчёт агента не считается доказательством». Замечание к процессу, не к коду поставки: review-файлы следующих поставок стоит именовать с task-id (review-NNN-5.1-…) и/или снабжать sidecar — иначе J10 будет честно гореть после каждой поставки.

---

## 3. Проверенные Scenario (спека deterministic-flow)

- «Approve устарел после нового коммита» — строгая ветка: **DENY/STALE_EVIDENCE** подтверждена live-пробой B и STALE-пробой gate_runner ✓
- «Автор ревьюит себя» — **DENY/WRONG_ROLE** подтверждена live-пробой A ✓
- ТЗ 05 приемка: ложный approve другой task/change — DENY ✓ (но M1: тихий путь через «нет sidecar под задачу»); падающий/отсутствующий/зависший gate блокируют с разными кодами — **частично** (FAIL/ERROR/DENY — да; «отсутствующий» в смысле SKIPPED — нет, B1); pr_validate без PR-контекста не запускается ✓ и не считается пройденным — частично (B1/M2); отчет показывает реально выполненные gates и digest ✓/частично (M2).

## 4. Что НЕ проверено (честно)

- `openspec validate` в preflight/ci — CLI openspec в этой среде отсутствует; проверено только на fake-executable (как и у автора). Реальный npx-путь не испытан.
- Интеграция gate_runner с оркестратором (поставка 06) — вне зоны.
- Мультипроцессная гонка append в audit JSONL (одиночный писатель предполагается; межпроцессная атомарность дописывания не тестировалась).
- Поведение `diff-digest` на историях с merge-коммитами (base..head двухродительский дифф не рассматривал).
- m10-перестройка графа проверена чтением + тестами; отдельного shadow-прогона на истории Р6 после f49f494 не делал.

## 5. Рекомендация

**RETURN.** B1 обязан к исправлению (маленький, локальный: классификация skip-причин в `run_gates` + тест). M1–M3 настоятельно рекомендованы до поставки 06 — оркестратор начнет доверять overall, и текущие дыры (молчаливый PASS, частичный sidecar → ALLOW) станут разрешающими путями в автоматике. m1–m3 — на усмотрение dev, можно долгом. После фикса — повторное ревью диф-а исправления (append-only, review-006).
