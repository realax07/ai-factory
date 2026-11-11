# Code review 002: reference-run (J65.10)

- Commit: 509c2c6 (диф ревью-итерации `3ba1da0..509c2c6`; база ветки — origin/main)
- Ветка: chore/reference-run
- Ревьюер: независимый code_reviewer (сабагент ПМ; автор дифа — другая сессия)
- Прогоны: `python -m pytest tests/unit/test_j65_reference_run.py tests/unit/test_package_runner.py tests/unit/test_j64_dev_per_task.py tests/unit/test_p03_zone_policy.py tests/unit/test_j65_role_zone_digest.py tests/unit/test_audit_fix_gates.py tests/unit/test_j52_w1.py tests/unit/test_j51_review003_fixes.py tests/unit/test_j64_tails.py tests/unit/test_j65_pack_prompt_zones.py tests/unit/test_j66_test_layout.py -q -p no:cacheprovider` → 271 passed in 39.01s (venv314; все файлы, где зовут narrow_zones / _pattern_lang_subset). Плюс свой независимый перебор (ниже).

## Итог

Оба blocker-а review-001 закрыты, новых blocker/major нет.

Свой перебор (алфавит шире тестового: сегменты `a x1 * x* ?1 [ab] ** r.md *.md`, паттерны до 4 сегментов, sub до 3, пути до 5 сегментов из `a b x1 x2 y1 r.md`):
- **реальное расширение = 0.** Считал так: принятая пара (sub, sup) и путь, где `glob_matches(sub)` = True (так зону исполняет session_check), а оракул зон для sup = False;
- оракул автора (идеальная семантика зон) против `glob_matches`: 12 паттернов, где `glob_matches` матчит больше оракула. Все вида `<lit>/**/*`, они матчат сам каталог `<lit>`. Расширения они не дают: такой sub принимается только против sup с хвостом `**`, а тот этот каталог и так покрывает;
- `glob_matches` матчит меньше оракула в ~1.08 млн пар (glob перед `**`). На сужение это работает только в сторону отказа.

Выбор оракула верный. `glob_matches` для sup применялась бы только в роли «политики», а там она лишь строже; исполнение по sub через `glob_matches` я проверил отдельно — расширения нет. Алфавит тестового перебора достаточен: литерал, `*`, частичный glob, `?`, класс, `**`. Длина путей на 1 больше длины паттернов — этого хватает, чтобы найти путь-контрпример для всех хвостов `**` и для префиксов.

Живая политика (agents/roles.json): `**` в середине паттерна нет ни у одной роли (проверил перебором `ROLE_ZONE_POLICY`), значит отказ на `**` в середине sup ничего живого не ломает. Типовые запросы проходят:
- `openspec/changes/x/specs/**` (sa);
- `test-model/new/x/**` (qa_case_author);
- `code-reviews/x/review-1.1-001.md`;
- `src/a/*.py` (dev).

## Замечания

### blocker

нет (review-001 №1 и №2 закрыты: scripts/role_zone_policy.py:154 `return j == len(sup_segs)`, :146 `**` поглощает остаток только последним, :151 lit против glob — fnmatchcase; регрессии `code-reviews/*`, `code-reviews/<pkg>/*`, `openspec/changes/*` в TC-J65-REF-006).

### major

нет

### minor

1. **scripts/pm_bounds_check.py:149 FINISHED_STATUSES** — в session_check есть ещё один нетерминальный по списку, но не держащий зону статус: `stale` (reconcile умершей сессии, session_check.py:845/873). Сейчас stale-запись считается живой. Если после падения стадии сделать reconcile и перезапустить её с тем же owner_pm=package_runner, ворота дадут ложный FAIL «пара повторяется». Отказ безопасный (fail-closed), это вопрос доступности resume. Решение за ПМ: добавить `stale` в FINISHED_STATUSES (зону он не держит) или явно записать в бэклог, что после reconcile нужен release.
2. **Готовность concrete-пути (до этого диффа, вне пакета)**. `narrow_zones("sa", ["openspec/changes/x/specs/a/spec.md"])` → DENY и на origin/main тоже: `_allowed_superset` для конкретного пути идет через `glob_matches`, а та сравнивает glob перед `**` как литерал. В бэклоге J65 это уже записано кандидатом (запись 2026-11-11, строка ~378). Отмечаю только, что дефект бьет по живому пути СА (spec.md внутри specs/ по конкретному пути). Приоритет кандидата стоит поднять.

Проверено без замечаний:
- заглушка подменяет вердикт только в файлах своей стадии (`written`);
- новый тест на дописывание: два заголовка, решает последний (`parse_verdict` = return), review-1.1 не тронут;
- git env изолирован и в `_git`/`git init`, и в `runner_env`;
- docstring REF-003 исправлен;
- REF-005 покрывает fail-closed на `""` и `weird`.

Не проверено: полный сьют (гонит ПМ).

## Вердикт: approve
