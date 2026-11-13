# Правила AGENTS.md ↔ проверки (J65.11)

Карта для людей и ревью: чем проверяется каждое правило ядра AGENTS.md.
Сабагенты ее не читают (решение Заказчика 2026-11-13 «Отдельный файл»:
AGENTS.md читает ПМ на Hermes, glm-5.3-flash — правила короткие, без
справочных колонок). Номера совпадают с AGENTS.md «Правила»; совпадение
номеров держит тест TC-J65-AGC-002. «Не проверяется» — правило держится на
промпте и приемке ПМ; кандидаты на проверку — в конце.

| № | Правило (кратко) | Чем проверяется (скрипт → код отказа) |
|---|---|---|
| 1 | Работа только при валидном входе | `flowctl prepare` → решение flow_transition: DENY/UNKNOWN (`MISSING_INPUT`, `INVALID_GATE`, `AMBIGUOUS_STATE`), в enforcing подготовка не создается |
| 2 | Передача только файлами | `flowctl finish`: без файла отчета приемка не проводится (`blocked`); остальное — не проверяется |
| 3 | Зеленые ворота перед сдачей | `gate_runner` на finish (scope post_agent/pre_accept: `FAIL`/`ERROR`/`STALE`); CI `.github/workflows/flow.yml` — openspec validate --strict, flow_check |
| 4 | Только своя зона, push только своей ветки | `session_check` reserve/check: `ZONE_CONFLICT`, `ZONE_OUTSIDE_POLICY`, `OUT_OF_ZONE`, `ZONE_POLICY_MISMATCH`; раннер — сверка git diff на finish; zone-guard Pi; flow-enforcer push_gate (`push_denied`); GitHub ruleset main (bypass never) |
| 5 | Противоречие — Заказчику | не проверяется |
| 6 | Трассировка | `flow_check`: тест без TC-ID, раскладка tests/ (J66); `pr_validate`: артефакты по контрактам |
| 7 | История append-only | `gate_runner record-review`: перезапись ревью запрещена; `flow_check`: архив change без слияния дельт; остальное — не проверяется |
| 8 | Сессия заканчивается коммитом | не проверяется |
| 9 | Блок статусов ворот в докладе | не проверяется |
| 10 | Задача = сессия, параллель при непересекающихся зонах | `flowctl prepare --task` (ворота dev_task, зависимости J10: approve-ревью предшественницы); `session_check` `ZONE_CONFLICT`; раннер `per_task` (J64.13) |
| 11 | Worktree на сессию | flow-enforcer: `worktree_missing`, `worktree_gate_unavailable`; раннер создает worktree сам |
| 12 | Скиллы через бандлы | не проверяется |
| 13 | План задачи с `Флоу: N` | flow_transition: `PLAN_RELEASE_MISSING`, `PLAN_FLOW_UNDECLARED` (Флоу 1/2/4) |
| 14 | План релиза до СА | то же: `check_create_change`, `check_dev_task` (транзитивно) |
| 15 | Делегация только через ворота | flow-enforcer (pre_tool_call delegate_task): маркер `flow:`, `flowctl prepare --dry-run`, strict — block; `delegate_watchdog` (BYPASS делегаций Hermes); `executor_watchdog` (BYPASS процесса исполнителя вне резервации, J65.5) |
| 16 | scope по флоу, bypass только дословно | `flow_ids.py` (`FLOW_ID_INVALID`); bypass — лог `flow-enforcer-bypass.log` |
| 17 | Боевые роли — раннером | flow-enforcer MODEL_ENFORCE (J60): `[hermes:<роль>]` для SA/архитектора/DEV/BA — DENY |
| 18 | Решения Заказчика — артефактами | flow_transition: `HUMAN_APPROVAL_REQUIRED` (approval_ref на decision-record) |
| 19 | Режимы и AGENTS.md — только Заказчик | `flow_mode set … --by customer`; защищенные пути (J3): правка AGENTS.md/openspec/contracts без `[pipeline]` — отказ prepare, `pm_bounds_check` |
| 20 | Бэклог после цикла | не проверяется |
| 21 | Внешний агент только через PR | ruleset main; `pr_validate` J10 (approve-ревью с Reviewer-Delegation); provenance — `author_delegation: codex:<id>` |

Разделы «Оркестрация» и «Эскалация»: провенанс ревью — `gate_runner
record-review` (самоприемка — DENY); приемка сессии — `session_archive.py`
(вердикт clean/suspicious/degraded); здоровье сессий — `session_watchdog.py`;
остальное (пинг, heartbeat, ротация, дробление [M]) — не проверяется.

## Исполняемые слои (перенесено из AGENTS.md 2026-11-13)

1. **Движок** — `flowctl` prepare/run/finish (решение flow_transition по
   снимку flow_state), `session_check` (резервация зон), `gate_runner`
   (ворота с digest входов; PASS после нового коммита = STALE; SKIPPED
   обязательного ≠ PASS). Режим enforcing: DENY/UNKNOWN останавливают
   действие; shadow — только прогоны на истории.
2. **Энфорсер** — плагин Hermes `plugins/flow-enforcer/`: каждая делегация
   валидируется до исполнения; fail-closed; режимы `FLOW_ENFORCER_MODE`
   permissive/strict; MODEL_ENFORCE (J60), push_gate (J42), sequence-gate.
3. **Раннер** — `scripts/package_runner.py`: стадии `<исполнитель>:<роль>`
   (J65.5) проходят те же ворота; сверка git diff с зоной, provenance,
   журнал запусков.
4. **Вотчдоги** — `delegate_watchdog` (+ `executor_watchdog`) крон */5:
   обход виден за ~5 минут; канал — только дельта новых инцидентов.
5. **CI и ruleset** — flow.yml (flow_check, pr_validate, openspec strict),
   ruleset main (bypass never); проекты — ворота по `factory.lock` (J65.7).

Принцип: «нельзя + заметят + не засчитают»; инструкция агенту — не
гарантия. Проектные копии ворот ставит `factory_init.py` (без `--force` не
трогает существующее), сверка копий — `check_mirrors.py`.

## Кандидаты на проверку

- п.8, п.20 — коммит сессии и запись в бэклог: проверка «сессия ПМ без
  коммита в PLAN/backlog» по журналу делегаций.
- п.9 — блок статусов ворот в докладе: шаблон отчета ПМ.
- Пинг и heartbeat ПМ — session_watchdog уже ловит часть деградаций.
