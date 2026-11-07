# Review-002: установщики фабрики (chore/installers), повторное ревью

Commit: 4bd99df10c13ad42064385aa50f94077b9c14d02 (исправления по review-001 поверх 6b9f01f)
Диф: `git diff 6b9f01f 4bd99df`. Ревьюер — независимый сабагент (Claude Code), автор
кода — другой агент; файлы репо не правил.

Проверено прогоном (scratchpad):
- `test_installers.py` + `test_j58_impact_gate.py` + `test_factory_paths.py` — 61 passed;
  `test_installers.py` + `test_flow_mode_integration.py` — 30 passed;
- репро review-001 (`openspec/changes/_x/` с proposal.md и дельтой) — снова 5 FLOW-ERROR;
- голый `openspec/changes/_template/impact.md` — FLOW-WARNING «легаси-шаблон» и OK.

## Закрытие находок review-001

| # | Было | Статус | Подтверждение |
|---|---|---|---|
| 1 | major: flow_check пропускал любой `_*` | закрыта | flow_check.py:475-481 `is_legacy_impact_template` — только `_template`, где единственный файл `impact.md`; иначе каталог идет через все проверки (kebab-case, контракты 1/2, J10). Репро `_x` — FLOW-ERROR; TC-INST-006 покрывает три случая (голый шаблон, `_template` с дельтой, `_x`) |
| 2 | minor: флаг понижал enforcing молча | закрыта | factory_bootstrap.py:129-132 — WARN при enforcing → shadow с командой возврата; тест проверяет текст |
| 3 | minor: reload протекал в сьют | закрыта (с оговоркой, nit A) | фикстура `bootstrap_env`: сохранение/восстановление env и повторный reload в teardown |
| 4 | minor: TC-INST-005 без rc | закрыта | rc 0 либо 1 только при «openspec CLI: НЕ найден»; плюс проверка места шаблона |
| 5 | minor: python<3.10 недостижим | закрыта | `from __future__ import annotations` |
| 6 | minor: таймаут = MISSING | закрыта (с оговоркой, nit B) | `_run` → 124 «timeout», check_env печатает WARN «не ответил за 60s» |
| 7 | minor: устаревший комментарий | закрыта | factory_init.py:616 |
| 8 | minor: скилл/process-context | закрыта | references/flow-control.md:8, process-context.md:15 — обертки Hermes, */5 |
| 9 | minor: «Hermes не найден» без подсказки | закрыта | bootstrap и init: «поставишь Hermes — перезапусти …» |
| 10 | minor: «шаг 2» в README | закрыта | «(см. «Шаг 2»)» |

## Новые замечания

| # | Серьезность | Где | Что не так | Рекомендация |
|---|---|---|---|---|
| A | minor (nit) | tests/unit/test_installers.py:43-70 | Teardown-reload идет при env теста (HOME от autouse `isolated_home` еще подменен, AF_STATE_DIR снят), поэтому `flow_mode.DEFAULT_MODE_FILE` после теста указывает в HOME этого теста, а не в сессионный HOME, как до первого reload. Файла там нет — `get_mode()` = shadow, поведение то же. Остаточная утечка, но безвредная. | При желании — запомнить `flow_mode.DEFAULT_MODE_FILE`/`_STATE_DIR` до теста и вернуть `setattr`-ом вместо повторного reload. |
| B | minor (nit) | scripts/factory_bootstrap.py:106-108 | Таймаут обязательного инструмента (git/node/npm/openspec) — WARN и `continue`, `ok` не сбрасывается: зависший openspec не мешает итоговому OK. | Для `required` при rc 124 — `ok = False` (или явно оговорить в доке, что таймаут не блокирует). |
| C | minor (nit) | scripts/flow_check.py:479-481 | Сравниваются только имена файлов из `rglob`: `_template/sub/impact.md` тоже считается шаблоном. Дельт там нет, обхода контрактов это не дает. | Сравнивать относительный путь (`p.relative_to(d) == Path("impact.md")`). |

Регрессий не найдено: `warns` определен в модуле (flow_check.py:490) до вызова в check(),
поведение bootstrap/init вне затронутых веток не менялось.

## Вердикт: approve
