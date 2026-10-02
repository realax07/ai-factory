# Review-007 — финальное ревью среза 4: поставки 06+07 (flowctl + m4 + байпас-тесты)

- **Ревьюер:** тот же независимый code-reviewer (review-001…006 — мои)
- **Дата:** 2026-10-02
- **База:** ветка `deterministic-flow`, ревьюируемые коммиты: `b3de86a` (поставка 06), `4cf4d38` (поставка 07 + m4), `8759fc3` (.gitignore). Зафиксирован и проверен пост-ревью-коммит `b94878e` (scripts/flow_mode.py — вне-zone, см. §7)
- **Диф ревью:** `2163a59..8759fc3` — 5 файлов, +2606/−1 (scripts/flowctl.py +932, tests/test_flowctl.py +700, tests/test_workflow_bypasses.py +968, scripts/flow_transition.py +5/−1, .gitignore +1)
- **Метод:** чтение диффа и ТЗ (00, 06, 07, контракт §4–10, docs/shadow-r6-scenario.md) + полный прогон тестов + **собственные live-пробы** на scratch-фикстурах (tmp-репозитории, fixture-реестры; реальный ~/.hermes/state/ и живой ai-factory не тронуты — `git status` после проб чист, кроме предсуществующего `?? docs/process-context.md`)
- **История ревью:** append-only; седьмая запись, review-001…006 не изменялись

---

## Вердикт: **APPROVE**

Обе поставки соответствуют ТЗ по существу; все десять осей проверки отработаны, ключевые гарантии подтверждены моими независимыми live-пробами, а не только тестами автора: dry-run действительно без side effects; идемпотентность run по correlation ID выдерживает 4-поточную гонку (ровно один `started=True`, статус running, вторая сессия не создается); STALE_SNAPSHOT ловит и чужой git-коммит, и чужую запись в реестр; crash-recovery сохраняет данные, повторный run отказывает, finish на needs_attention → blocked; goal-артефакт честно помечен «подготовка ≠ запуск»; m4 закрыт ровно так, как рекомендовал review-006. Регрессий нет: **327 passed** (мой полный прогон, 2026-10-02; 251 предсуществующих + 76 новых), openspec `validate --all --strict` **4/4 green** (реальным CLI). Три новых замечания — minor (m11–m13), не блокирующие.

---

## 1. Приемка по осям (каждая — live-пробой)

