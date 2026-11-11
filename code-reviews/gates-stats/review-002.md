# Code review 002: gates-stats (J65.9)

Commit: 24b782a (повторное ревью; диф исправлений `496e349..24b782a`)
Ветка: chore/gates-stats
Ревьюер: code_reviewer (независимая сессия, автор диффа — другая делегация)
Прогоны: `pytest tests/unit/test_j65_gates_stats.py tests/unit/test_bug026_init_imports.py tests/unit/test_flowctl*.py -q -p no:cacheprovider` → 70 passed (23.46s), AF_STATE_DIR — временный каталог; ручные пробы на временных копиях scripts/ и временном state.
Итог: approve — major из review-001 закрыт, minor 2–9 закрыты; 4 новых/остаточных minor, ни одного blocker/major.

## Закрытие замечаний review-001

| # | Статус | Проверка |
|---|---|---|
| 1 major | закрыт | `UNOBSERVABLE_CODES` (ZONE_CONFLICT, STALE_SNAPSHOT) исключены из `reason_codes_never_fired`, выводятся отдельным списком `reason_codes_unobservable`; `SPAWN_NOTE` про dry-run энфорсера — в JSON (`not_observed`), render, docstring, README. Дрейф — TC-J65-GST-006 (код без `Finding(` в flow_transition обязан быть в списке; regex `Finding\(\s*CODE` покрывает и перенос строки). |
| 2 | закрыт | flowctl.py: try/except ImportError, без модуля — только подкоманда (exit 2), `status --help` работает (тест + ручная проба). Остаток — п.1 ниже. |
| 3 | закрыт частично | state/runs/отчет не объект — exit 2 / WARN. Остаток — п.2 ниже. |
| 4 | закрыт | `--since` > `--until` → exit 2 (тест). |
| 5 | закрыт | окно — UTC-даты в help/docstring/README (все писатели UTC); `undated_skipped` + WARN (тест). |
| 6 | закрыт | `gates_not_executed` (только SKIPPED/нет отчетов) отдельно от `gates_never_failed` (был PASS, без FAIL/ERROR) — тест. |
| 7 | закрыт | `--reports DIR` (повторяемый, дедуп по resolve), `--enforcer-log`, дефолт по FLOW_ENFORCER_STATE_DIR как у энфорсера (enforcer.py:853-858) — тест. |
| 8 | закрыт | описание TC-005 приведено к поведению. |
| 9 | закрыт слабо | каталог отчетов finish проверяется строковым поиском в исходнике flowctl — см. п.3 ниже. |

## Замечания

| # | Уровень | Файл:строка | Сценарий / рекомендация |
|---|---|---|---|
| 1 | minor | scripts/flowctl.py (fallback gates-stats, `nargs=argparse.REMAINDER`) | Известная особенность argparse: REMAINDER-позиционал не забирает аргументы, начинающиеся с `--`. В копии без gates_stats.py `flowctl gates-stats --json --state x` → `error: unrecognized arguments: --json --state` (exit 2, проверено) — понятное сообщение «нет gates_stats.py» теряется; тест вызывает подкоманду без флагов и это не ловит. Exit 2 и не-падение остального flowctl сохраняются. Варианты: `parse_known_args` для этой ветки или зарегистрировать те же флаги-заглушки. |
| 2 | minor | scripts/gates_stats.py:139-141 | Отчет-объект с `gates` не списком (`"gates": "abc"`) или элемент gates не dict → AttributeError, traceback, exit 1 (проверено). Проверять `isinstance(list)`/`isinstance(dict)`, иначе — в `unreadable`. |
| 3 | minor | tests/unit/test_j65_gates_stats.py (TC-005, `assert 'report_dir=args.report_dir or str(state_path.parent / "gate-reports")' in src`) | Проверка по тексту исходника: безобидный рефакторинг (перенос в константу) даст ложный красный, а реальное расхождение в другом месте — не поймает. Поведенческий finish лучше, но допустимо как страховка от дрейфа. |
| 4 | minor | scripts/gates_stats.py (`--reports`) | Несуществующий каталог `--reports` молча игнорируется (проверено: `--reports /nonexistent` → 0 отчетов, без WARN). Для явно переданного флага — WARN в `unreadable`. |

Не проверено: боевой state на VPS (по плану — за Заказчиком); полный сьют и ci_local (гоняет ПМ).

## Вердикт: approve
