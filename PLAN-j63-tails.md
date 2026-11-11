# PLAN-j63-tails: остаток ревью J63 — раннер и flowctl (J64.14)

**Флоу: 4** — обслуживание фабрики.

## Решение Заказчика

«Давай все что можно сделать до 66» (2026-11-10), «давай дальше погнали»
(2026-11-11): J64.14 — следующим после J65.7.

## Состав (7 пунктов ТЗ)

1. gc и живой пакет — маркер пакета в git-dir worktree + `finished_at`;
   worktree, который делит не-done сессия, не сносится.
2. `rejected_after_accept` при отказе после `finish accepted`.
3. `flowctl phase` — repo по `git_main_root`.
4. `finish --pm-resume` — реестр проверяется до перевода в running.
5. `git_main_root` bare-репо — common-dir.
6. `flowctl close` — finished → closed для делегаций Hermes.
7. gate/stand-стадии, оставившие файлы, — STOP с перечнем.

Тесты TC-J64-J63-001…007.

## Возврат ревью review-001 (2 major, 8 minor)

Исправлено: `closed` — done для gc (worktree докатанного пакета и закрытых
`flowctl close` сессий сносится; недокатанный пакет держит маркер); запись
цикла хранит `repo_root` — phase находит ее по клону и после сноса worktree;
optional-стадия после accepted тоже помечается; `finished_at` сбрасывается в
начале прогона; `git status -z` (кириллица, кавычки); оставленные файлы
стадии запоминаются в state — resume их снова ловит; собственные артефакты
раннера (план, state, лог, отчеты) — не «оставленные»; отчет и реестр
проверяются до `--pm-resume`; `flowctl close` — событие в lifecycle записи,
шаг процесса ПМ в docs/README-flow-control.md; интеграционные тесты
(gc_plan, phase после сноса worktree, идемпотентность close, resume).
Не сделано (записано): ключ зон `git_main_root` для bare/подмодулей без
миграции старых резерваций (обычные репо не затронуты; для bare —
резервации до мержа ключ меняют); enforcer `worktree_conflict` для
bare/подмодулей; остатки optional gate-стадии со skip остаются в worktree.

## Критерий закрытия

Сьют зеленый, ревью approve, CI зеленый.