| Ось | Результат | Подтверждение (live, независимое) |
|---|---|---|
| **1. Идемпотентность run** | ✓ | 4 параллельных процесса `run` одного CID: ровно 1 сессия в реестре, `started=True` ровно у одного, статусы `[running, prepared×3]`; повторные run → `idempotent: true`, started=False. Повтор prepare same payload → идемпотентен; тот же CID с другим payload (owner-pm) → **DUPLICATE_PAYLOAD**, exit 1. Гонка двух prepare одного CID с общим реестром → ровно одна reservation (вторая ZONE_CONFLICT, state no-state/prepared — см. m12) |
| **2. prepare --dry-run** | ✓ | После dry-run: state-файла нет, реестр пуст (`[]`), goal-файла нет, exit 0, `dry_run: true`. Ни одного side effect |
| **3. STALE_SNAPSHOT** | ✓ | Чужой git-коммит между prepare и run → exit 1, reason STALE_SNAPSHOT, статус не продвинут (prepared). **Дополнительно моя проба:** чужая reservation в ДРУГОМ проекте (меняет байты реестра) между prepare и run → тоже STALE_SNAPSHOT (registry_digest входит в digest) — fail-closed, чужих изменений не пропускает. См. m11 о цене этой строгости |
| **4. Recovery** | ✓ | Crash после reservation (prepared, чистое дерево) → flowctl reconcile → stale; crash после записи файлов (running + dirty) → needs_attention; правки агента на месте (`X = 99`); повторный run → exit 1 («статус не допускает запуск»); finish на needs_attention → blocked/exit 2; ничего не удалено молча |
| **5. adapter=manual** | ✓ | run возвращает `started: true` с note «adapter=manual — исполнение delegate_task ВНЕШНЕЕ, этот статус не является фактом работы агента»; goal-файл содержит блок «сам факт запуска фиксируется отдельно и не следует из наличия файла» + «push НЕТ». Подготовленный goal нигде не выдается за запуск |
| **6. Вердикт по фактам** | ✓ | finish строит вердикт из `sc.check` (фактический diff vs зоны, WRONG_WORKTREE/WRONG_BRANCH/OUT_OF_ZONE) + `gr.run_gates` (реальный exit/digest); отчет агента читается только для digest/пути — на вердикт не влияет. accepted ⇔ zone ok AND gate_exit=0; SKIPPED-gates → дефект → не accepted; STALE gate-отчета → дефект. Отчет агента «обходной» не пробьет: gates и зона считаются из Git, не из текста |
| **7. Байпас-тесты (9 пунктов ТЗ 07)** | ✓ | 46 TC покрывают все 9 пунктов, у каждого пункта есть и негатив, и контроль-ALLOW. Выборочно воспроизведено мною live: п.3 (саморевью/чужой SHA/чужой task → DENY с верным кодом; валидный sidecar → ALLOW), п.6 (битый реестр → REGISTRY_ERROR на reserve, статус UNKNOWN), п.7 (gate timeout→ERROR/exit 2, missing→ERROR, invalid exit 7→ERROR), п.8 (crash→needs_attention без повторной делегации — сквозной через CLI), п.9 (merge_task/release при полном локальном комплекте все равно несут EXTERNAL_ENFORCEMENT_UNKNOWN, GateReport не содержит утверждений о защите main) |
| **8. m4 (rev sidecar)** | ✓ | `rev('review-001-1.1.md.provenance.json')=1`, task-first тоже, невалидное имя → 0; выбор max ревизии при смешении rev-first/task-first — численный, не лексикографический (моя проба: sidecar rev-9 чужой при rev-1 своем → DENY по факту чужого, свой rev-5+rev-1 → выбран rev-5 → ALLOW). Фикс ровно по рекомендации review-006 (срез SUFFIX перед матчингом) |
| **9. Deadlock-фикс state_write_locked** | ✓ | `_acquire_lock` не реентерабелен — автор это знает и документирует в docstring `state_write`: `state_write_locked` берет лок **ровно один раз**, читает, мутирует, пишет под тем же локом. Проверка гонки: 4 параллельных run → ни одного TimeoutError, ни одной потери записи (итог running ровно у одного). Реестр и state лочатся раздельно, вложения нет (`registry_transition` лочит реестр и освобождает до `state_write_locked`) |
| **10. Границы** | ✓ | `git diff 2163a59..8759fc3 -- contracts/ openspec/ docs/ code-reviews/ pm_bounds_check.py session_worktree.sh flow_check.py gate_runner.py session_check.py flow_state.py` — **пусто**. Тронуты только flow_transition.py (m4-фикс, 5 строк), flowctl.py (новый), 2 тест-файла, .gitignore. Огр. 2 (00-README: flow_check/pm_bounds не заменяются, exit codes сохранены — прокси-команды пробрасывают argv целиком) ✓ |

## 2. Приемочные сценарии ТЗ 06 (по ТЗ — «отдельными прогонами»)

Покрыты тестами автора и подтверждены прогоном: human gate (create_change без approval_ref → HUMAN_APPROVAL_REQUIRED, exit 1, сессии нет), падение агента (finish на prepared → blocked), stale snapshot (см. ось 3), gate failure (flow_check FAIL → returned; gate missing → blocked), restart без повторной делегации (reconcile → run отказ). Полный цикл dev task → review request (prepare → работа в зоне → post-gates → accepted) — тест `test_finish_accepted_in_zone_gates_pass`, green. Никакого автоматического продвижения к QA/release в коде нет (finish останавливается на локальном вердикте).

## 3. Замечания

| № | Место | Серьезность | Замечание и рекомендация |
|---|---|---|---|
| m11 | scripts/flowctl.py:529 (run), docs 06 | **minor** | **Чувствительность STALE к нерелевантной записи реестра + вырожденный recovery-путь.** digest включает registry_digest (байты всего реестра), поэтому чужая reservation в другом проекте/зоне между prepare и run дает STALE_SNAPSHOT — сам по себе это fail-closed и ось 3 («не пропускает чужие изменения») выполняется. Но восстановление по документированному пути («повтори prepare») не работает: повтор prepare того же CID идемпотентен и **не переснимает** digest (возвращает старую запись), новый CID упирается в ZONE_CONFLICT со своей же живой reservation. Фактический путь — reconcile (помечает stale) → prepare с **новым** CID — нигде не документирован; note у STALE-отказа («повтори prepare») вводит в заблуждение. Live-проба: prepare→чужой reserve(другой проект)→run=STALE→repeat prepare (idempotent, digest не обновился)→run снова STALE→prepare новый CID=ZONE_CONFLICT→reconcile→stale→prepare новый CID=OK. Рекомендация: (а) поправить note у STALE_SNAPSHOT на честный путь «reconcile → новый correlation ID» (одна строка); (б) долгом — сузить digest реестра до проекции, относящейся к scope (repo+project/зоны), либо исключить registry_digest из prepared-сравнения при неизменном наборе зон. Самостоятельного обхода не создает: STRICT — в безопасную сторону |
| m12 | scripts/flowctl.py:cmd_prepare (шаг 3→4) | **minor** | **Порядок «решение → fingerprint → side effects» оставляет окно осиротевших side effects.** При гонке двух prepare одного CID побеждает reservation первого, второй получает ZONE_CONFLICT и выходит, не записав state; если же side effect (worktree) уже создан, а решение после переснимка перестало быть ALLOW (ветка шага 6), reservation остается зарезервированной («для разбора») — это осознанный выбор автора (документирован в комментарии шага 4) и он fail-safe (ничего не теряется, никакого повторного делегирования), но ПМ должен знать: после ZONE_CONFLICT/«перестало быть ALLOW» возможна живая reservation без state-записи, которую разыскивает только `status`/`reconcile` по реестру. Рекомендация: в note этих отказов добавлять delegation_id, чтобы разбор не требовал чтения реестра вручную |
| m13 | scripts/flowctl.py (prepare без --dry-run), README фабрики | **minor** | **`--owner-pm` не обязателен на уровне парсера.** docstring обещает «обязателен без --dry-run», но validate отсутствует: prepare без --dry-run и без --owner-pm создает сессию с owner_pm=None. Резервация принимает это (reserve не требует owner_pm), что ослабляет атрибуцию сессии (кто владелец — неизвестно). Рекомендация: явная проверка в cmd_prepare перед шагом 4 (exit 2 MISSING_INPUT). Не обход workflow: зоны/решения/reservation работают и без атрибуции |

