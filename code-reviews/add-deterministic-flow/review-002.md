# Code Review 002 — change add-deterministic-flow, повторное ревью (фикс поставки 03)

- **Ревьюер:** независимый code-reviewer (не автор кода; тот же, что review-001)
- **Дата:** 2026-10-02
- **База:** ветка `deterministic-flow`, HEAD `72aae6e` (фикс-коммит)
- **Диф ревью:** `72aae6e` (scripts/flow_transition.py +100/−10, tests/test_flow_transition.py +204)
- **Предмет:** закрытие замечаний review-001: R4/R5/R6 (major) + R7/R8/R9 (minor). R1–R3 (поставка 01, контракт) — автор не трогал сознательно, оценка отдельно (§4). R10 — вне зоны (координация с ревью поставки 02).
- **История ревью:** append-only; это вторая запись (review-001.md не изменялся).
- **Метод:** как в review-001 — живые пробы на fixture-репозиториях + чтение дифа, не «по диагонали».

---

## Вердикт: **APPROVE**

Все три major закрыты по существу, каждый подтвержден live-пробой (не только тестами автора). Регрессий не найдено: 104 теста green, поставка 02 не задета (диф не трогает flow_state), семантика ALLOW/DENY/UNKNOWN и next_candidates не изменены (сверено с 77d2978), shadow read-only подтвержден повторно. R1–R3 (minor, поставка 01) ACCEPT не блокируют — переносятся как долг поставки 01.

---

## 1. Проверка закрытия major (по рецептам review-001, live-пробы)

### R4 — транзитивный порядок Флоу 1: ЗАКРЫТ

- `check_dev_task` теперь начинается с `_requirements_approved` (flow_transition.py:432–440) — проверяет ВСЕХ предшественников цепочки «утверждённые требования → change/SDD → arch review → dev_task», а не только ближайшего этапа.
- `check_release` при отсутствии факта `change.archived` дает MISSING_INPUT → UNKNOWN (flow_transition.py:613–624) — «все чекбоксы [x]» больше не равны молчаливому ALLOW (D3 соблюден).
- **Live-проба A′ (CLI):** requirements=ЧЕРНОВИК + dev_task 1.1 → **DENY/exit 1** [INVALID_GATE] (в review-001 было молчаливое ALLOW). Проба A″: requirements.md отсутствует → **DENY/exit 1** [MISSING_INPUT, INVALID_GATE].
- **Live-проба D′ (API):** все задачи [x], факт archive отсутствует, release → **UNKNOWN** [MISSING_INPUT, EXTERNAL_ENFORCEMENT_UNKNOWN], деталь называет archive_change явно.
- Негативные тесты есть (TestR4TransitiveFlow1Order: draft/missing requirements, release без факта архивации) — ровно тот кейс, которого не хватало (`test_unapproved_requirements_blocks_dev` проверял только create_change).

### R5 — [P]-механизм в CLI-пути: ЗАКРЫТ

- `--parallel` переведен в три состояния: `action="store_true", default=None` (flow_transition.py:1220–1222) — автодетект [P] из tasks.md достижим.
- Новое поле `ActionRequest.parallel_confirmed`: подтверждением служит только маркер, разобранный из tasks.md (CLI check: `parallel_confirmed = bool(info.get("parallel"))`; CLI next: из парсера). Флаг/API на веру не принимается: `task_parallel=True` без `parallel_confirmed is True` → MISSING_INPUT (flow_transition.py:447–458).
- **Live-проба B′ (CLI):** [P]-задача 1.2 БЕЗ флага → **ALLOW/exit 0**, admit_session-пометка зон в required_gates присутствует (в review-001 — отсутствие пометки).
- **Live-проба B″ (CLI):** `--parallel` на открытой не-[P] задаче → **UNKNOWN/exit 2**, деталь «task_parallel=True без подтвержденного маркера [P] в tasks.md» — флаг на веру не прошел.
- **Live-проба B‴ (API):** `task_parallel=True` без подтверждения → блокирующий MISSING_INPUT по маркеру; тест `test_parallel_without_marker_confirmation_unknown` фиксирует UNKNOWN на открытой задаче.
- Регресс-грань закрыта тестом `test_non_parallel_task_unaffected` (обычная задача без флага — прежнее поведение).

### R6 — хотфикс-долг Флоу 3: ЗАКРЫТ

