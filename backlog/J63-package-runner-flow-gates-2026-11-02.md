# J63 — ворота flowctl в package_runner (pi-стадии не обходят движок)

Дата: 2026-11-02. Флоу 4 (план — PLAN-runner-flow-gates.md). Источник —
аудит Pi-миграции (внешний агент Claude Code), решение Заказчика «Да, начни
с ворот».

## Проблема

После J59/J60 основной путь исполнения 5.3-ролей — Pi через
`scripts/package_runner.py`, но раннер вызывал `pi` в обход ворот:
ни `flowctl prepare` (план релиза, требования, политика зон), ни резервации
в реестре сессий (ZONE_CONFLICT с делегациями и другими пакетами), ни
приемки по фактическому диффу. flow-enforcer и delegate_watchdog видят
только `delegate_task` — Pi-стадии для них невидимы. J60 запрещал
hermes-делегацию на 5.3-роли, а разрешенный путь не охранялся.

## Сделано

- pi-стадия: `flowctl prepare --worktree` → `run` → pi → `finish
  --gate-scope post_agent` → коммит стадии в ветку пакета → резервация
  finished → closed. DENY/UNKNOWN/returned/blocked → STOP с кодом
  (optional — skipped, зона освобождается). provisional только из-за
  `pr_validate` SKIPPED засчитывается (это ворота PR/CI).
- Роль без этапа во флоу (ba, regress_runner, devops вне Ф3): резервация
  зоны по политике роли + post-check `session_check`, WARNING
  ROLE_WITHOUT_STAGE. Роль вне политики (debug, auditor) — STOP.
- Ролевой AGENTS-файл раннера убирается после pi; SESSION.md не коммитится.
- normalize_zone: glob в середине зоны → конкретный префикс guard'а.
- Мини-парсер YAML: срезка комментариев в конце строки (паритет с
  yaml.safe_load). Полный пример Флоу 1 в гайде до этого НЕ разбирался
  (`run: pi:sa  # …`, многострочные `[...]`) — исправлено, тест TC-PR-053
  держит примеры гайда разбираемыми и в рамках политики зон.
- Гайд: раздел «Ворота pi-стадии», зоны примера Флоу 1 приведены к
  политике ролей (10 из 13 pi-стадий получили бы ZONE_OUTSIDE_POLICY).
- Тесты TC-PR-042…053 (реальные flowctl/session_check во временном
  реестре); тесты раннера больше не трогают ~/.hermes.

## Остаток (кандидаты, решение Заказчика)

1. **Флоу 4 scope:** `flow_state.CHORE_RE = ^chore$`, а пакеты/планы
   обслуживания — `<slug>` / `PLAN-<slug>.md` (J43.1). Реальный prepare —
   UNKNOWN AMBIGUOUS_STATE; энфорсер гасит это постфильтром только в
   dry-run. Раннер не подменяет scope → Флоу-4-пакеты раннером сейчас STOP.
   Предложение: CHORE_RE принимает `chore` и kebab-slug.
2. **Зоны пак-README ≠ политика ролей** (agents/README.md): code-reviewer
   пишет в `test-model/reviews/` (политика и pr_validate J10 —
   `code-reviews/`), architect/qa-automation/regress-runner/devops — шире
   политики. Выровнять паки (или политику — защищенная зона).
3. **debug/auditor вне политики зон** — роли паков без строки в таблице.
4. **zone-guard:** только write/edit; bash-запись не охраняется; guard не
   версионирован в репо для всех ролей (живет в ~/.pi). С воротами выхода
   выход за зону теперь ловится по диффу, но уже после факта.
5. **finished-сессии делегаций** не переходят в closed нигде в коде
   (ZONE_HOLDING включает finished) — зона принятой делегации держится до
   ручного разбора. Раннер закрывает свои; для делегаций — отдельно.
6. **Тесты фабрики пишут в реальный HOME** (`~/.hermes/scripts`,
   `flow-enforcer.log`, `flowctl_state.json`) — на чистой машине прогон
   сьюта создает ~/.hermes. Родственный инцидент: коммит 6d4d365 занес в
   main каталог `prepared: true/` с симлинками на /home/openclaw/... .
7. Pi-стадии по-прежнему не видит delegate_watchdog (сверяет
   async_delegations Hermes) — теперь они видны в реестре сессий и state
   flowctl (owner_pm=package_runner), детектор обхода для них не нужен,
   пока раннер — единственный путь вызова pi.
