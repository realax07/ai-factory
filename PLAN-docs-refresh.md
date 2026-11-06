# PLAN-docs-refresh: актуализация документации фабрики (2026-11-06)

**Флоу: 4** — обслуживание: документация приводится к фактическому состоянию
фабрики после J59–J65; код, спеки, контракты и промпты ролей не меняются.

## Решения Заказчика (2026-11-06, выбор в диалоге)

- AGENTS.md: «Только фактические правки» — устаревшие утверждения, без смены
  правил и структуры; сжатие до ядра остается в J64.15/J65.11.
- Промпты ролей `agents/*_agent.md`: «Не трогать промпты» — расхождения
  выписаны ниже.

## Что исправлено

| Файл | Было | Стало |
|---|---|---|
| README.md | Python ≥3.11 / bootstrap ≥3.10; `@openspec/cli`; исполнитель — Hermes `delegate_task`; «990»/«777 тестов»; нет Флоу 5; канал ПМ-0; битая ссылка на e12-спайк; 2 роль-пака; пилот на Р6 | ≥3.10 (CI 3.12); `@fission-ai/openspec@1.14.0`; Pi + пакетный раннер, ПМ — Hermes или любой кодагент; «более 1200»; Флоу 4 (план + slug) и Флоу 5; единственный канал вотчдога; ссылка в archive/docs; 15 паков; таблица проектов (ekotov-wiki, child_bot, auto-school); строки раннера J63 и новых скриптов (flow_ids, factory_paths, role_zone_policy, ci_local, check_mirrors) |
| AGENTS.md | заголовок энфорсера `change=`; scope Ф2 BUG-NNN / Ф3 incident-id; J60 «кандидат»; flow_check проверяет чеклист; «скрипты ядра на проект не копируются»; «скопируй flow_check и flow.yml» | `flow=…scope=`; грамматика flow_ids; J60 реализован (MODEL_ENFORCE); пункт 7 — раннер J63; границы вотчдога (Pi не видит); factory_init копирует ядро; синхронизация проектов — factory_init/check_mirrors |
| docs/process-context.md | §4 «переход только по „погнали"» (отменено 2026-10-03); нет Pi и путей | режим непрерывного доведения; модели Pi-паков; env путей и doctor; скрипты ядра J62–J65 |
| docs/guarantees.md, docs/ci-gates.md | «405+ тестов»; нет раннера и J60/J42 | 1200+; строки раннера J63, MODEL_ENFORCE, грамматики; принятый риск «вердикт — подстрока»; раздел ci_local |
| docs/README-flow-control.md | в реестре скриптов нет flow_ids, factory_paths, package_runner, ci_local; раннер не описан | строки реестра + раздел «Пакетный раннер Pi (J62/J63)» (замечание ревью BUG-026) |
| docs/agent-succession.md | scope Ф3 incident-id; изменения только через delegate_task; срез 2026-10-14 как текущий | грамматика flow_ids; раннер Pi + delegate_task; срез помечен историческим |
| docs/factory-evolution-stages.md | стадия 2 без фактов после 10-03 | что добавлено после; тега v2.0 нет; критерий — J65.6 |
| docs/chatgpt-deterministic-flow/00-README.md | читается как открытое ТЗ | баннер «реализовано, историческое ТЗ» |
| plugins/README.md | заголовок `change=`; нет грамматики и MODEL_ENFORCE | канонический заголовок, грамматика flow_ids, раздел J60 |
| agents/README.md | (таблица зон не тронута — защищена отпечатком) | вводная строка об исполнителях |
| templates/task_delegation.md | только `delegate_task` | связь с брифом стадии раннера |
| PLAN.md | статус на 2026-10-10 | раздел «Текущее состояние (2026-11-06)»; пометки к устаревшим строкам «Решений» (история не переписана) |
| archive/ | — | PLAN-flow-ids.md, PLAN-dev-tools.md → archive/plans/; README архива |

## Расхождения в промптах ролей (не исправлялись — решение Заказчика)

1. `agents/code_reviewer_agent.md:27` требует вердикт `## Вердикт: approve` +
   `Reviewer-Delegation:`, а пак `code-reviewer` и манифест раннера — строку
   «Вердикт: Одобрить» (подстрока). Согласование — J64.12/J65.4.
2. Пак `code-reviewer` пишет ревью в `test-model/reviews/**`, промпт и
   `pr_validate` (J10) ждут `code-reviews/<change>/` — J64.11 / J65.1.
3. `agents/pm_agent.md` описывает ПМ-сабагента, который не внедряется
   (решение 2026-10-10) — дизайн-артефакт, так и помечен в README.
4. Промпты описывают запуск через `delegate_task`; боевой путь — Pi через
   раннер (паки несут свою выжимку промпта, base-маркеры сверены в J62).

## Манифест

```yaml
pipeline:
  package: docs-refresh
  flow: 4
  stages:
    - id: docs
      run: hermes:pm    # README/AGENTS/docs — зона ПМ (agents/README.md)
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/docs-refresh/review-001.md]
      verdict:
        file: code-reviews/docs-refresh/review-001.md
        contains: "Вердикт: Одобрить"
    - id: merge
      run: hermes:pm
```

## Критерий закрытия

Ссылки в измененных файлах целы, полный сьют (в т.ч. отпечаток таблицы зон)
зеленый, `flow_check` OK, ревью «Одобрить» (сверка утверждений с кодом), CI
зеленый.

## Исполнение

pi на машине исполнителя нет — стадии исполняет внешний агент (Claude Code);
ревью — независимый сабагент.
