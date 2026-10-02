# Сценарий shadow-сверки 4.2 (add-deterministic-flow)

Цель: сравнить решения flow_transition с фактически принятыми решениями ПМ на
истории Р6 (ekotov-wiki). Режим shadow — только наблюдение, файлы не меняются.

## Точки сверки (реальные решения ПМ/роли за Р6, с коммитами)

| № | Решение (факт) | action/role/flow | Ожидание от машины |
|---|---|---|---|
| S1 | Старт change add-r6-task-form-ux после утверждения ТЗ (0eedae4^) | create_change / sa / 1 | ALLOW при наличии решения Заказчика в approval_ref; без него DENY/HUMAN_APPROVAL_REQUIRED |
| S2 | dev 2.1+2.2 (комбобокс) после 1.1 (60946f6) | dev_task / dev / 1, task 2.1 | ALLOW (spec + sdd + arch review зафиксированы), или честный список недостающих фактов |
| S3 | fix 2.1/2.2 по ревью (60eaa94) | dev_task / dev / 1 (возврат) | ALLOW как доработка после RETURN, evidence: review-файл |
| S4 | accept_review волны 2 (6a6cbb4, fix review-001) | accept_review / code_reviewer / 1 | UNKNOWN/STALE_EVIDENCE (compat) — provenance до поставки 05 |
| S5 | QA-контур 5.1 (fc41b90: impact+чеклист+кейсы+автотесты одним контуром) | qa_case_author / qa / 1 | ALLOW только после approved кейсов… (порядок QA), иначе INVALID_GATE |
| S6 | Релиз 5.2+5.3 (1c9eb4d: бамп static_v + регресс) | release / pm / 1 | DENY/HUMAN_APPROVAL_REQUIRED без зафиксированного решения; gates: полный регресс |
| S7 | Архивация (f925a57, контракт 7) | archive / sa / 1 | ALLOW при слитых дельтах; INVALID_GATE если дельты не слиты |
| S8 | Деплой (4908fe3) | deploy/rollback / pm / 1 | EXTERNAL_ENFORCEMENT_UNKNOWN + полномочия |

## Метод

Для каждой точки: собрать snapshot на соответствующем коммите (git checkout в
detached HEAD на КОПИИ репо — не на живом ekotov-wiki; или --repo на копию),
выполнить check с --json, зафиксировать decision; сравнить с колонкой «Ожидание»
и с фактом (что реально было сделано). Расхождения классифицировать:
ложный запрет (машина DENY, ПМ сделал и это было правильно), ложное разрешение,
честный UNKNOWN (правило текстовое).

Результат — таблица в этом файле (ниже, append) + вывод в отчет 4.4.

## Результаты (прогон 2026-10-02, копия /tmp/shadow-r6/ekotov-wiki, ai-factory@53c13a0)

Метод исполнения: в копии `git checkout <sha>` (detached), `flow_state.py inspect` +
`flow_transition.py check --json` с параметрами из сценария. Роль/ action — из
таблицы этапов Флоу 1 (flow_transition.py STAGE_TABLE); там, где имена из сценария
отличаются от графа (qa_case_author, deploy/rollback), прогонялись оба варианта.