- `_hotfix_debt_findings` (flow_transition.py:471–493): STALE_EVIDENCE-пометка «незакрытый долг хотфикса» + gate «PR-цикл … обязателен до завершения» на accept_review И merge_task Флоу 3 (проверка `flow != 3: return []` — Флоу 2 не задет).
- **Live-проба C′ (CLI):** merge_task Флоу 3 → пометка долга в details ✓, долг-гейт в required_gates ✓ (сравнение с 77d2978 на том же fixture: пометки не было — эффект именно от фикса).
- **Live-проба C″:** merge_task Флоу 2 → долга нет ✓ (точечность подтверждена).
- Форма — заявленный в review-001 fallback («факт hotfix.pr_pending в снимке среза 1 не строится → честная пометка, не молчание»), координация с поставкой 02 задокументирована в докстринге и деталях. Соответствует D3.

---

## 2. Проверка закрытия minor

| # | Статус | Подтверждение |
|---|---|---|
| R7 | ЗАКРЫТ | Docstring `_approval_finding` документирует упрощение «фаза == scope.flow», расширение scope_ref — follow-up. Наблюдение (не замечание): в самом design.md D5 формулировка не дополнена, ссылка докстринга «зафиксировано в design D5» — с натяжкой;docs-правка возможна при случае, блокировать нечего. |
| R8 | ЗАКРЫТ | `TestR8RolesAndEvidenceFlows2to5`: параметризованные wrong-role и STALE_SNAPSHOT на Флоу 2–5 (DENY + соответствующий код на каждом) — приемка ТЗ 03 «табличные тесты для каждого Flow» выполнена. Тесты green. |
| R9 | ЗАКРЫТ | `to_dict` несет `expected_snapshot_digest`, `dependency_evidence` (полностью, как и рекомендовано), `parallel_confirmed`. Live-проба F′ + тесты сериализации (в т.ч. None-случаи). |

---

## 3. Отсутствие регрессий

- `pytest tests/test_flow_transition.py` → **80 passed**; `pytest tests/test_flow_state.py` → **24 passed**; весь набор → **104 passed** (было 66+24; рост за счет TestR4/R5/R6/R8/R9 — 14 новых тестов, из них негативные, что и требовалось).
- **Поставка 02 не задета:** диф 72aae6e трогает только flow_transition + его тесты; test_flow_state 24/24 без изменений.
- **Семантика спеки не изменена:** ALLOW/DENY/UNKNOWN-классификация прежняя; новое UNKNOWN появляется только там, где review-001 требовало (неподтвержденный [P], отсутствие факта archive). `next_candidates` сверены с 77d2978 на идентичном fixture (API include_next и CLI next) — **поэлементно идентичны**; зависимая задача 3.1 по-прежнему не проскакивает раньше merge 1.2.
- **Shadow read-only повторно:** check+next на fixture-репо — git status чист до/после.
- Побочный эффект реализации: debt-пометка R6 сейчас безусловна для всех post-emergency действий Флоу 3 (даже когда PR-цикл фактически закрыт) — это осознанная цена отсутствия факта в срезе 1, закроется вместе с `hotfix.pr_pending` в поставке 02. К ним и привязано, не блокирует.

## 4. R1–R3 (поставка 01, контракт) — переносится, не блокирует

Подтверждено: fix-коммит контракт не трогает (заявлено автором, сходится с `--stat`). По классификации review-001 все три — minor (в отличие от R4–R6, которые и были основанием RETURN). ACCEPT/вливание фикса они не блокируют. Переносятся как долг поставки 01 в ее же зоне записи: R1 (`requirements_checked` отсутствует в §6 Decision), R2 (`decision_format_version` вне структуры код-блока §10), R3 (§7: полные таблицы только для Флоу 1 при самозаявленном покрытии 1–5 в §15). Рекомендация оркестратору: отдельный docs-фикс поставки 01 до archive change.

---

## Проверенные Scenario спеки (повторно, после фикса)

- «Порядок флоу 1–5»: транзитивность dev_task ✓ (A′/A″), release-факт архивации ✓ (D′), независимые [P] ready ✓ (тест + B′).
- «Разрешение действия»: флаг без evidence → не доверие, а UNKNOWN ✓ (B″/B‴).
- «Честная граница»: UNKNOWN не разрешает — не изменилось (набор регресс-тестов green).
- «Режим shadow»: read-only ✓ (повторная проба).

## Что НЕ проверено (честно)

- `openspec validate --all --strict` — как и в review-001, CLI openspec в среде ревью не установлен; проверяется CI (.github/workflows/flow.yml).
- Интеграция с поставками 04/05 (admit_session, gate runner) — не поставлены; required_gates-ссылки проверены структурно.
- R10 (дубль парсера вердиктов в flow_state) — зона ревью поставки 02, здесь не ревьюился.

## Итог

**APPROVE.** Фикс 72aae6e закрывает R4, R5, R6 (все подтверждены живыми пробами по рецептам review-001) и R7–R9; регрессий нет. Долги вне зоны фикса: R1–R3 → поставка 01 (docs-фикс), R10 → ревью поставки 02. История ревью append-only соблюдена: review-001.md не изменялся.
