# Code Review 001 — change add-deterministic-flow, поставки 01 + 03

- **Ревьюер:** независимый code-reviewer (не автор кода)
- **Дата:** 2026-10-02
- **База:** ветка `deterministic-flow`, HEAD `77d2978`
- **Дифы:** `744ab95` (contracts/flow_control_contract.md), `77d2978` (scripts/flow_transition.py + tests/test_flow_transition.py)
- **Нормативные источники:** ТЗ `docs/chatgpt-deterministic-flow/00,01,03`, спека `openspec/changes/add-deterministic-flow/specs/deterministic-flow/spec.md`, requirements.md (FR-1…FR-8), design.md (D1–D6)
- **История ревью:** append-only; это первая запись.

---

## Вердикт: **RETURN**

Поставки добротные по архитектуре (таблица этапов D3, честный UNKNOWN, shadow read-only, переиспользование парсеров flow_check импортом), но есть 3 major: нарушение транзитивности порядка Флоу 1 (проверено live-прогоном), неработающий [P]-механизм в CLI-пути (проверено live-прогоном) и нереализованный хотфикс-долг Флоу 3. Все три — расхождения с ТЗ 03 дословно; в shadow-режиме они не блокируют пилот, поэтому RETURN, а не отклонение поставки.

---

## 1. Поставка 01 — contracts/flow_control_contract.md (744ab95)

### Соответствие ТЗ 01 (по пунктам)

