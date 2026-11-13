# Review 002: docs-refresh

- Commit: `c74b6e6` (ветка `chore/docs-refresh`; исправления по review-001 поверх `a6e3b62`).
- Ревьюер: независимый сабагент (роль code_reviewer, только статика диффа). Автор исправлений — ПМ-сессия.
- Прогоны:
  - `python3 scripts/flow_check.py .`: OK.
  - `gen_role_docs.py --check`: таблицы актуальны.
  - `pytest tests/unit/test_j65_pack_zone_docs.py test_j65_agents_core.py test_j65_roles_registry.py`: 18 passed.
  - `openspec validate`: SKIPPED, CLI в среде ревьюера нет; openspec/ не тронут.
  - `git status`: `code-reviews/docs-refresh/review-001.md` вернулся к состоянию main (#226).
- Итог: все major из review-001 закрыты. Новых неточностей в правках нет. Остался один minor (частично закрыт).

## Сверка замечаний review-001

| # | Было | Статус | Проверка |
|---|---|---|---|
| M1 | вотчдог без оговорки о паузе крона | закрыто | README.md п.6 и строка «Вотчдоги»: «только при включенном кроне delegate-watchdog (сейчас на паузе)». Совпадает с README-flow-control.md:280 и guarantees.md:37,56. |
| M2 | эталон «Флоу 1… любого звена» | закрыто | README, README-flow-control, ci-gates, guarantees: «Флоу 1 без QA-контура (sa → architect → dev по задачам с парным ревью → gate → merge)», QA — кандидат J65.10b. Совпадает с fixtures/reference-run/README.md и test_j65_reference_run.py:55-59. |
| M3 | pipeline-manifest: модель из settings.example.json | закрыто | pipeline-manifest.md:66-70: roles.json или стадия, иначе MODEL_UNRESOLVED. Совпадает с package_runner.py `role_model`. |
| 4 | Codex без артефакта | закрыто | PLAN.md:33-36 приводит дословно решение Заказчика 2026-11-13. Перечень «Claude Code, Codex, Qwen» совпадает с журналом J65 (claude-code, qwen) и расширяет его по этому решению. |
| 5 | hermes как запускаемый | закрыто | README.md:53-54: «`hermes:` — ручная стоп-точка ПМ, раннер ее не исполняет» (executors/hermes.py `manual = True`). |
| 6 | эталон на `stub:` | частично | README.md:375-379 исправлен верно: `pi:` с подменным `bin/pi`, повтор на `stub:`. Осталось см. замечание 1 ниже. |
| 7 | «Слой 4» | закрыто | guarantees.md:46 → «Слой 3». |
| 8 | «правило 1 + F3» | закрыто | → «AGENTS.md «Оркестрация», приемка + F3». Раздел и пункт приемки есть в текущем ядре. |
| 9 | слой 2a без исполнителей | закрыто | guarantees.md:56 дополнен (executor_watchdog, J65.5). |
| 10 | J66 без артефакта решения | закрыто | PLAN.md:37-38 приводит дословно «J 66 я сделаю с агентами фабрики». MAP ссылается на тот же статус. Резолюцию в backlog/J66 желательно дописать, но это не обязательно. |
| 11 | «Правило 11» в pipeline-manifest | закрыто | pipeline-manifest.md:244 → «Правило 10» (п.10 ядра — одна задача, один dev). |
| 12 | agents/README.md:5 | закрыто | Добавлены `<исполнитель>:<роль>`, `scripts/executors/` и источник модели roles.json. gen_role_docs не задет. |
| 13 | `~/.pi` в README паков | отклонено ПМ | С обоснованием: строки описывают ручные запуски, и для них это верно. role-packs/README.md:14 разводит ручной запуск и раннер. Принимаю. |
| 14 | дата ruleset_check | закрыто | guarantees.md: «ruleset_check.py OK 2026-11-14». |

## Замечания

| # | Серьезность | Файл:строка | Что неверно | Как в коде | Рекомендация |
|---|---|---|---|---|---|
| 1 | minor | README.md:268-269; docs/README-flow-control.md:214 | Осталось «`stub:dev` — заглушка эталонного прогона» и «`stub:` … им же гоняется эталонный прогон». Это противоречит исправленному README.md:375-379. | Основной эталон идет на `pi:` с подменным `bin/pi` (fixtures/reference-run/project/PLAN-add-greeting.md). На `stub:` — только повтор, TC-J65-EXE-008. | «`stub:dev` — исполнитель-команда из `AF_EXECUTOR_STUB_CMD` (повтор эталона)». На вердикт не влияет. |

## Вердикт: approve
