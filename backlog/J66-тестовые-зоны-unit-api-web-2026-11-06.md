# J66 — Тестовые зоны: tests/unit · tests/api · tests/web

- **Заявлено:** 2026-11-06, Заказчик («надо чтобы в папке tests зоны были unit/ web/ api/; api — requests python, web — playwright»).
- **Флоу:** 4 (обслуживание фабрики) + зеркальные PR в проекты.
- **Статус:** заявлено, к обсуждению/реализации 2026-11-07.

## Целевая раскладка

| Каталог | Стек | Владелец (предложение) |
|---|---|---|
| `tests/unit/` | pytest, без сети и браузера | dev |
| `tests/api/` | pytest + requests | qa_automation |
| `tests/web/` | pytest + playwright | qa_automation |

## Как сейчас (аудит 2026-11-06)

- `agents/roles.json`: dev → `tests/**`, `e2e/**`, `test-model/bugs/*`; qa_automation → `tests/**`, `test-model/bugs/*`, `pytest.ini`. Зоны совпадают — изоляция автора кода от автора приемочных тестов держится на дисциплине (`[test-adapted]`, dev_agent.md:75).
- `tests/unit/` не упомянут нигде: ни в спеке, ни в промптах, ни в зонах.
- Стек api/web уже есть в спеке `openspec/specs/qa-pipeline/spec.md:51` и в промптах qa_automation (`tests/api/`, `tests/web/`) — словами, не зонами.
- `flowctl regress` (scripts/flowctl.py:1820): frontend → tests/web, backend → tests/api, иное → корень `tests/` (а не tests/unit).
- `pr_validate` J50: UI-дельта требует правок `tests/web/` — совместимо.
- Проекты:
  - auto-school — почти по схеме (unit/api/web), 1 тест в корне (`test_container_contract.py`);
  - ekotov-wiki — api/web, unit нет; в корне 3 теста + 8 `REPORT-*.md`; отдельный `e2e/` (стенд-смоук);
  - child_bot — ~25 тестов плоско в корне `tests/`, подкаталогов нет.
- `tests/smoke_cross/` — поставляется фабрикой (factory_init), вне трех зон.

## Открытые вопросы (обсудить до реализации)

1. **Жесткое или мягкое разделение.** Жесткое: dev только `tests/unit/**`, qa_automation `tests/api/**` + `tests/web/**`; поломанный продуктом api/web-тест чинит qa_automation отдельной делегацией. Мягкое: dev сохраняет api/web, но pr_validate требует `[test-adapted]` на любую его правку там. Предложение — жесткое.
2. **Общие файлы:** `tests/README.md`, корневой `tests/conftest.py`, `pytest.ini`, фикстуры. Предложение: conftest на каталог (unit — dev, api/web — QA), корневые общие — qa_automation.
3. **Трассировка unit-тестов:** спека требует TC-ID в docstring каждого автотеста, а у unit-тестов dev кейсов нет. Предложение: unit ссылается на FR-N / задачу tasks.md, TC-ID — только api/web.
4. **`e2e/**` у dev** (ekotov-wiki: стенд-смоук) — свернуть в `tests/web/`, оставить отдельной зоной или передать integrator/regress_runner.
5. **Проекты без HTTP API и UI** (child_bot — Telegram-бот): всё в unit? Нужен ли интеграционный уровень вне трех зон.
6. **Строгость проверки:** тест в корне `tests/` — сначала WARNING (легаси), затем дефект; срок перехода.
7. **Тесты самой фабрики** (`tests/` плоско, ~1000) — раскладка касается только продуктовых проектов (предложение: фабрику не трогать).

## Состав работ (черновик)

1. Спека qa-pipeline: требование раскладки unit/api/web + стек unit.
2. `agents/roles.json`: зоны dev / qa_automation → `gen_role_docs` (таблицы agents/README, role-packs/README).
3. Промпты и Pi-паки dev, qa_automation (role-agents.md, README манифестов).
4. `flowctl regress`: «иное» → `tests/unit`.
5. `flow_check`: тест в корне `tests/` — WARNING/дефект по п.6.
6. Тесты на всё выше (TC-J66-*).
7. Миграция проектов — отдельными PR: child_bot (основной объем), ekotov-wiki, auto-school.

## Резолюции