| Точка | sha (срез) | action/role/flow | decision машины | Факт (ПМ) | Вердикт | Классификация расхождения |
|---|---|---|---|---|---|---|
| S1 | 0eedae4^ (=088fd1c) | create_change / sa / 1 | с approval_ref: **ALLOW** (requirements.status=approved); без: **DENY** (HUMAN_APPROVAL_REQUIRED) | пакет создан c604505 по принятому ТЗ (67cbc6f), ОВ-1…ОВ-4 в proposal | **совпал** | — |
| S2 | 60946f6 | dev_task / dev / 1, task 2.1 | **ALLOW** (package+deltas+sdd+approved requirements, зоны) | dev сделал 2.1+2.2; коммит ПМ (WIP, лимит итераций) | **совпал** | — (коммит за dev — нарушение J вне поля машины, не decision) |
| S3 | 60eaa94 | dev_task / dev / 1 (возврат), task 2.1 | **ALLOW** | fix по review deleg_a63de084 | **совпал** | замечание: evidence «review-файл» машина не требует (tasks.md всё еще [ ] — цикл RETURN ей невидим); решение совпадает, требование слабее сценария |
| S4 | 6a6cbb4 | accept_review / code_reviewer / 1 | **UNKNOWN** (STALE_EVIDENCE, compatibility mode до поставки 05) | fix review-001 принят, волна 2 слита (1807082) | **совпал** | честный UNKNOWN (правило текстовое, как и ожидал сценарий) |
| S5 | fc41b90 | qa-контур 5.1; имена сценария qa_case_author/qa **не входят в граф** (MISSING_INPUT); графовые qa_cases/qa_checklist/qa_review/**qa_automation** (roles qa_author/qa_checklist/qa_case_reviewer/qa_automation) — все **ALLOW** | весь контур одним коммитом: impact+чеклист+3 кейса (test-model/new/) + автотесты одновременно; test-model/approved/add-r6-task-form-ux/ пуст | **РАСХОЖДЕНИЕ** | **ложное разрешение**: qa_automation ALLOW, хотя approved-кейсов для r6 нет — `_test_model_sub` проверяет глобальную непустоту test-model/approved/ (там лежат старые пакеты), а не наличие approved-кейсов этого change; порядок QA «кейсы → ревью → approved → автоматизация» не подтверждается. Плюс номенклатурное: ролевые имена практики (qa_case_author/qa) вне графа §7 |
| S6 | 1c9eb4d | release / pm / 1 | **DENY**: HUMAN_APPROVAL_REQUIRED (без approval_ref); даже с approval_ref — DENY: INVALID_GATE «архивация не завершена (open=10), release gate после archive» + MISSING_INPUT (факт change.archived не строится в срезе 1) + EXTERNAL_ENFORCEMENT_UNKNOWN | релиз 5.2+5.3 сделан 07:09, архивация f925a57 — 07:19 (релиз ДО архивации), задеплоен 4908fe3 | **частично** | статус DENY совпал с ожиданием сценария, но причина машинная шире: запрет порядка «release до archive» противоречит фактической принятой практике Р6 → **ложный запрет** (относительно практики) в части INVALID_GATE; недостающий факт archive_change — честный UNKNOWN |
| S7 | f925a57 (+контроль 5d74d11) | archive_change / sa / 1 (факт — sa); графовые роли dev_lead/integrator | на f925a57: **DENY** — WRONG_ROLE (sa ∉ {dev_lead, integrator}) + MISSING_INPUT (change.tasks отсутствует: пакет уже перемещен в archive, snapshot пост-фактум слеп); на 5d74d11 (до перемещения): **ALLOW** при approval_ref, без него UNKNOWN | sa заархивировал f925a57, validate 13/13 strict green, дельты слиты | **РАСХОЖДЕНИЕ** | **ложный запрет** по роли (архивацию реально и корректно делал sa; роль в графе — dev_lead/integrator) + слепая зона снапшота: на самом коммите архивации проверка невозможна (пакет уже перемещен) — контроль проведен на шаге раньше |
| S8 | 4908fe3 | deploy/rollback: во Флоу 1 **действия нет в графе** (MISSING_INPUT); во Флоу 3 (deploy_rollback/pm, change→BUG-000): **DENY** (HUMAN_APPROVAL_REQUIRED + EXTERNAL_ENFORCEMENT_UNKNOWN); с approval_ref → **UNKNOWN**, единственный блокер EXTERNAL_ENFORCEMENT_UNKNOWN | деплой выполнен ПМ (EXPECTED_COMMIT→1c9eb4d), static_v=r6.0 verified на проде | **совпал** (с оговоркой) | честный UNKNOWN + внешние полномочия — как ожидал сценарий; но проверяемо только через Флоу 3 с BUG-NNN-скоупом: в графе Флоу 1 деплоя нет — discoverability нулевая |

### Сводка

- Совпало: S1, S2, S3, S4, S8 (5/8; S6 — частично).
- **Ложное разрешение (1): S5** — проверка QA-порядка глобальна по каталогам test-model, не по change; автоматизация разрешена без approved-кейсов этого пакета.
- **Ложный запрет (2): S6 (частично, INVALID_GATE release-после-archive против практики), S7 (роль sa на архивации + пост-фактум слепой снапшот)**.
- Честный UNKNOWN (правило текстовое): S4 (provenance, по дизайну), S6/S8 (факт archive/внешние полномочия).
- Номенклатурные расхождения графа и практики: qa_case_author/qa и deploy/rollback не входят в Флоу 1; архивация по графу — не sa.
- Гигиеническое наблюдение вне решений: релиз-коммит предшествует архивации (1c9eb4d → f925a57), деплой-коммит (4908fe3, 07:10) — между ними; машина такой порядок запретила бы.

Живой репозиторий /home/openclaw/ekotov-wiki не затронут (git status чист), все прогоны — на копии /tmp/shadow-r6/ekotov-wiki.
