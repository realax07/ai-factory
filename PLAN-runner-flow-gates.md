# PLAN-runner-flow-gates: ворота flowctl в package_runner

Флоу: 4 — обслуживание фабрики (chore): меняется исполняемый слой
(`scripts/package_runner.py`) и гайд манифеста; спеки конвейера, контракты и
политика зон не меняются. Код продукта проектов не затрагивается.

## Цель

pi-стадии раннера проходят тот же жизненный цикл ворот, что и делегации
через `delegate_task`: решение `flowctl prepare` (план релиза, требования,
политика зон роли, ZONE_CONFLICT), `run`, приемку `finish` по фактическому
git diff и гейтам этапа. До этой правки раннер вызывал `pi` в обход ворот:
`flowctl.py не зависит от этого скрипта` — движок (DENY на входе) для
основного пути исполнения 5.3-ролей (J59) не работал.

Источник: аудит Pi-миграции 2026-11-02 (внешний агент Claude Code), решение
Заказчика в диалоге «Да, начни с ворот».

## Состав изменений

1. `package_runner.py`, pi-стадия роли с этапом в STAGE_TABLE своего флоу:
   `flowctl prepare --worktree <wt> --path <зоны>` → `flowctl run` → pi →
   `flowctl finish --gate-scope post_agent` → коммит стадии в ветку пакета →
   закрытие резервации (finished → closed). DENY/UNKNOWN/returned/blocked —
   STOP с кодом причины (optional-стадия — skipped, резервация освобождается).
2. Роль без этапа во флоу (ba, devops вне Ф3, regress_runner): решение
   flowctl не выносится — только резервация зоны по политике роли и
   post-check диффа (session_check), WARNING `ROLE_WITHOUT_STAGE`. Роль вне
   политики зон (debug, auditor) — STOP `ZONE_OUTSIDE_POLICY` (расширение
   политики — решение Заказчика, agents/README.md).
3. Ролевой AGENTS-файл раннера удаляется из worktree до приемки (не попадает
   в дифф/коммит стадии); SESSION.md не коммитится.
4. PI_ZONE_WRITE: зона политики с glob в середине (`code-reviews/*/review-*.md`)
   → конкретный префикс (`code-reviews`) — guard грубый, точная проверка —
   session_check по диффу.
5. Манифест: необязательные ключи стадии `action` (этап STAGE_TABLE, если
   роль участвует в нескольких) и `task_id` (→ `--task`).
6. Мини-парсер YAML раннера срезает комментарии в конце строки (паритет с
   yaml.safe_load): полный пример Флоу 1 гайда до этого не разбирался.
7. Гайд `docs/guides/pipeline-manifest.md`: зоны примера Флоу 1 приведены к
   политике зон ролей (10 из 13 стадий примера получили бы
   ZONE_OUTSIDE_POLICY), раздел «Ворота pi-стадии».

## Порядок работ

dev (внешний агент) → тесты `tests/test_package_runner.py` (TC-PR-035…) →
полный сьют → PR → ревью Заказчиком (code_reviewer для `scripts/`, G7).

## Развилки Заказчика

- Расширение политики зон на роли debug/auditor и выравнивание зон пак-README
  с политикой (code-reviewer пишет в `test-model/reviews/`, политика и
  pr_validate J10 — `code-reviews/`) — отдельной задачей, правка
  agents/README.md (защищенная зона).

## План прогонов

`pytest tests/test_package_runner.py`, затем `pytest tests/` (база до правки:
1082 passed, 2 skipped).

## Критерий закрытия

Все pi-стадии раннера видны в реестре сессий; DENY prepare, выход за зону и
красный flow_check останавливают пакет; полный сьют зеленый.
