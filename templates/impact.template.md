# Impact-карта — <change-id>

> Обязательный артефакт СА (J58): заполняется при create_change, до dev-задач.
> Живет в `openspec/changes/<id>/impact.md` ИЛИ как секция «## Impact» в
> design.md/proposal.md. Reviewers (code_reviewer) сверяют карту с диффом PR;
> pr_validate механически сверяет дифф с правилами `scripts/impact_rules.json`.

## Затронутые сервисы

<!-- перечисли сервисы/модули, которых коснется изменение -->

## Контракты

<!-- openapi-дельты; при изменении контракта — contracts/openapi.json перегенерировать (правило IR-01) -->

## Статика (static_v?)

<!-- трогает ли frontend/static|templates; если да — bump static_v в backend/app/pages.py (IR-03) -->

## Deploy-матрица и RUNBOOK

<!-- новый сервис? — deploy/deploy.sh + deploy/RUNBOOK.md (IR-02); порядок выкатки/отката -->

## Миграции

<!-- migrate_*.py? — упоминание в deploy/RUNBOOK.md: порядок применения и отката (IR-04) -->

## Тесты

<!-- какие домены регресса затронуты; план прогонов; нужен ли regress-smoke/new кейсы -->
