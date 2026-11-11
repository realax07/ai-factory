# PLAN-zone-guard: zone-guard в репо, политика по роли (J64.10)

**Флоу: 4** — обслуживание фабрики: исполнитель Pi, пакетный раннер.

## Решения Заказчика (2026-11-11)

- «Прямо из репо»: раннер подключает guard из репо движка, не копию в
  `~/.pi`; нет файла — STOP, sha256 — в отчет стадии.
- «Всем, кроме devops»: docker-мутации запрещены всем ролям, кроме devops;
  `git push` — всем.

## Состав

- `skills/pm-factory/pi/zone-guard.ts` — единственный эталон (перенесен из
  `role-packs/regress-runner/extensions/`): env `PI_ZONE_WRITE` (без env —
  запись запрещена; сегмент с `*`/`?` — glob), `PI_ZONE_ROLE` (bash-правила),
  `PI_ZONE_GUARD_LOG` (лог вне worktree; дефолт `~/.pi/agent/zone-guard.log`);
  чтение docker в той же команде больше не снимает запрет мутации
  (`docker ps && docker rm x` проходил).
- `package_runner`: `ZONE_GUARD` — репо движка (рядом с flowctl; у зеркала
  раннера в проекте `skills/` нет); STOP `ZONE_GUARD_MISSING` до ворот
  входа; env роли и лога (`<state>/zone-guard/<пакет>.log`); sha256 guard'а
  — в `flow_gates.<стадия>.zone_guard_sha256` и в отчете стадии.
- `factory_bootstrap`: копия для ручных запусков — из нового пути.
- Доки: README фабрики, role-packs/README.md, README паков, гайд манифеста.
- Тесты `tests/unit/test_j64_zone_guard.py` (TC-J64-ZG-001…004): guard
  гоняется настоящим node с заглушкой ExtensionAPI (SKIP без node с
  поддержкой TypeScript).

## После мержа (Заказчик, VPS)

Копия `~/.pi/agent/extensions/zone-guard.ts` разойдется с эталоном —
bootstrap предупредит; для ручных запусков обновить:
`cp skills/pm-factory/pi/zone-guard.ts ~/.pi/agent/extensions/`. Ручным
запускам по README паков нужен `PI_ZONE_WRITE` (дефолта больше нет), devops
— `PI_ZONE_ROLE=devops`.

## Вне объема

Bash-канал — по-прежнему эвристика (граница записи — сверка git diff на
finish, J63); parsing редиректов/`mv`/`tee` не делается.

## Критерий закрытия

Сьют зеленый, ci_local зеленый, ревью approve, CI зеленый.
