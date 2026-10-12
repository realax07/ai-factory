# plugins/ — плагин flow-enforcer (J43)

`pre_tool_call`-энфорсер делегаций: делегация `delegate_task` мимо конвейера
становится невозможной без видимого отключения плагина. Источник плагина —
репозиторий фабрики (этот каталог); установка — штатный git-механизм Hermes.

## Как ставить

Вариант 1 — штатный (пин к коммиту, обновления только по явному new-pin):

```bash
hermes plugins install realax07/ai-factory --ref <40-char commit SHA>
# затем ответить 'y' на Enable или:
hermes plugins enable flow-enforcer
```

Вариант 2 — при развертывании конвейера в проект:

```bash
python3 scripts/factory_init.py --target <repo> --name "<проект>"
# копирует plugins/flow-enforcer/ в ~/.hermes/plugins/flow-enforcer/
# и добавляет 'flow-enforcer' в существующий блок plugins.enabled
# config.yaml (нет блока — печатает инструкцию, не правит).
# Отключить шаг: --skip-plugin.
```

## Как включить / выключить

Плагины Hermes opt-in: активен только тот, чье имя в `plugins.enabled`
`~/.hermes/config.yaml` (или `hermes plugins enable flow-enforcer`).
Отключение = явное действие (правка защищенного файла профиля) — это
осознанный обход ворот, фиксируемый в истории файла.

## Режимы (env `FLOW_ENFORCER_MODE`)

- `permissive` (дефолт) — делегация без маркеров ПРОПУСКАЕТСЯ, факт
  пишется в лог (аудит-след, не блокировка);
- `strict` — делегация без маркеров блокируется с кодом `MARKERS_MISSING`.

Прочие env: `AI_FACTORY_HOME` (путь к фабрике, дефолт `~/ai-factory`),
`FLOW_ENFORCER_REGISTRY` (--registry для flowctl), `FLOW_ENFORCER_FLOW`
(дефолт 1), `FLOW_ENFORCER_STATE_DIR` (каталог логов, дефолт
`~/.hermes/state`).

## Формат заголовка goal (обязателен для конвейерных делегаций)

Первая строка goal (см. templates/task_delegation.md, чеклист 0):

```
flow: role=<роль> repo=<путь> change=<id>
task: <id задачи tasks.md>        # опционально, для dev_task
```

Роль → действие ворот (flowctl): dev→dev_task, sa→create_change,
code_reviewer→code_review, qa_automation→qa_automation, ...

Одиночные маркеры `role: X` / `repo: P` / `change: C` в goal/context тоже
распознаются (fallback, если заголовка нет).

## Bypass

Дословная строка в goal: `flow: bypass --by customer` — явное распоряжение
Заказчика. Делегация пропускается, факт пишется в incident-файл
`~/.hermes/state/flow-enforcer-bypass.log` (timestamp, task_id, первые 200
символов goal). Любой другой «bypass» не распознается.

## Что логируется

`~/.hermes/state/flow-enforcer.log` (JSONL): каждое зафиксированное
`delegate_task`, вердикт prepare (rc, длительность, роль/repo/change),
permissive-пропуски без маркеров, bypass, WARNING при prepare дольше 10с
(замер латентности на fixture: ~0.2s).

## Механика (кратко)

Хук `pre_tool_call` срабатывает только на `delegate_task`; валидация —
`flowctl prepare --dry-run` (без side effects: reservation/goal создает
штатный prepare ПМ, энфорсер только проверяет решение ворот). Код 0 →
делегация идет; ненулевой → block с выводом ворот (machine-коды
PLAN_RELEASE_MISSING, ZONE_*, REQUIREMENTS_NOT_APPROVED, ...). Любое
исключение в хуке → fail-closed block (`flow-enforcer internal error: ...
(fail-closed)`); платформенный таймаут тоже fail-closed (docs hooks.md
§pre_tool_call).
