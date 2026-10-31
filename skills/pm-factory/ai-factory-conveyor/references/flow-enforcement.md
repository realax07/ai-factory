# Flow enforcement: план релиза, энфорсер делегаций, память фазы (J41/J43)

## План релиза — обязательный артефакт (J41)

PLAN-файл (легальные пути: `PLAN-<id>.md` в корне или `PLAN.md` в каталоге
пакета) пишет ПМ ДО запуска СА; внутри — строка `Флоу: N` (N 1–5).
Ворота `flowctl prepare` этапов create_change/dev_task возвращают
PLAN_RELEASE_MISSING / PLAN_FLOW_UNDECLARED.

Матрица по флоу: Ф1 — PLAN обязателен; Ф2 — `PLAN-<BUG-NNN>.md` в корне ИЛИ
общий `test-model/bugs/PLAN.md` (строка «Флоу: 2»); Ф3 — incident_ref (без
плана — хотфикс против секунд); Ф4 — `PLAN-<slug>.md`; Ф5 — без плана.

## Энфорсер делегаций (плагин flow-enforcer, J43)

pre_tool_call-хук Hermes валидирует КАЖДЫЙ delegate_task ДО исполнения через
`flowctl prepare --dry-run` (только чтение вердикта — резервы зон остаются
штатному prepare ПМ, иначе гарантированный ZONE_CONFLICT).

Конвейерная делегация обязана нести первую строку goal:

    flow: flow=<1-5> role=<роль> repo=<путь> scope=<идентификатор>

scope по флоу: Ф1 change-id; Ф2 BUG-NNN; Ф3 incident-id; Ф4 chore-slug; Ф5
slug. Легаси `change=` без `flow=` → трактовка Ф1 + WARNING. Ошибки маркера →
block FLOW_MARKER_INVALID.

Режимы `FLOW_ENFORCER_MODE`: permissive (дефолт; без маркеров — пропуск+лог
`~/.hermes/state/flow-enforcer.log`) / strict (block MARKERS_MISSING).
Bypass — только дословно `flow: bypass --by customer` (+ запись в
flow-enforcer-bypass.log). Fail-closed двойной: собственный catch-all +
платформенный таймаут хука.

## Память фазы и порядок этапов (J43.1)

`flowctl phase --repo R --project P --flow N --scope S` → JSON последнего
завершенного этапа scope ({action, actor_role, finished_status, timestamp})
или {phase: "none"}. Sequence-gate (`FLOW_ENFORCER_SEQUENCE=1`, дефолт off)
после prepare-ALLOW сверяет запрошенное действие с SEQUENCE_PREREQS
(производная STAGE_TABLE): нарушение порядка → block SEQUENCE_VIOLATION;
return-вердикт ревью легален (доработка). Недоступность phase → WARNING,
fail-open только у этой опциональной проверки.

## Латентность и установка

prepare --dry-run на fixture-репо: ~0.17s (WARNING в логе при >10s).
Установка: factory_init (копия в `~/.hermes/plugins/flow-enforcer/` +
`plugins.enabled`) или `hermes plugins install realax07/ai-factory --ref
<pin>`; плагин переживает обновления агента (каталоги раздельные); правка
плагина = защищенная зона профиля, требует согласия Заказчика.