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