- **2026-11-07 — решения Заказчика** по вопросам (варианты дословно):
  разделение — «Жёстко»; проекты без api/web — «Четвёртый каталог»,
  имя — «tests/integration»; `e2e/` — «В tests/web/e2e»; строгость —
  «WARNING, потом ошибка»; тесты фабрики — «Перенести в tests/unit».
  Решения ПМ без развилки: общие `tests/conftest.py`, `tests/README.md`,
  `pytest.ini` — qa_automation; unit-тесты dev без TC-ID; `flowctl regress`
  не меняется («иное» → весь `tests/` шире, чем `tests/unit`, и не теряет
  покрытие `src/`) — п.4 черновика снят.
- **2026-11-07 — фабрика сделана** (PLAN-test-zones.md, Флоу 4): спека
  qa-pipeline (раскладка, проверка, трассировка, стек), контракт 6, зоны
  `agents/roles.json` (dev — `tests/unit/**` без `tests/**` и `e2e/**`;
  qa_automation — `tests/api|web|integration|smoke_cross|archive/**`,
  `tests/conftest.py`, `tests/README.md`), промпты и паки dev и
  qa_automation, примеры манифестов; `flow_check` — раскладка и стек по
  режиму `test-model/test-layout.json` (warn по умолчанию, strict, битый
  файл — ошибка), unit без TC-ID; `factory_init` — smoke в `tests/unit/`,
  режим strict/warn по факту тестов проекта; файл режима — защищенный путь;
  тесты фабрики перенесены в `tests/unit/`, фабрика — strict; TC-J66-001…009.
- **2026-11-07 — возврат ревью review-001** (2 major, 10 minor), исправлено:
  `tests/conftest.py` фабрики оставлен в корне (в `tests/unit/` pytest не
  вызывал `pytest_sessionstart` — сторож дерева J64.1 молча отключался;
  TC-J66-010); развилка Заказчика по Флоу 2–5 — «Этап qa_automation»: этап
  после первого этапа флоу с тем же входом (STAGE_TABLE, SEQUENCE_PREREQS
  enforcer; TC-J66-015); импорты — `ast`; контракт 6 «без кейс-базы» — только
  приемочные тесты; archive — с TC в спеке; factory_init — разбор flow_check;
  guard пака qa-automation сужен до `test-model/bugs`; ничьи
  `tests/__init__.py`, `tests/fixtures/**` — qa_automation; устаревшие
  тексты в skills и qa_case_reviewer; subject коммита с `[pipeline]`.
- **Известное ограничение (review-001 #12):** `flowctl regress` по диффу
  только `backend/` гоняет `tests/api`, только `frontend/` — `tests/web`;
  unit-тесты dev (`tests/unit/`) в доменный регресс не попадают (дефект не
  новый, J66 делает его системным). Добавление `tests/unit` к доменам
  свернет прогон в полный `tests/` (правило дедупа BUG-005) — решать вместе
  с картой доменов J52; кандидат следующей волны.
- **2026-11-07 — review-002: approve** (3 minor): SyntaxWarning при разборе
  `ast` подавлен; этап qa_automation дописан в контракт flow_control
  (Флоу 2–5); правка спеки оформлена change-пакетом и заархивирована
  (`openspec/changes/archive/2026-11-07-test-zones/`, контракт 7).
- **Вне объема (зафиксировано):** корневой `e2e/` вне `tests/` раскладкой не
  проверяется — до миграции ekotov-wiki он вне ворот; PR миграции `e2e/` →
  `tests/web/e2e/` требует явной зоны в брифе ПМ (удаление `e2e/**` — вне
  зон обеих ролей). Прочие `tests/*.md`, кроме README, — без владельца
  (отказ: отчеты прогонов — `test-model/`, не `tests/`).
- **Открыто:** миграция проектов отдельными PR (до нее у них warn):
  child_bot — ~25 тестов из корня в `tests/integration/` (или `tests/unit/`
  для тестов dev); ekotov-wiki — 3 теста из корня, `e2e/` → `tests/web/e2e/`,
  `REPORT-*.md` из корня `tests/` — вне зоны qa_automation (перенос в
  `test-model/` или отчеты в `tests/README.md`); auto-school —
  `test_container_contract.py` из корня. После миграции — `mode: strict` (правка защищенного пути — `[pipeline]` в subject коммита).
  Строка AGENTS.md «Автотесты (`tests/**`)» в таблице роутинга ревью —
  защищенная зона, правка по согласию Заказчика (J65.11).
