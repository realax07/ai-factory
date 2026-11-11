# Code review 002 — chore/j63-tails (J64.14, Флоу 4)

- **Commit:** c70d122475eaf35c5e27af7489826b00935aefbe (исправления по review-001; `git diff 1bc0632 c70d122`)
- **Ревьюер:** code_reviewer (независимый; автор — другой агент)
- **Вход:** review-001.md (2 major, 8 minor), PLAN-j63-tails.md (раздел «Возврат ревью review-001»)
- **Прогон:** test_j64_j63_tails + test_flowctl_gc + test_package_runner + test_flowctl — 178 passed. Пробы review-001 повторены в scratch на c70d122 (результаты ниже).

## Сверка находок review-001

| # | Было | Статус | Факт |
|---|---|---|---|
| 1 | major: closed не done для gc | исправлено | `GC_WORKTREE_DONE` += `closed`. Проба на worktree с маркером: с `finished_at` — `[closed, released]` → remove d0,d1; `[closed]` → remove; `[finished]` → remove; `[closed, running]` → list_only («делит активная сессия»). Без `finished_at` — все варианты list_only «пакет раннера не докатан». Интеграционный тест gc_plan добавлен. |
| 2 | major: phase после сноса worktree | исправлено | `cmd_prepare` пишет `repo_root = git_main_root(scope.repo)` (для worktree раннера — корень клона; проба: совпадает с ключом клона). Проба после `git worktree remove`: phase находит запись (`chore_task`, accepted). Легаси-записи без `repo_root` — прежний фолбэк по живому пути (допустимо). |
| 3 | minor: optional после accepted | исправлено | optional-ветка `_reject` помечает запись `rejected_after_accept` (`registry=False`, зону освобождает gate_abandon). |
| 4 | minor: finished_at при повторном прогоне | исправлено | `state.pop("finished_at")` в начале прогона (после dry-run). |
| 5 | minor: porcelain без -z | исправлено | `-z` + пропуск исходного имени для R/C. Проба: `code-reviews/ревью-001.md`, `new name.txt`, `q"uote.txt` — без экранирования. |
| 6 | minor: обходы проверки остатков | частично | resume после STOP ловится (`gate_leftovers` в state, тест добавлен); артефакты раннера исключены. Optional skip — записан в плане как не сделанный: приемлемо (предупреждение в журнале есть, исход — прежний OUT_OF_ZONE следующей стадии). См. новую находку N1. |
| 7 | minor: pm-resume до проверки отчета | исправлено | проверка отчета перенесена выше мутации resume, дубль `registry_path` убран (используется определение до проверки реестра). |
| 8 | minor: git_main_root bare/подмодули | не сделано (записано) | приемлемо: обычные репо (`.git`) не затронуты, ограничение зафиксировано в PLAN; миграцию ключа/enforcer для bare и подмодулей стоит вынести в backlog отдельным item. |
| 9 | minor: close без аудита/процесса | исправлено | событие `close` в lifecycle записи; шаг ПМ в docs/README-flow-control.md. `--audit` не добавлен — для minor достаточно истории реестра и lifecycle. |
| 10 | minor: тесты-юниты | исправлено | интеграция gc_plan, phase после сноса worktree, идемпотентность close, resume после STOP по остаткам. |

## Новые находки

| # | Severity | Файл:строка | Находка |
|---|---|---|---|
| N1 | minor | scripts/package_runner.py `stage_dirty_before` (≈972) | `gate_leftovers` вынимается (`pop`) из state ДО запуска стадии. Если следующая попытка падает по другой причине (gate exit ≠0, таймаут), `_stop` пишет state уже без памяти об остатках, и третья попытка опять считает их «бывшими до стадии». Проба: 1) стадия оставила `lint-report.txt` → STOP; 2) gate exit 1 → STOP; 3) gate ok → **пакет докатан, rc 0, файл на месте**. Фикс: не делать `pop`, а вычитать; чистить запись только при успехе стадии (или когда файлов уже нет). |
| N2 | minor | tests/unit/test_j64_j63_tails.py:233-245 | В TC-003 `repo_root` записи задается руками: нет теста, что `cmd_prepare` реально пишет `repo_root` (в том числе для `--repo <worktree>`, как у раннера). По чтению кода (cmd_prepare: `repo` = `args.repo` resolved, `scope.repo` из того же снимка) путь корректен. |
| N3 | nit | scripts/package_runner.py `runner_leftovers` | Артефакты раннера исключаются по basename в любом подкаталоге (`Path(p).name in names`); если gate-команда правит сам PLAN-файл в worktree, это не будет замечено. Риск минимален. |

Blocker/major нет.

## Вердикт: approve
