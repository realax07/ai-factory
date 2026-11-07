# PLAN-test-zones: тестовые зоны tests/unit · api · web · integration (J66)

**Флоу: 4** — обслуживание фабрики: правило раскладки автотестов и зоны
записи ролей. Правка master-spec qa-pipeline оформлена change-пакетом и
заархивирована в том же PR (`openspec/changes/archive/2026-11-07-test-zones/`,
контракт 7; прецедент d4f0a10); порядок «спека → контракт → промпты»
соблюден внутри пакета.

## Решения Заказчика (2026-11-07)

Ответы на вопросы J66 (диалог сессии ПМ, дословно выбранные варианты):

1. Разделение — «Жёстко»: dev пишет только `tests/unit/**`,
   qa_automation — `tests/api/**`, `tests/web/**`.
2. Проекты без api/web (child_bot) — «Четвёртый каталог»,
   имя — «tests/integration».
3. `e2e/` ekotov-wiki — «В tests/web/e2e»; у dev `e2e/**` из зоны убирается.
4. Строгость — «WARNING, потом ошибка».
5. Тесты фабрики — «Перенести в tests/unit».

Решения ПМ по вопросам без развилки (оглашены Заказчику в докладе):

- общие файлы `tests/conftest.py`, `tests/README.md`, `pytest.ini` —
  qa_automation; свой `conftest.py` в `tests/unit/` — dev;
- трассировка: TC-ID в docstring обязателен для api/web/integration;
  unit-тесты dev — ссылка на FR-N/задачу желательна, машинно не требуется;
- `flowctl regress` не меняется: «иное» → весь `tests/` (включая unit и
  integration) — это шире, чем `tests/unit`, и не теряет покрытие src/.

## Развилка из ревью review-001 (2026-11-07)

Во Флоу 2–5 этапа qa_automation не было — жесткая зона dev оставляла
регрессионный api/web-тест к багу и адаптацию приемочных тестов без
исполнителя. Решение Заказчика — «Этап qa_automation»: во Флоу 2–5 этап
`qa_automation` (роль qa_automation) сразу после первого этапа флоу, вход
тот же (`STAGE_TABLE`, `SEQUENCE_PREREQS` enforcer).

## Целевая раскладка

| Каталог | Стек | Зона |
|---|---|---|
| `tests/unit/` | pytest, без сети и браузера | dev |
| `tests/api/` | pytest + requests | qa_automation |
| `tests/web/` (в т.ч. `tests/web/e2e/`) | pytest + playwright | qa_automation |
| `tests/integration/` | pytest, приемка через сервисный слой без HTTP и браузера | qa_automation |

## Состав изменений

1. **Спека** `openspec/specs/qa-pipeline/spec.md`: требование «Раскладка
   автотестов»; «Трассировка» — TC-ID для api/web/integration;
   «Стек» — unit и integration.
2. **Контракт 6** — пути выхода автоматизатора.
3. **Реестр** `agents/roles.json`: dev — `tests/unit/**` вместо `tests/**`,
   без `e2e/**`; qa_automation — `tests/api/**`, `tests/web/**`,
   `tests/integration/**`, `tests/conftest.py`, `tests/README.md`,
   `tests/*.md`; `gen_role_docs` — таблицы.
4. **Промпты и паки** dev и qa_automation, `agents/README.md`.
5. **`flow_check`**: настройка `test-model/test-layout.json`
   (`{"mode": "warn"|"strict"}`; файла нет — warn). Проверки: тестовый файл
   вне четырех каталогов; импорт `requests`/`playwright` в `tests/unit/`;
   `playwright` в `tests/api/`; web-файл без `playwright`; TC-трассировка
   не требуется в `tests/unit/`. warn — FLOW-WARNING, strict — FLOW-ERROR.
   Битый файл настройки — FLOW-ERROR (не молчаливый дефолт). Импорты —
   разбором `ast` (не регексом). Проверка «web-файл без playwright» снята:
   web-тесты получают `page` фикстурой из conftest и playwright не
   импортируют — проверка дала бы ложные срабатывания.
   Правило контракта 6 «автотесты без кейс-базы» — только приемочные тесты.
6. **`factory_init`**: smoke нового проекта — `tests/unit/test_smoke.py`;
   `test-model/test-layout.json` ставится `strict`, если в проекте нет
   тестов вне раскладки, иначе `warn` (существующий файл не трогается).
7. **Защита**: `test-model/test-layout.json` — PROTECTED_PATHS
   (`pm_bounds_check`, `flow_transition`): смягчение strict → warn —
   решение Заказчика.
8. **Тесты фабрики** → `tests/unit/` (git mv; глубина путей
   `parents[1]` → `parents[2]`); фабрика — `strict`. `tests/conftest.py`
   остается в корне: pytest вызывает `pytest_sessionstart` только у
   conftest, загруженных до сбора (корень `tests/`); в `tests/unit/` сторож
   дерева J64.1 молча отключался (review-001 #1). Цена — правка корневого
   conftest фабрики вне зоны dev (зона qa_automation).
9. Тесты TC-J66-*; бэклог: резолюция J66, MAP.

## Вне объема

- миграция проектов (child_bot, ekotov-wiki, auto-school) — отдельные PR
  в их репозиториях после этого пакета; до миграции у них `warn`;
- исторические ссылки на `tests/test_*.py` в ревью, баг-репортах,
  архивах — append-only, не правятся.

## Внимание при выкатке

- `POLICY_VERSION` (sha256 реестра) меняется: резервации до мержа на
  finish получат `ZONE_POLICY_MISMATCH` — мержить без активных сессий.
- Flow 2 в проектах: регрессионный api/web-тест на баг теперь пишет
  qa_automation (dev — только unit).

## Манифест

```yaml
pipeline:
  package: test-zones
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [scripts/**, tests/unit/**]
      task: J66 раскладка тестов, flow_check, factory_init, перенос тестов фабрики
      gate: python3 -m pytest tests/ -q
    - id: docs
      run: hermes:pm    # спека, контракт, roles.json, промпты, перенос tests/ → tests/unit/ — вне зоны dev
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      verdict:
        file: code-reviews/test-zones/review-001.md
    - id: merge
      run: hermes:pm
```

## Критерий закрытия

Полный сьют зеленый, `openspec validate --all --strict` и
`gen_role_docs --check` OK, `flow_check` фабрики без FLOW-WARNING по
раскладке, ревью «approve», CI зеленый; резолюция J66 в бэклоге.

## Исполнение

Внешний агент (Claude Code); ревью — независимый сабагент.
