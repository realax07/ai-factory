---
name: flow-playbooks
description: "Use when cutting tasks.md or running Флоу 1-5 packages."
version: 1.0.0
author: Егор Котов (realax07), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [ai-factory, ekotov-wiki, flow-control, qa, planning]
---

# Playbooks флоу: нарезка пакетов и обязательный QA-контур

Когда: СА режет tasks.md нового пакета, ПМ планирует этапы, ПМ принимает возвраты (return ревьюера, баги QA-раннеров). Скилл закрывает инцидент add-wiki (J39): QA-артефактный контур выпал из плана пакета — ворота поймали только на финальном PR, кейсы писались задним числом от кода.

## Правило выбора файла

Флоу объявляется ПМ до старта пакета (памятка ПМ п.2). СА при нарезке читает файл СВОЕГО флоу в каталоге `references/flows/` этого скилла: `flow-1-full.md` (полный: БА → СА → дизайн → dev → QA → приемка), `flow-2-bugfix.md`, `flow-3-hotfix.md`, `flow-4-maintenance.md`, `flow-5-express.md`. Общие правила (ворота, маркеры PR, зоны, возвраты) — в этом SKILL.md; специфика флоу — в его файле. Чужие файлы флоу не читать — они про другой цикл.

## Обязательные задачи tasks.md при нарезке (Флоу 1, пакеты с дельтами)

Эталон нарезки — add-responsive-mobile: impact → чеклист → кейсы → ревью кейсов → автотесты. Пакет Флоу 1 ОБЯЗАН содержать (или в явном QA-этапе):

1. `[tests] qa_impact_analysis` — impact-анализ (`test-model/impact/<id>.md`) при MODIFIED/REMOVED дельтах (H5).
2. `[tests] qa_checklist` — чеклист (`test-model/checklists/<id>.md`) — статус по J23 (кандидат на упразднение; пока этап существует — задача обязательна).
3. `[tests] qa_author` + `[tests] qa_case_reviewer` — кейсы (`test-model/new/` → `approved/`) с независимым ревью.
4. `[tests] qa_automation` — автотесты/прогон по наборам, TC-ID в каждом тесте (`TC-<change>-NNN`, правило 6 flow_check).

Нарезка ДОЛЖНА идти «кейсы до автотестов»: qa_author раньше qa_automation. ЭТАП QA, состоящий только из раннеров «прогнать наборы», — ДЕФЕКТ плана; СА не отдает tasks.md без QA-контурных задач, ПМ не принимает.

## Проверка перед стартом QA-этапа (чек-лист ПМ до диспатча раннеров)

1. `test-model/checklists/<id>.md` существует и покрывает все Requirements дельт.
2. Кейсы написаны из дельт спеки (не из готового кода).
3. Кейсы прошли qa_case_reviewer (new/ → approved/).
4. Каждый автотест несет TC-ID, трассируемый к кейсу.
5. На пакетах после add-wiki: независимый аудит покрытия «сценарий дельты → кейс → тест» (как REPORT-coverage-audit) до прод-выкатки.

## Возвраты с этапов

- **return code_reviewer**: фикс-дифф → ре-ревью коротким кругом (тот же ревьюер, append-only review-NNN+1); чекбокс [x] закрывается ТОЛЬКО после финального approve (approved_review_tasks берет последний вердикт — старый approve перезаписывается return'ом).
- **баг QA-раннера**: баг-репорт (`test-model/bugs/BUG-NNN`), набор останавливается до фикса и зеленого перегона; фикс через Флоу 2 (code_review обязателен — решение 2026-10-07-code-review-flow2); повторный прогон набора — отдельной делегацией.
- **GAP аудита покрытия** (сценарий дельты без кейса/теста): Must-сценарий = блокер следующего этапа (деплой/архивация), Should/Could — фикс или принятый риск с пометкой в tasks.md.
- **rework мокапов Заказчиком**: новый мокап → повторный design_validation после фикса.

## Ссылки

- Машина: STAGE_TABLE (`scripts/flow_transition.py`), delegate_gate.py, delegate_watchdog.py — детали в skill `ekotov-factory-pipeline` (references/flowctl-stage-recipes.md, references/design-phase.md, references/flow-graph.md).
- Бэклог: J39 (этот инцидент), J23 (чеклист-этап под упразднением), J13 (5 ролей QA раздельно).
