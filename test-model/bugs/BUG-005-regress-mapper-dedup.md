# BUG-005: дедуп доменов маппинга flowctl regress

## Суть
flowctl regress маппил дифф в домены [tests/api, tests/web, tests] — дубль
общего домена рождает коллизию conftest для bare-импортов: pytest exit 2
на коллекции, до исполнения тестов. Воспроизводится на чистом main
(ekotov-wiki, regress-final 2026-10-18).

## Статус

- 2026-10-18: исправлено (pipeline/fix-regress-mapper: дедуп доменов до
  прогона — общий tests/ сворачивает частичные; TC-J51-021/022 + обновлены
  TC-J51-010/016; негативная проверка снятие-фикса → 3 красных). CLOSED —
  после merge и синхронизации зеркала ekotov-wiki.
