# PLAN-factory-lock: ворота CI проекта по версии фабрики (J65.7, часть фабрики)

**Флоу: 4** — обслуживание фабрики.

## Решение Заказчика (2026-11-10)

J65.7 — «Lock по SHA сейчас»: factory.lock хранит SHA коммита фабрики;
теги core-vX.Y — после J65.6; копии из проектов снимаются после перевода
всех трех проектов (вместе с J66). Запуск — «давай дальше погнали»
(2026-11-11).

## Состав

- `factory.lock` (`repo=`, `sha=`), `scripts/factory_lock.py` (show/update);
- `.github/workflows/flow.yml`: шаг Factory lock, checkout фабрики на SHA в
  `.factory/`, ворота через `$FACTORY_SCRIPTS`;
- `factory_init`: пишет lock опубликованным HEAD;
- README, реестр скриптов, бэклог; тесты TC-J65-LCK-001…005 (шаг CI
  исполняется bash'ем как в Actions).

## Возврат ревью review-001 (3 major, 8 minor)

Исправлено: lock не записан — WARNING, init не проваливается (тесты init не
зависят от git-состояния фабрики); одна грамматика lock в CI и в
factory_lock.py (ровно по одной строке repo=/sha=, без пробелов; repo по
regex), тесты на расхождения; «опубликован» = влит в origin/main
(`merge-base --is-ancestor`, без сети), а не любая remote-ветка;
`persist-credentials: false` на checkout фабрики; update чинит битый lock;
тесты AI_FACTORY_HOME и условия checkout. Остальное — в резолюции J65.7.

## Вне объема

Перевод проектов (их `flow.yml` и `factory.lock`) — `factory_init --force` в
каждом проекте, с J66; снятие копий скриптов — после перевода всех трех.

## Критерий закрытия (часть фабрики)

Сьют зеленый, ревью approve, CI фабрики зеленый (без lock — свои scripts/).
