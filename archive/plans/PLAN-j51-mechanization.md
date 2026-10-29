# PLAN-j51: Механизация параллельных делегаций (worktree, regress, regress-final)

**Флоу: 4** (обслуживание конвейера). Источник: `backlog/J51-механизация-параллельных-делегаций-2026-10-16.md`
(фактура инцидента регресса после параллельных qa/dev + решения разбора 2026-10-16).

## Декомпозиция

### J51.1 — Worktree-per-delegation в prepare
`flowctl prepare` при ALLOW создает выделенный worktree (переиспользование
`scripts/session_worktree.sh`), путь в ALLOW-объекте. Enforcer (J43):
параллельные скоупы без разных деревьев → DENY. Тесты: TC-J51-001..00N.

### J51.2 — `flowctl regress --change C`
Детерминированный маппинг диффа → затронутые тестовые домены (frontend →
tests/web, backend → tests/api, scripts/ → tests/…), прогон только их,
артефакт `test-model/regress/<C>/regress-<N>.md`: PASS/FAIL, commit hash,
хвост лога. Регресс своего куска — механически.

### J51.3 — Ворота merge = regress-final
`pr_validate`/check_change: для change-пакетов требуется финальный артефакт
`regress-final.md` (PASS, commit == PR head, свежесть) — без него FAIL,
fail-closed. Артефакты `regress-<N>.md` финальными не считаются.

### J51.4 — Роль regress_runner
`agents/regress_runner_agent.md`: узкий бриф (ветка/коммит/сьюты — контекст
релиза не нужен), обязан различить баг от флака (изолированный перепрогон),
FAIL → возврат dev'у. + строка в agents/README, чекбоксы MAP J51.
Решение о переиспользовании qa_runner (J17-2) — при реализации J51.4.

## Порядок и регресс

Сериально (фабрика — один worktree, параллель здесь и есть гонка):
J51.1 → J51.2 (один dev-прогон), затем J51.3 → J51.4. Финальный полный регресс
фабрики — сериально перед merge каждого PR; роль regress_runner подключается
с J51.4. Прецедент реализации: J50 (deleg + фабричный PR + зеркало).

## Не в скоупе

Bypass-реестр (без изменений), watchdog'и, CI-ворота J42 (отдельное решение).