## 4. Проверка m4-фикса отдельно (долг review-006)

Фикс `4cf4d38` — ровно рекомендованный вариант (срез `PROVENANCE_SIDECAR_SUFFIX` перед матчингом). Пробы: rev-first → 1/9, task-first → 2/3, обычный .md → 1, мусор/None → 0. Выбор «чужого» sidecar теперь по максимальной ревизии (unit-тест автора + моя проба с rev-001 vs rev-009: выбран 009, DENY называет фактический sidecar). Регрессия выбора покрывающего: max-rev свой → ALLOW. Три новых TC в классе TestM4SidecarRevisionParsing — green. Долг закрыт полностью.

## 5. Что проверено (сводка)

- Полный прогон: **327 passed** (мой, 45s; предсуществующие 251 отдельно перепроверены — green); openspec `validate --all --strict` реальным CLI — 4/4 green
- Live-пробы осей 1–6, 8–9 (таблица §1); байпас-пробы п.3, 6, 7, 8, 9 ТЗ 07 — воспроизведены независимо от тестов автора
- Идемпотентность/гонки: 4-поточная гонка run × 5 повторов; гонка prepare; DUPLICATE_PAYLOAD; ZONE_CONFLICT
- Границы диффа (ось 10) — чисто; exit-коды прокси (inspect/check/next) сохранены (тесты + код-чтение)
- Вердикт accepted/returned/blocked: ветвление только по zone_res/gate_report; текст отчета агента в вердикт не входит (проверено чтением cmd_finish + тестами accepted/returned/blocked)

## 6. Что НЕ проверено (честно)

- Мультипроцессная гонка audit JSONL (append из двух процессов одновременно) — вне зоны, перенесено из review-005/006
- `--create-worktree` в живую через session_worktree.sh — покрыт тестом автора (worktree переживает crash), в живых пробах не дублировал
- Поведение flowctl при FLOW_MODE=enforcing — не проверяемо: см. §7
- HTTP/WebUI — вне MVP по ТЗ 06

## 7. Наблюдение вне диффа ревью (не замечание к поставкам 06/07)

Поверх зафиксированного HEAD ревью (8759fc3) появился коммит `b94878e` — scripts/flow_mode.py (переключатель shadow/enforcing, «включить enforcement после review-007»). На момент моей проверки: **компоненты пакет его еще не читают** — ни flowctl, ни session_check, ни flow_transition не импортируют get_mode/blocks_on; режим сейчас ни на что не влияет (дефолт shadow, файла нет). Это не дефект поставок 06/07 и не нарушение границ (файл новый, изолированный), но фиксирую для Заказчика: фактическое включение enforcing потребует отдельного изменения в компонентах + отдельной приемки (переключатель сам по себе enforcement не включает). Также зафиксирован незакоммиченный `docs/process-context.md` (память ПМ → репозиторий, распоряжение Заказчика) — вне зоны ревью.

## 8. Рекомендация

**APPROVE** обеих поставок (06+07). Задачи могут вливаться в ветку; m11–m13 — долгом к следующему срезу либо к doc-фиксу (m11 — одна строка note). Пакет add-deterministic-flow в целом готов к докладу Заказчику о переводе в enforcing (Шаг B/C ТЗ 07) — с оговоркой §7: переключатель режима требует подключения в компонентах и собственной приемки до фактической блокировки.
