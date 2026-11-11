# Code review 001: gates-stats (J65.9)

Commit: 496e349 (диф `origin/main...HEAD`: c99be28, 496e349)
Ветка: chore/gates-stats
Ревьюер: code_reviewer (независимая сессия, автор диффа — другая делегация)
Прогоны: `pytest tests/unit/test_j65_gates_stats.py tests/unit/test_bug026_init_imports.py tests/unit/test_flowctl*.py -q -p no:cacheprovider` → 69 passed (18.26s), AF_STATE_DIR — временный каталог; ручные пробы gates_stats.py на временном state (окно, таймзона, битый state).
Итог: return — 1 major (неполная оговорка о «невидимых» кодах: `reason_codes_never_fired` структурно врет для части кодов), 8 minor.

## Что проверено

- Источники: отчеты gate_runner пишет `flowctl finish` в `<state>/gate-reports` (scripts/flowctl.py:1339), имя `gate-report-*.json` и поле `started_at` (scripts/gate_runner.py:525-535) — совпадают с чтением в gates_stats.py:85-97; `latest.json` правильно исключен глобом.
- runs flowctl_state.json: `decision` = `Decision.to_dict()` с `status`/`blocking_reasons` (scripts/flow_transition.py:211-221, 2091-2094), `created_at` (flowctl.py:739, 928, 978), `defects` с `code`/`source` (flowctl.py:1512) — формат прочитан верно.
- Лог энфорсера: `state_dir()/flow-enforcer.log`, JSONL с `ts` UTC, `event`, `level` (plugins/flow-enforcer/enforcer.py:1126-1138) — верно.
- Копия в проекты: gates_stats.py в FLOW_CONTROL_FILES (factory_init.py:338), test_bug026_init_imports автоматически покрывает импорты копий (COPY_FILES + FLOW_CONTROL_FILES) — зелено.
- Квартальный пересмотр за Заказчиком на VPS — явно сказано в PLAN-gates-stats.md («За Заказчиком»); правило в docs/README-flow-control.md — на месте.

## Замечания

| # | Уровень | Файл:строка | Сценарий / рекомендация |
|---|---|---|---|
| 1 | major | scripts/gates_stats.py:153, 22-25, 191-192; docs/README-flow-control.md:241-243 | `reason_codes_never_fired` выдает коды, которые в runs не могут появиться в принципе, а оговорка «Не видно» перечисляет только ZONE_OUTSIDE_POLICY и J3. Факты: (а) **ZONE_CONFLICT** в flow_transition только объявлен (ft.py:70, 87) и нигде не эмитится в decision; реальный ZONE_CONFLICT дает `session_check.reserve` в prepare (flowctl.py:818-888) — `return 1` без записи цикла. Значит ZONE_CONFLICT всегда «без срабатываний» — а документ сам приводит его как пример дорогого гейта. (б) **STALE_SNAPSHOT** штатно возникает в `flowctl run` (flowctl.py:1078-1089) — без записи в runs; в decision он только при `expected_snapshot_digest`. (в) **Путь энфорсера**: хук гоняет `prepare --dry-run`, а dry-run возвращается ДО записи state (flowctl.py:668-677); энфорсер логирует `prepare_result` лишь с `rc` (enforcer.py:1486-1490) — все отказы на спавне (основной боевой путь J43) не попадают в коды вовсе. Квартальный пересмотр по такому отчету подтолкнет к удалению кодов, которые срабатывают. Рекомендация: в выводе разделить коды «наблюдаемые в runs» и «ненаблюдаемые этим источником» (ZONE_CONFLICT, STALE_SNAPSHOT run-time, dry-run энфорсера) — не класть вторые в never_fired; дополнить «Не видно» в docstring, render и README; тест на это (ZONE_CONFLICT не в never_fired или помечен). Опционально — кандидат в бэклог: писать коды в `prepare_result` энфорсера. |
| 2 | minor | scripts/flowctl.py:3252 | Комментарий «ленивый импорт: только эта подкоманда» неверен: `import gates_stats` стоит при построении парсера и выполняется на КАЖДЫЙ вызов flowctl. Стоимость нулевая (все его импорты flowctl уже загрузил), но отсутствие gates_stats.py в проектной копии (старый init без докопирования) роняет весь flowctl, включая dry-run энфорсера → fail-closed блок всех делегаций. Митигировано FLOW_CONTROL_FILES + test_bug026. Либо поправить комментарий, либо импорт внутри обертки `func` подкоманды (действительно лениво). |
| 3 | minor | scripts/gates_stats.py:88-97, 106-107 | Корректный JSON не того типа (state = `[]`, отчет-список, элемент gates не dict) → traceback и exit 1 вместо обещанного exit 2/WARN (проверено: `echo '[]' > flowctl_state.json` → AttributeError). Проверять `isinstance(..., dict)`, битый отчет — в `unreadable`. |
| 4 | minor | scripts/gates_stats.py:204-210 | `--since` позже `--until` — пустой отчет с exit 0 и полным списком «без срабатываний» (проверено). Отказ exit 2 с сообщением. |
| 5 | minor | scripts/gates_stats.py:55-69 | Окно по префиксу строки без нормализации: запись `2026-11-01T01:00:00+03:00` (= 2026-10-31 UTC) попадает в `--since 2026-11-01` (проверено). Все текущие писатели — UTC (`gr.utcnow_iso`, enforcer `_append_log`), так что честно, но стоит сказать «даты окна — UTC» в help/README и/или парсить `fromisoformat` → `astimezone(utc)`. Записи без времени при заданном окне выпадают молча — добавить счетчик «без времени: N» в вывод. |
| 6 | minor | scripts/gates_stats.py:139-147 | Гейт, который за период только SKIPPED (типично pr_validate локально без PR-контекста), попадает в «без FAIL/ERROR» наравне с честно проходившим — повод удалить гейт, который просто не исполнялся. Выделить «не исполнялся (только SKIPPED/нет отчетов)» отдельно. |
| 7 | minor | scripts/gates_stats.py:10-17, 85; docs/README-flow-control.md:239-241 | Не учтены и не оговорены отчеты вне `<state>/gate-reports`: `flowctl finish --report-dir D` (flowctl.py:1339), прямой `gate_runner run` (дефолт `<repo>/.gate-logs`, gate_runner.py:472, 533), CI. Также лог энфорсера при `FLOW_ENFORCER_STATE_DIR` (enforcer.py:853-858) лежит не рядом с state. Добавить в «Не видно» (или опции `--report-dir`/`--enforcer-log`). |
| 8 | minor | tests/unit/test_j65_gates_stats.py:16-17 vs 133-166 | Трассировка TC-J65-GST-005 обещает «prepare с DENY и finish с FAIL гейта», тест гоняет только prepare. Либо добавить finish (отчет gate_runner в `<state>/gate-reports` — именно путь, от которого зависит статистика), либо поправить описание TC. |
| 9 | minor | tests/unit/test_j65_gates_stats.py | Нет регрессии на ключевые допущения источников: имя каталога `gate-reports` относительно `--state` берется из flowctl (finish → collect) — сейчас тест сам кладет отчеты, расхождение путей flowctl/gates_stats тесты не поймают. Покрывается тем же finish из п.8. |

Не проверено: боевой state на VPS (по плану — за Заказчиком); полный сьют и ci_local (гоняет ПМ).

## Вердикт: return