| Треб. ТЗ 01 | Где в контракте | Статус |
|---|---|---|
| 1. Спека требований и сценариев | `openspec/changes/.../specs/deterministic-flow/spec.md` (дельта change-пакета; основная появится в `openspec/specs/` при archive) | ✓ (по OpenSpec-методологии) |
| 2. Интерфейс 4 операций + side effects | §4 + таблица чистоты | ✓ |
| 3. Scope, неизвестный Flow/неоднозначный scope блокируют | §3 | ✓ |
| 4. Граф действий, не один State(Enum) | §7 по флоу | ✓ (см. minor #5) |
| 5. ActionRequest: actor_role/project/scope/action/approval_ref/expected_snapshot_digest | §6 | ✓ |
| 6. 9 стабильных кодов + человекочитаемые детали с путями | §9 (таблица: код/значение/источник/обязательное содержание детали) | ✓ |
| 7. Приоритет источников, конфликт фактов → блокировка | §2 (лестница 1–2–3) | ✓ |
| 8. Матрица ответственности (runtime/CI/branch protection/CLI) | §12 | ✓ |

Приемка ТЗ 01: «версия формата решения» — §10 (`decision_format_version = 1`) ✓; «никакой этап не стартует на основании текста агента» — §2 ✓; «OpenSpec validate --all --strict проходит» — **не проверено** (см. «Что не проверено»).

Честность: контракт прямо запрещает объявлять декларативные правила обеспеченными (§1.3), self-report агента не evidence (§2), UNKNOWN не повышает статус (§9, §12) — ось «нет скрытого enforcement/shadow» выдержана: контракт описывает check-слой, исполнение вынесено в поставки 04–05, shadow-режим оговорен (§14). Ссылка на «факты по коду на HEAD d3304c3» в §12 корректна (d3304c3 — предок HEAD).

### Замечания к поставке 01

| # | Файл:строка | Серьезность | Замечание → рекомендация |
|---|---|---|---|
| R1 | contracts/flow_control_contract.md:100–110 (§6 Decision) | minor | `Decision` не содержит `requirements_checked`, хотя ТЗ 03 (строка 7) перечисляет его в составе Decision и реализация 03 его имеет → контракт отстает от ТЗ/реализации. → Добавить поле в §6 (или явно пометить как расширение среза 1). |
| R2 | contracts/flow_control_contract.md:194–209 (§10) | minor | Формат `customer_decision v1` объявляет версию (`decision_format_version = 1`), но в самой структуре код-блока поля версии нет — правило «нераспознаваемая/устаревшая версия → MISSING_INPUT» (строка 208) нереализуемо: нечему распознаваться. → Добавить `decision_format_version: 1` внутрь структуры. |
| R3 | contracts/flow_control_contract.md:123–158 (§7) | minor | Чеклист приемки §15 утверждает «таблица … покрывает Флоу 1–5», фактически таблично описан только Флоу 1; Флоу 2–5 — маркерные списки без полных колонок «роль/evidence/gates/результат». Самозаявленный пункт чеклиста выполнен не полностью. → Довести таблицы Флоу 2–5 либо скорректировать формулировку §15. |

---

## 2. Поставка 03 — scripts/flow_transition.py + tests (77d2978)

### Проверено исполнением (не чтением)

- `pytest tests/test_flow_transition.py` — **66 passed**; `pytest tests/test_flow_state.py` — 24 passed.
- Live-проба A (fixtуре-репо, requirements=ЧЕРНОВИК, полный change-пакет+sdd+дельты): `check_action(dev_task, task=1.1)` → **ALLOW** (см. major #1).
- Live-проба B ([P]-задача в tasks.md, CLI check без `--parallel`): exit 0, `required_gates` **без** admit_session-пометки (см. major #2).
- Live-проба C (Флоу 3 merge_task): STALE_EVIDENCE присутствует, но это provenance-пометка, не долг хотфикса (см. major #3).
- Exit codes 0/1/2 подтверждены тестами TestCLI (ALLOW→0, DENY→1, UNKNOWN/ошибка→2) — соответствие FR-8/ТЗ 03 ✓.

### Соответствие спеке дословно

- Decision-поля ТЗ 03: все 11 присутствуют (`requirements_checked` включен) ✓.
- 9 кодов причин реализованы, `REASON_CODES` = контракт §9 ✓; каждый Finding несет человекочитаемую деталь с путем к evidence/правилу ✓ (ТЗ 03 «Вывод содержит конкретный недостающий факт и источник правила»).
- UNKNOWN не разрешает: `allowed=(status==ALLOW)`; тест `test_unknown_dominates_allow` ✓. UNKNOWN обязателен при непроверяемости: битый снимок, неизвестный flow, unknown-факты, deps без evidence, provenance — ✓ (D3/D4 соблюдены).
- DENY перечисляет ВСЕ причины: `blocking_reasons` без дедупликации потерь, тест `test_deny_lists_all_reasons` ✓.
- Provenance compat (ТЗ 03 п.8, спека «Provenance review»): accept_review/merge_task → UNKNOWN со STALE_EVIDENCE, дополнительно EXTERNAL_ENFORCEMENT_UNKNOWN на merge (FR-7) ✓; approve чужой задачи не принимается (`_approvals_for_task` по task-id, тест) ✓.
- Этапные ворота: create_change/release без решения → HUMAN_APPROVAL_REQUIRED; dict-формат проверяет grants и привязку scope/фазы; решение другой фазы не переносится (тесты спека-сценариев) ✓. «ПМ считает согласованным» строкой проходит в срезе 1 — задокументировано в D5 как ограничение (strict-верификация — follow-up), для release тест подтверждает, что маскировку не пройти из-за INVALID_GATE. Приемлемо для срезa 1.
- Параллель/зависимости: зависимости через `flow_check.closed_dev_tasks` + `approved_review_tasks` импортом (переиспользование ✓, дублирования парсеров в 03 нет); зависимая ждёт merge предшественницы (тесты + CLI next waiting) ✓; две независимые [P] ready одновременно ✓ (спека-сценарий).
- Shadow read-only: тесты фиксируют git status/HEAD/файлы/реестр до и после check+next ✓; никаких записей в коде нет ✓. Скрытого enforcement нет: exit-коды информационные, ничего не блокируется извне.

### Замечания к поставке 03

| # | Файл:строка | Серьезность | Замечание → рекомендация |
|---|---|---|---|
| R4 | scripts/flow_transition.py:418–428 (`check_dev_task`), 544–557 (`check_release`) | **major** | **Нетранзитивный порядок Флоу 1.** `check_dev_task` проверяет только arch review + задачу + deps, но не `_requirements_approved` — live-проба A: requirements в статусе draft (и так же при отсутствующем requirements.md — факт missing не читается ни одной проверкой dev-пути) → dev_task **ALLOW**. ТЗ 03 п.2 дословно: «утверждённые требования → change/SDD → architecture review → dev task». Цепочка рвется: create_change и architecture_review требования проверяют, dev_task — нет. Аналогично `check_release` отличает только «есть открытые задачи»: завершенный `archive_change` (дельты слиты, openspec validate) от «просто все чекбоксы [x]» не отличим — факта архивации в снимке нет, а по D3 отсутствие критерия правила = UNKNOWN, не молчаливое ALLOW. Тест `test_unapproved_requirements_blocks_dev` проверяет create_change, не dev_task — дыра не покрыта. → Включить `_requirements_approved` в `check_dev_task`; для release: факт archive или UNKNOWN при его отсутствии; добавить негативный тест «dev_task при draft requirements → DENY/INVALID_GATE». |
| R5 | scripts/flow_transition.py:1006–1011 (`_cmd_check`), 1138–1139 (`--parallel` store_true), 422–427 (`check_dev_task`) | **major** | **[P]-механизм не работает в CLI-пути (главном пользовательском).** `--parallel` объявлен `store_true`, поэтому `args.parallel` — всегда bool: `parallel = args.parallel` дает False, и ветка `if parallel is None: parallel = parallel_auto` (автодетект [P] из tasks.md, заявленный в docstring и тесте `test_check_cli_dep_evidence_from_repo`) недостижима. Live-проба B: [P]-задача без явного флага не получает admit_session-пометку зон. Дополнительно: API-путь принимает `task_parallel=True` на веру — соответствие маркеру [P] в tasks.md не проверяется, факта [P] в snapshot нет; правило ТЗ 03 п.1 «параллельная задача допускается только при [P]» не проверяемо ни одним путем (по D3 нехватка факта должна давать UNKNOWN, не доверие флагу). Тест-пробел: CLI-тесты не ассертят admit_session-gate — потому баг не пойман. → `--parallel` с `default=None` (три состояния); факт [P] в snapshot (координация с 02) либо UNKNOWN при task_parallel без подтверждения; тест на gate. |
| R6 | scripts/flow_transition.py:591–601, 727–737; tests:645–652 | **major** | **Хотфикс-долг Флоу 3 не отслеживается.** ТЗ 03 п.4 + контракт §7: «Пока PR-цикл не закрыт, все последующие действия этого scope получают STALE_EVIDENCE-пометку незакрытого долга». Реализация: `emergency_stabilize` кладет PR-цикл в собственный `required_gates` (это тест `test_full_cycle_not_declared_done`), но последующие действия Флоу 3 (accept_review/merge_task) никакой пометки незакрытого долга не получают — live-проба C: STALE_EVIDENCE на merge_task это provenance-compat, не долг; механики «PR-цикл закрыт/не закрыт» нет ни в фактах, ни в коде. Хотфикс формально может «завершиться» merge без последующего PR. → Факт `hotfix.pr_pending` в snapshot (координация с поставкой 02) либо на срез 1 честный fallback: STALE_EVIDENCE-пометка на все post-emergency действия Флоу 3, пока факт недоступен (по D3 — UNKNOWN/пометка, не молчание); тест на merge_task Флоу 3 с маркером долга. |
| R7 | scripts/flow_transition.py:344–389 (`_approval_finding`) | minor | Привязка решения Заказчика: `phase` в scope_ref сравнивается с `scope.flow` — «фаза» сведена к номеру флоу. Спека-сценарий «Решение другой фазы» про фазы внутри процесса (например фаза А/Б релиза одного change): решение соседней фазы того же flow не будет различено. → Документировать упрощение в D5/контракте §10 либо расширить scope_ref (фаза ≠ flow). |
| R8 | tests/test_flow_transition.py (классы TestFlow2–5, TestCLI) | minor | Приемка ТЗ 03: «табличные тесты для **каждого** Flow: … неподходящая роль, отсутствие решения заказчика, устаревшее evidence». Роли протестированы только для Флоу 1; для Флоу 2–5 нет ни одного wrong-role-кейса; STALE_SNAPSHOT не проверен на флоу 2–5. → Добавить по одному негативному кейсу роли/evidence на флоу (таблично, параметризация). |
| R9 | scripts/flow_transition.py:112–127 (`ActionRequest.to_dict`) | minor | Сериализация неполна: `expected_snapshot_digest` и `dependency_evidence` не попадают в to_dict — при фиксации решений в shadow-логе (расхождения с ПМ — данные среза 1) часть входа решения теряется. → Дополнить to_dict (digest — полностью, evidence — дайджестом). |
| R10 | scripts/flow_state.py:244–252 (наблюдение, вне дифа этого ревью) | minor / координация | Поставка 03 потребляет факт `reviews.approved`, который flow_state строит **собственным** regex-парсером вердиктов вместо `flow_check.parse_verdict` — ось «переиспользование парсеров без дублирования» нарушена на уровне 02 (расхождение возможно на комбинированных вердиктах «approve … доработка», где parse_verdict дает return, а дубль — approve). Сам flow_transition дублирования не содержит. → Передать как замечание ревью поставки 02: заменить на `flow_check.parse_verdict`. |

### Что хорошо (зафиксировать для истории)

- Таблица этапов D3 реализована буквально (STAGE_TABLE), правила не if-лесом; отсутствующий критерий → UNKNOWN, не DENY — семантика честности выдержана.
- Переиспользование `flow_check.closed_dev_tasks`/`approved_review_tasks` импортом (D1) — дублирования парсеров в самой поставке 03 нет.
- Тесты shadow-режима — сильные: фиксация git status/HEAD/дерева файлов и реестра до/после; чистота check_action (без мутаций, повтор воспроизводим).
- DENY-семантика «все причины сразу» и стабильные коды покрыты тестами на комбинацию (WRONG_ROLE+INVALID_GATE+HUMAN_APPROVAL_REQUIRED).

---

## Проверенные Scenario спеки

- «Разрешение действия»: недостаточный evidence (DENY/MISSING_INPUT, тест + live), неоднозначное состояние (AMBIGUOUS_STATE: неизвестный flow, битый снимок, FLOW_ID_INVALID), чужая роль (WRONG_ROLE, 3 теста) — ✓.
- «Порядок флоу 1–5»: dev до arch review ✓, независимые [P] ready ✓, Флоу 2 эскалация с next_candidates [create_change, escalate_to_customer] ✓ — НО транзитивность порядка (R4) и [P]-проверяемость (R5) — с дефектами.
- «Этапные ворота Заказчика»: старт change без решения ✓, решение другой фазы ✓ (с упрощением R7).
- «Честная граница enforcement»: EXTERNAL_ENFORCEMENT_UNKNOWN на merge/deploy, не повышает статус ✓.
- «Provenance review»: compat UNKNOWN/STALE_EVIDENCE ✓, approve чужой задачи ✓; «автор ревьюит себя» — непроверяемо в срезе 1 (совместимо с D4, documented).
- «Режим shadow»: тесты read-only ✓.

## Что НЕ проверено (честно)

- `openspec validate --all --strict` (приемка ТЗ 01) — CLI openspec не установлен в среде ревью; проверяется CI (.github/workflows/flow.yml). Ревьюером не исполнялось.
- Интеграция с поставками 04/05 (admit_session, gate runner) — не поставлены; корректность required_gates-ссылок проверена только структурно.
- Дублирующий парсер вердиктов flow_state (R10) — детально ревьюится в поставке 02, здесь только влияние на 03.
- Поведение на реальном большом репозитории (производительность inspect-пересборок в `_cmd_next`) — не замерялось.

## Итог

**RETURN.** Обязательны к исправлению: R4, R5, R6 (major). R1–R3, R7–R9 — minor, желательно в том же фикс-коммите; R10 — координация с ревью поставки 02. После фикса — повторное ревью диф-а исправления (append-only: следующий файл review-002.md).
