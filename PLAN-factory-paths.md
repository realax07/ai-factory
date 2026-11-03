# PLAN-factory-paths: единый модуль путей машины (J64.5)

**Флоу: 4** — обслуживание фабрики: исполняемый слой (скрипты, энфорсер),
спеки и контракты не меняются.

## Цель

Фабрика должна переезжать на другую машину или под другого исполнителя без
правки кода (вводная Заказчика: «Проект должен быть гибким, и заменяемым»).
До правки пути машины были прошиты примерно в 50 местах 16 файлов:
`Path.home() / ".hermes"`, `/home/openclaw/...` (chat_degrade_watchdog),
`~/ai-factory/agents` (flow_check), `~/.pi/agent/...` (раннер), а env
стенда пилота `EKOTOV_WIKI_*` — в фабричном раннере.

## Состав изменений

- `scripts/factory_paths.py` — единственный источник путей: `state_dir()`
  (AF_STATE_DIR), `hermes_home()` (HERMES_HOME), `factory_home()`
  (AI_FACTORY_HOME), `projects_root()` (AF_PROJECTS_ROOT), `pi_agent_dir()`
  (PI_AGENT_DIR); дефолты = прежние пути (на VPS без env ничего не меняется).
- 15 скриптов переведены на модуль; энфорсер (ставится копией в Hermes,
  модуль не импортирует) — зеркало тех же env/дефолтов, паритет — тест.
- `factory_init`: `factory_paths.py` в COPY_FILES (копии скриптов в проектах
  его импортируют).
- Раннер: срезаемый env стенда — ключ манифеста `pipeline.gate_env_strip`
  (дефолт — список пилота, `[]` — не срезать).
- Документация: README «Пути машины», гайд манифеста.

## Манифест

```yaml
pipeline:
  package: factory-paths
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [scripts/**, tests/**, plugins/**]
      inputs: [backlog/J64-ТЗ-по-итогам-аудита-2026-11-02.md]
      task: J64.5 — factory_paths.py, перевод скриптов, gate_env_strip, тесты
    - id: docs
      run: hermes:pm    # README.md, docs/ — зона ПМ
    - id: check
      run: gate:python3 -m pytest tests/ -q
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/factory-paths/review-001.md]
      verdict:
        file: code-reviews/factory-paths/review-001.md
        contains: "Вердикт: Одобрить"
    - id: merge
      run: hermes:pm
```

Исполнение: pi на машине исполнителя нет — стадии исполняет внешний агент
(Claude Code), ревью — независимый сабагент.

## Критерий закрытия

Тест `test_no_hardcoded_machine_paths` зеленый (в scripts/ и plugins/ нет
прошитых путей машины, кроме factory_paths и зеркала энфорсера); каждая
переменная переопределяет свой путь; сьют зеленый.

## Внимание при выкатке

`HERMES_HOME` раньше учитывали только bootstrap/init; теперь — все скрипты.
Если на VPS `HERMES_HOME` задан не на `~/.hermes`, вотчдоги и ворота начнут
читать оттуда — сверить `python3 scripts/factory_paths.py` до мержа.
