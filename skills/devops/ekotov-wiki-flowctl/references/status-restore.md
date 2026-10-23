# Восстановление статуса конвейера (обрыв сессии / «восстанови статус»)

Цель: за один проход собрать фактическое состояние и выдать доклад с этапами
ворот (prepare/reserve/check/gates/provenance: PASS/DENY/UNKNOWN/SKIPPED).
Оборванные вводные не додумывать — только данные из источников ниже.

## Порядок (одна-две пачки параллельных команд)

1. **Реестр сессий** `~/.hermes/state/active_sessions.json` (вне git): скриптом
   посчитать `Counter` по lifecycle-state, вывести НЕ-completed записи
   (delegation_id, роль, зоны, последний lifecycle-переход) и 5 последних
   записей по дате. Полный файл читается по кускам (он сотни КБ) — сворачивай
   в Python, не тащи в контекст целиком.
2. **Git обоих репо** (`~/ekotov-wiki`, `~/ai-factory`): `git branch --show-current`,
   `git log --oneline -8`, `git status --short`, `main` vs `origin/main`.
3. **PR**: `gh pr list --state open` + последние merged с датами; по каждому
   открытому — `gh pr checks <n>` (flow/e2e) и mergeable.
4. **Свежие flowctl-раны** `~/.hermes/state/flowctl_state.json` → `runs`:
   отсортировать по created_at, последние 5-8 (action, role, change/task,
   finished?). Незакрытые `finished=False` при живом артефакте = делегация
   оборвана — фиксируется в lifecycle реестра (reason + evidence), затем
   ре-диспетч.
5. **Прод** (если релевантно): `docker ps --format '{{.Names}} {{.Status}}'` —
   все контейнеры healthy?
6. **Открытые хвосты из памяти** (напр. «проверить прод после ребута») —
   закрыть проверкой из п.5 или пометить как открытые в докладе.

## Диагностика красного чека

`gh run view <run-id> --log-failed | tail` — причина (FLOW-ERROR flow_check /
PR-VALIDATE FAIL pr_validate). Локальная репликация: см. SKILL.md «Красный
flow/pr_validate».

## Доклад

- Где стоим (пакет/волна/задача + delegation_id), что влито, что красное и
  почему (дефект кода vs процессная краснота), что запущено, что дальше.
- Каждый красный PR: вердикт «чинить / ожидаемый процессный статус».
