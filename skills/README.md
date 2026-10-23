# Скиллы конвейера

Скилл — процедура выполнения типовой задачи по лучшим практикам (гайд Anthropic: imperative form, объяснение «почему», progressive disclosure, запрет нечитаемых предписаний). Скиллы загружаются агентами при выполнении задач (см. таблицу в agents/README.md) и переиспользуются между ролями.

## Реестр

| Скилл | Назначение | Используют |
|---|---|---|
| [requirements-elaboration](requirements-elaboration/) | Elicitation и структурирование ТЗ (IEEE 830/29148, MoSCoW) | БА |
| [openspec-authoring](openspec-authoring/) | Спеки, change-пакеты, SDD по конвенциям Fission-AI | СА |
| [brainstorming](brainstorming/) | Прояснение замысла до требований (альтернативы, anti-scope) | БА |
| [service-decomposition](service-decomposition/) | Границы сервисов, владение схемой БД, сквозные процессы, швы делегаций | СА, dev_lead |
| [test-case-design](test-case-design/) | Чеклисты и тест-кейсы: покрытие, границы, трассировка | QA-чеклисты, QA-автор |
| [case-review](case-review/) | Ревью кейсов: оси проверки, серьезности, итерации | QA-ревьюер |
| [test-automation](test-automation/) | Автотесты pytest/requests/playwright с трассировкой | QA-автоматизатор |
| [playwright-pro](playwright-pro/) | Playwright: golden rules, локаторы, anti-patterns, flaky-таксономия | QA-автоматизатор |
| [handoff](handoff/) | Handoff-документ при завершении/обрыве сессии | ПМ |
| [factory-flow](factory-flow/) | Скелет детерминированного флоу: стадии 5 флоу, карта блокеров, правила эскалации | Все роли (входит во все бандлы) |

## Дизайн-скиллы (зеркало `~/.hermes/skills/creative/`)

Вендорские/творческие скиллы визуального дизайна. Не процессные процедуры конвейера — дистилляты и инструменты: загружаются ui_designer и design_validator (см. таблицы «Скиллы» в agents/). Обновляются зеркалированием из локальной библиотеки, не правятся в фабрике напрямую.

| Скилл | Назначение | Источник / лицензия |
|---|---|---|
| [frontend-design](frontend-design/) | Эстетическая директория до кода, анти-AI-эстетика, bans/качество-пол для мокапов | Дистиллят anthropics/skills frontend-design + Impeccable (Apache-2.0) |
| [design-review](design-review/) | Ревью UI по трём столпам качества, чек-листы сдачи/приемки, два режима (ревью/создание) | Дистиллят microsoft/skills frontend-design-review (MIT) |
| [ui-ux-matrices](ui-ux-matrices/) | Локальный поиск: стили, палитры, шрифтовые пары, UX-гайдлайны (`scripts/search.py`) | Vendor nextlevelbuilder/ui-ux-pro-max-skill (MIT), скопирован целиком |
| [claude-design](claude-design/) | Дисциплина HTML-мокапов: один файл = самодостаточный артефакт | BadTechBandit (MIT) |
| [popular-web-designs](popular-web-designs/) | 54 реальных дизайн-системы (Stripe, Linear, Vercel) как HTML-референсы | — |
| [baoyu-infographic](baoyu-infographic/) | Инфографика: 21 макет × 21 стиль, layout/style-референсы | — |
| [design-md](design-md/) | Формализация дизайн-токенов в DESIGN.md spec-файл | — |
| [p5js](p5js/) | p5.js скетчи: генеративка, шейдеры, интерактив, 3D | — |
| [architecture-diagram](architecture-diagram/) | Темные SVG architecture/cloud-диаграммы как HTML | — |

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


## Полная библиотека (зеркало локальной, 2026-10-23)

Помимо процессных скиллов конвейера (выше), в репо зеркалируется полная локальная
библиотека скиллов ПМ по категориям: `creative/` (дизайн, визуал), `devops/`
(эксплуатация фабрики и проектов), `productivity/`, `software-development/`,
`research/`, `autonomous-ai-agents/`, `email/`, `media/`, `note-taking/`,
`social-media/`, `web/`, `apple/`, а также `ekotov-factory-pipeline` и
`skill-repo-mining`.

Каноничность: **эталон процессных скиллов — этот репо** (установщик обновляет
локальные копии); **эталон категорийных — локальная библиотека** (правки входят
через PR сюда же). Рассинхрон ловится сверкой `find skills -name SKILL.md`
между репо и `~/.hermes/skills`.
