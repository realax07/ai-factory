# Ревью core-ready (J65.6 «ядро готово») — review-003

- Пакет: PLAN-core-ready.md (Флоу 4), ветка `chore/core-ready`
- Коммит правок: d59e19a (`git diff 2f32fcb..d59e19a`)
- Ревьюер: code_reviewer (независимый сабагент Claude Code, автор диффа — другая сессия). Только статика и пробы
  вызовом функций. pytest в окружении нет, поэтому тесты запущены вызовом функций с заглушками `pytest` и
  `monkeypatch`:
  - `test_scope_match_not_for_change_ids`, `test_flow2_scope_slug_and_plain_review_order`,
    `test_boundary_detector_catches_violation`, `test_core_boundary_no_hermes_outside_adapter` — PASS;
  - все 5 тестов `test_j65_gates_changelog.py` — PASS;
  - `flow_check.py .` — OK. `openspec` в окружении ревьюера нет, его прогон — за ПМ.

## Вердикт: return

m8, m9, m10, n1, n2 закрыты. m7 закрыт для примера из review-002 (`bug-tracker` / `bug-tracker-v2`), но не по
существу. `scope_matches` по-прежнему засчитывает стадию ревью другого scope в двух случаях:
- два разных bug-id, если один продолжает другой (`BUG-042` / `BUG-042-RECHECK-003`);
- change-id Флоу 1, который подпадает под грамматику bug-id (`bug-fix-001` / `bug-fix-001-v2`).

Это тот же fail-open в воротах независимости, что и m7. Правка — несколько строк (m11).

## Закрытие находок review-002

| Находка | Статус | Чем подтверждено |
|---|---|---|
| m7 | частично | `pr_validate.py:334-336`, `BUG_SCOPE_RE` (`:376`). `bug-tracker` / `bug-tracker-v2` в обе стороны — False, `BUG-0420` / `BUG-042` — False, тест `test_scope_match_not_for_change_ids` добавлен. Остаток — m11. |
| m8 | закрыта | `STATE_DIR_MENTION` (`test_j65_core_ready.py:67`) вырезает `~/.hermes/state` только как каталог. `"~/.hermes/state.db"` ловится, `Path.home() / ".hermes"` ловится через `BANNED_EXACT ".hermes"`. Проба на всех `scripts/**/*.py`: срабатывания только в файлах из `ALLOWED` (hermes.py, factory_bootstrap, factory_init, factory_paths, session_watchdog). Ложных срабатываний на остальном ядре нет. `task-0.log` в `BANNED_SUBSTR` не добавлен — это некритично, путь логов ловится по `.hermes`/`/.hermes/`. |
| m9 | закрыта | `pr_validate.py:492` — `scope_matches`. Sidecar с `change = "BUG-042-fix"` для `check_bug(repo, "BUG-042")` проходит (новый тест PASS). |
| m10 | закрыта | `CHANGELOG-gates.md:60, 64`. `SKIP` сверен с `flow_scope_check.py:173, 179` и `flow_preflight.py:145-163, 196-200, 249` («HEAD не читается»). `STALE` сверен с `gate_runner.py:25, 571, 593`, `flowctl.py` (finish) и `package_runner.py:643`. |
| n1 | закрыта | `pr_validate.py:1418-1420`. Хвост называет обоих проверяющих: pre_merge с `--pr-id` и Заказчика при merge. |
| n2 | закрыта | TC-007 стоит перед TC-008 (`test_j65_core_ready.py:23-27`), дата 2026-11-16 указана (`PLAN-core-ready.md:12`). |

## Находки

### m11 (minor): `scope_matches` склеивает разные bug-id и change-id Флоу 1 в грамматике bug-id

`scripts/pr_validate.py:334-336`. Slug-правило проверяет только короткую сторону (`BUG_SCOPE_RE.fullmatch(b)`)
и префикс. Длинная сторона при этом может сама быть другим bug-id или change-id. Пробы прямым вызовом:

| run_scope | scope PR | результат | ожидается |
|---|---|---|---|
| `BUG-042-RECHECK-003` | `BUG-042` | True | False: по `flow_ids.BUG_ID_PATTERN` это отдельный баг (комплекс `042-RECHECK`), slug в грамматике только строчный |
| `BUG-001-002` | `BUG-001` | True | False: отдельный bug-id |
| `bug-fix-001-v2` | `bug-fix-001` | True | False: change-id Флоу 1 (`CHANGE_ID_PATTERN` допускает `bug-fix-001`), slug-правило к Флоу 1 неприменимо |
| `BUG-042-` | `BUG-042` | True | False: пустой slug |
| `BUG-AF-RECHECK-003-fix` | `BUG-AF-RECHECK-003` | True | True |
| `BUG-AF-003` | `BUG-AF-RECHECK-003` | False | False |

`scope_matches` вызывается и в Флоу 1 (`review_independence_findings` из проверки change-пакета, `:204`), и в
`runner_review_ok` (`:358`), `dev_delegations` (`:412`), `sidecar_findings` (`:492`). Поэтому в Флоу 1 ревью
пакета `bug-fix-001-v2` засчитается для PR `bug-fix-001`. Такие имена редки, но это обход ворот независимости,
ради которых сделан пакет.

Та же склейка есть в `bug_review_dir` (`:67-77`, `startswith(want + "-")`). Без каталога `code-reviews/BUG-042/`
PR бага BUG-042 возьмет `code-reviews/BUG-042-RECHECK-003/`.

Что сделать:
1. Передавать флоу явно: `scope_matches(run_scope, scope_id, bug=True)` только из `check_bug_review` и цепочки
   Флоу 2. Для Флоу 1 — точное сравнение без учета регистра.
2. Хвост после префикса проверять как slug и запрещать хвосту делать строку другим bug-id. Например:
   `rest = a[len(b) + 1:]`, засчитывать при `SLUG_RE.fullmatch(rest)` и `not BUG_SCOPE_RE.fullmatch(a)`.
   Цена — ложный отказ для slug вида `fix-001`, это безопасная сторона.
3. То же правило применить в `bug_review_dir`.
4. Добавить в тест `test_scope_match_not_for_change_ids` отрицательные случаи `BUG-042-RECHECK-003` / `BUG-042`,
   `bug-fix-001-v2` / `bug-fix-001` (Флоу 1), `BUG-042-` / `BUG-042`.

### n3 (nit): STALE в CHANGELOG без случая «отчет без repo_head»

`docs/CHANGELOG-gates.md:64`. gate_runner помечает STALE и отчет без `repo_head` при валидном HEAD
(`gate_runner.py:26, 571`). Можно дописать «или отчет не несет HEAD». Не блокирует.

## Проверено, замечаний нет

- Новый тест TC-J65-CORE-008 сверяет sidecar со slug по всей цепочке `check_bug` → `check_bug_review` →
  `review_independence_findings` → `sidecar_findings` → `delegation_findings`, с реестром Hermes completed.
- `STATE_DIR_MENTION` с lookahead `$|[/\s)»,;:]`. `"~/.hermes/statefoo"` и `"~/.hermes/state.db"` не вырезаются.
  `"~/.hermes/state."` в конце фразы дал бы ложное срабатывание по `/.hermes/`, но это безопасная сторона, и
  в реальном коде такой формы нет.
- Итоговая строка pr_validate: хвост есть только при `SKIPPED_REVIEW_CHECKS`, формат `SKIPPED (N, …)` сохранен.
- Тесты CHANGELOG после правки таблицы статусов — PASS.
