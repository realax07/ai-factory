# Скиллы конвейера

Скилл — процедура выполнения типовой задачи по лучшим практикам (гайд Anthropic: imperative form, объяснение «почему», progressive disclosure, запрет нечитаемых предписаний). Скиллы загружаются агентами при выполнении задач (см. таблицу в agents/README.md) и переиспользуются между ролями.

## Реестр

| Скилл | Назначение | Используют |
|---|---|---|
| [requirements-elaboration](roles/requirements-elaboration/) | Elicitation и структурирование ТЗ (IEEE 830/29148, MoSCoW) | БА |
| [openspec-authoring](roles/openspec-authoring/) | Спеки, change-пакеты, SDD по конвенциям Fission-AI | СА |
| [brainstorming](roles/brainstorming/) | Прояснение замысла до требований (альтернативы, anti-scope) | БА |
| [service-decomposition](roles/service-decomposition/) | Границы сервисов, владение схемой БД, сквозные процессы, швы делегаций | СА, dev_lead |
| [test-case-design](roles/test-case-design/) | Тест-кейсы по спеке (без чеклиста, J23): покрытие, границы, трассировка | QA-автор |
| [case-review](roles/case-review/) | Ревью кейсов: оси проверки, серьезности, итерации | QA-ревьюер |
| [implementation](roles/implementation/) | Реализация одной задачи спека с трассировкой и self-review | dev |
| [code-review](roles/code-review/) | Ревью задачного диффа против спеки и стандартов | code_reviewer |
| [test-automation](roles/test-automation/) | Приемочные автотесты по раскладке J66: `tests/api` (requests), `tests/web` (playwright), `tests/integration`; трассировка TC | QA-автоматизатор |
| [playwright-pro](roles/playwright-pro/) | Playwright: golden rules, локаторы, anti-patterns, flaky-таксономия | QA-автоматизатор |
| [handoff](pm-factory/handoff/) | Handoff-документ при завершении/обрыве сессии | ПМ |
| [factory-flow](flow/factory-flow/) | Скелет детерминированного флоу: стадии 5 флоу, карта блокеров, правила эскалации | Все роли (входит во все бандлы) |

## Дизайн-скиллы (зеркало локальной библиотеки, группа `roles-tools/`)

Вендорские/творческие скиллы визуального дизайна. Не процессные процедуры конвейера — дистилляты и инструменты: загружаются ui_designer и design_validator (см. таблицы «Скиллы» в agents/). Обновляются зеркалированием из локальной библиотеки, не правятся в фабрике напрямую.

| Скилл | Назначение | Источник / лицензия |
|---|---|---|
| [frontend-design](roles-tools/frontend-design/) | Эстетическая директория до кода, анти-AI-эстетика, bans/качество-пол для мокапов | Дистиллят anthropics/skills frontend-design + Impeccable (Apache-2.0) |
| [design-review](roles-tools/design-review/) | Ревью UI по трём столпам качества, чек-листы сдачи/приемки, два режима (ревью/создание) | Дистиллят microsoft/skills frontend-design-review (MIT) |
| [ui-ux-matrices](roles-tools/ui-ux-matrices/) | Локальный поиск: стили, палитры, шрифтовые пары, UX-гайдлайны (`scripts/search.py`) | Vendor nextlevelbuilder/ui-ux-pro-max-skill (MIT), скопирован целиком |
| [claude-design](roles-tools/claude-design/) | Дисциплина HTML-мокапов: один файл = самодостаточный артефакт | BadTechBandit (MIT) |
| [design-md](roles-tools/design-md/) | Формализация дизайн-токенов в DESIGN.md spec-файл | — |
| [architecture-diagram](roles-tools/architecture-diagram/) | Темные SVG architecture/cloud-диаграммы как HTML | — |

## Формат скилла

```
skills/<name>/SKILL.md
---
name: <kebab-case>
description: Что делает и когда применять — триггер загрузки.
---
# Заголовок
## Когда применять / Не применять
## Процедура (нумерованные шаги с критериями завершения)
## Формат результата / Примеры
## Ошибки (питфоллы с объяснением почему)
```

## Правила ведения

1. Description — триггер: агент по нему решает, загружать ли скилл. Описывает и «что», и «когда».
2. Один скилл = одна повторяемая процедура. Пошаговые ролные регламенты — в agents/, здесь — техники. Исключение — `factory-flow`: это общий скелет процесса, ролевые секции живут в промптах agents/*.md и ссылаются на него.
3. Объясняй почему: предписание без причины выполняется формально и ломается на первом нестандартном случае.
4. Питфоллы обязательны: раздел «Ошибки» из реальных сбоев, не общие слова.


## Состав библиотеки (чистка 2026-11-05, J64.16)

В репо — только скиллы конвейера и инструменты ролей: группы `roles/`,
`roles-tools/`, `flow/`, `pm-factory/`, `runtimes/` и `engineering/spike`.
Зеркало личной библиотеки ПМ (`creative/`, `office/`, `research/` и
неиспользуемые `engineering/*`, `runtimes/*`) удалено: ни роль-промпты,
ни паки, ни скрипты на них не ссылались. Эталон этих скиллов — локальная
библиотека `~/.hermes/skills/`, история — в git (до коммита чистки).

Каноничность процессных скиллов: **эталон — этот репо** (установщик
обновляет локальные копии). Новый скилл попадает в репо, только если на
него ссылается роль (`agents/*.md`), пак или скрипт.

Исключения и оговорки:
- процессные скиллы фабрики без ссылок (`flow/*-artifact-cleanup`,
  `pm-factory/{ai-factory-flow-control, factory-conveyor-audit}`) пока
  оставлены — их судьба решается отдельно;
- вендорские `roles-tools/{claude-design, design-md, github,
  systematic-debugging}` упоминают удаленные скиллы как related
  (`popular-web-designs`, `test-driven-development`,
  `requesting-code-review`). Вендорские скиллы в фабрике не правятся; в
  Hermes эти скиллы есть в локальной библиотеке, а исполнитель без
  `~/.hermes/skills` (Pi, другой агент) их не найдет.

### Гигиена (2026-10-23)

Фабрика переиспользуема для будущих проектов — в ней только универсальные и
фабричные скиллы. Проектные (ekotov-*) живут в репо проекта (ekotov-wiki,
`skills/project/`), личные (apple/*, weather-report) — только локально в
`~/.hermes/skills/`. При майнинге новых скиллов соблюдать этот расклад.
