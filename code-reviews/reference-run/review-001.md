# Code review 001: reference-run (J65.10)

- Commit: 3ba1da0 (диф `origin/main...HEAD`: 10594b4, 3ba1da0)
- Ветка: chore/reference-run
- Ревьюер: независимый code_reviewer (сабагент ПМ; автор дифа — другая сессия)
- Прогоны: `python -m pytest tests/unit/test_j65_reference_run.py tests/unit/test_package_runner.py tests/unit/test_j64_dev_per_task.py -q -p no:cacheprovider` → 119 passed in 28.55s (venv314). Перебор контрпримеров `_pattern_lang_subset` против `session_check.glob_matches` (сегменты `a b * ** x* ? [ab] *.md`, длины 1..3, пути глубины 1..4), старая версия (origin/main) против новой: старая — 39082 расширяющих пар, новая — 44582; **5500 новых**, из них 2835 с sup без `**`.

## Итог

Эталонный прогон собран добротно: раннер подпроцессом, настоящие flowctl/session_check/gate_runner во временном state, подменен только `pi`; тест ловит склейку ворот (REF-001..004 красные при поломке любого звена). Фикс pm_bounds_check корректен. Но фикс `role_zone_policy._pattern_lang_subset` **расширяет зону** — нарушает инвариант «сужение никогда не расширяет»: снятие консервативного отказа glob↔glob обнажило два латентных дефекта функции, ранее недостижимых. Вердикт — return.

## Замечания

### blocker

1. **scripts/role_zone_policy.py:158 (вместе с :148) — запрос-префикс короче политики принимается.** Цикл идет по сегментам sub и при `i == len(sub_segs)` возвращает True, не проверяя, что sup исчерпан (`j == len(sup_segs)` или остаток sup — ровно `["**"]`). Раньше это было недостижимо: любой glob-сегмент sub против не-`**` сегмента sup давал False до конца цикла. Теперь `ssub == ssup` пропускает одинаковый glob — и короткий glob-префикс проходит. Воспроизведено на реальной политике:
   - `narrow_zones("code_reviewer", ["code-reviews/*"])` → zones `["code-reviews/*"]`, violations `[]` (origin/main: violation). Зона матчит `code-reviews/evil.md`, политика `code-reviews/*/review-*.md` — нет.
   - `narrow_zones("sa", ["openspec/changes/*"])` → принято (origin/main: violation); зона матчит `openspec/changes/evil`, политика СА — нет.
   - Синтетика: `_pattern_lang_subset("*", "*/a")` → True; `("a/*", "a/*/b")` → True.
   Сценарий отказа: стадия манифеста (или делегация через flowctl prepare) объявляет усеченную зону — prepare ее не режет, `session_check check` пропускает запись вне политики роли. Это ровно класс, против которого P0.3 стоит.

2. **scripts/role_zone_policy.py:152-153 — литерал против любого glob-сегмента sup проходит без сопоставления** (rank "star" — это и `x*`, и `*.md`, и `?`, и `[ab]`, а не только `*`). Тоже латентно до этого диффа, теперь достижимо: `_pattern_lang_subset("a/*", "x*/*")` → True, путь `a/a` в sub есть, в sup нет; `("a/*.md", "*.md/*.md")` → True. В текущей политике ролей (glob-сегменты кроме `*` стоят только последними) эксплойта не нашел, но инвариант функции нарушен и следующая правка политики (например `test-model/reviews/*-x/...`) его вскроет. Исправление: в ветке lit↔star — `fnmatch.fnmatchcase(ssub, ssup)` (посегментно, как в `glob_matches`).

   Рекомендация по обоим: в конце цикла `return j == len(sup_segs) or sup_segs[j:] == ["**"]`; lit↔glob — через fnmatchcase. В TC-J65-REF-006 добавить отказы `code-reviews/*`, `code-reviews/{PKG}` с glob-хвостом короче политики (`code-reviews/*` и `openspec/changes/*` для sa) и property-тест «принято ⇒ ∀ путь из выборки: glob_matches(sub) ⇒ glob_matches(sup)» на небольшом алфавите сегментов (перебор из прогона выше укладывается в секунды).

   Отдельно (до этого диффа, не блокирует пакет, но стоит строки в бэклоге): `rsup == "dstar"` в середине sup трактуется как поглощение всего остатка — `_pattern_lang_subset("*", "**/a")` → True. Это основная масса старых 39082 пар; в текущей политике `**` стоит только хвостом.

### major

нет

### minor

1. **scripts/pm_bounds_check.py:161** — статус вне известного набора (опечатка `Running`, пустая строка `""`) трактуется как не-живой и молча выпадает из проверки повтора пары. Fail-open на кривой записи; предложение — живыми считать всё, кроме явно терминальных (`closed`, `released`, …), т.е. инвертировать список. По существу фикс корректен: J2 — про одновременное владение проектом, история закрытых сессий вторым ПМ не является; `load_pm_projects`/`--all-projects` не задеты (перебирают все записи независимо от статуса, проблемы реестра только агрегируют). Копия `LIVE_STATUSES` с тестом-сверкой против `session_check.ZONE_HOLDING` (REF-005) — приемлемо.
2. **tests/fixtures/reference-run/bin/pi:50-56** — подмена вердикта `REFERENCE_STUB_VERDICT` переписывает `## Вердикт: approve` во **всех** `code-reviews/*/review-*.md` worktree, а не только в файле текущей стадии: `dev-1.2-review:return` тихо перепишет уже закоммиченный review-1.1-001.md (история append-only, раннер это увидит как дифф в зоне ревьюера). Ограничить файлами `outputs/<stage>/`.
3. **tests/fixtures/reference-run/bin/pi:39-42** — ветка append при повторной итерации ревью ни одним TC не покрыта (REF-002 останавливается на первом return); либо тест resume после return, либо убрать ветку.
4. **tests/unit/test_j65_reference_run.py:90-106** — окружение не изолировано от глобального git config (`commit.gpgsign=true`, hooks у разработчика ломают коммиты стадий) и HOME. В CI безопасно; для локальной устойчивости — `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1` в `runner_env` и в `make_project`. `PIPELINE_OPENSPEC_CMD=true` — ок, зависимости от openspec CLI нет.
5. **tests/unit/test_j65_reference_run.py:196-198** — docstring REF-003 начинается с «dev-стадии пишут docs/», а фактически падает первая стадия create_change; переформулировать.

Проверено и замечаний нет: ассерт pr_validate «ровно QA-контур» — строгое равенство множеств по формату `  - <артефакт>: …` (pr_validate.py:1201) намеренно хрупкий в правильную сторону (любой новый недостающий артефакт СА/dev/ревью краснит эталон); `.tmpl` не собирается pytest фабрики; CI job test-flow-control гоняет `pytest tests/` (flow.yml:41) — тест включен; время ~15 с на полный эталон, таймаут подпроцесса 600 с.

Не проверено: полный сьют (по поручению гонит ПМ); мутационный прогон «откатить фикс pm_bounds → REF-001 красный» не делал (REF-005 покрывает юнитом).

## Вердикт: return
