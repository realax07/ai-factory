# Review-001 — P17-review (code review дифа: SDD-ворота arch-этапа + явный skip)

- **Задача:** P17-review (независимое code review, Флоу 4, scope=chore)
- **Ревьюируемая поставка:** ветка `chore/p17-arch-gate`, диф `main...HEAD`, коммит 2ef0169; 3 файла, +165/-5 (scripts/flow_state.py, scripts/flow_transition.py, tests/test_p17_arch_gate.py)
- **Reviewer-Delegation:** p17-review (Флоу 4, маркер flow=4 role=code_reviewer)
- **Решение:** 2026-10-08-arch-review-policy
- **Метод:** чтение дифа против брифа по 5 осям фокуса (skip только для MISSING, безавторный skip = INVALID, обратная совместимость при sdd ready, обходы «skip без автора», реальность тестов) + живые прогоны: целевая сьют (8 passed), полный регресс фабрики (848 passed, 120s) и две adversarial-пробы поверх тестов.

## Вердикт: approve

Поставка точно соответствует решению 2026-10-08-arch-review-policy: отсутствие sdd.md на пакете с обязательным arch-этапом — именованный INVALID_GATE (не тихий generic MISSING_INPUT), единственный законный проход без SDD — явный skip-факт из sdd-skip.md с `approved_by`, и этот проход не молчаливый (строка «arch: sdd skipped by <кто>» в required_gates). Все 8 новых тестов и полный регресс — **848 passed**. Оси фокуса проверены:

1. **Skip покрывает ТОЛЬКО MISSING — не расширен.** `skip_actor = _sdd_skip_actor(...) if sdd_status == "missing" else None` (flow_transition.py:557): при `unknown`/`invalid` факта `sdd.present` skip-актор не вычисляется вовсе, находки `out2` (MISSING_INPUT «источник нечитаем/непригоден») сохраняются → DENY. Подтверждено живой пробой: sdd.md как symlink наружу репо (→ STATUS_UNKNOWN через safe_read) + валидный sdd-skip.md → **DENY, INVALID_GATE в blocking_reasons**. Ключевой нюанс: `safe_read` различает «файла нет» (не проблема → MISSING) и «файл нечитаем» (проблема → UNKNOWN), так что битый sdd.md мимо skip не проскочит.
2. **Skip без `approved_by` — STATUS_INVALID, не молчаливый.** Три слоя: (а) `sdd_skip_fact` регэкспом `^approved_by:\s*(\S.*)$` (re.M|re.I) требует непустое значение — пустая строка/пробелы → `Fact(..., CONFIDENCE_VERIFIED, STATUS_INVALID)`; (б) `_sdd_skip_actor` пропускает только `status == "ready"` и непустой `value.approved_by` после strip; (в) при невалидном skip гейт падает в else-ветку с явным INVALID_GATE «sdd.md отсутствует…», который называет механизм легального skip. Проба: `approved_by:   ` (одни пробелы) → **DENY, INVALID_GATE**. Тест `test_skip_without_actor_is_invalid` фиксирует.
3. **Обратная совместимость — сохранена.** При sdd ready: `sdd_missing = False`, `out2` пуст, skip-строка не добавляется — гейт-вывод байт-в-байт прежний (тест `test_sdd_ready_unchanged` проверяет и ALLOW, и отсутствие «sdd skipped» в required_gates). Новый факт `sdd.approved_skip` добавлен в snapshot (flow_state.inspect), но все потребители — key-lookup (`_fact`), так что соседние гейты его не видят. Регресс 848 green, включая существующие тесты с `with_sdd=False` в test_flow_transition — прежние DENY-сценарии не сломаны (текст находки стал богаче: добавлен хвост про skip-механизм, но код INVALID_GATE и ядро сообщения прежние).
4. **Обход «написать sdd-skip.md без автора» — закрыт** (см. ось 2). Дополнительно: skip-файл, который нечитаем (symlink наружу), даёт UNKNOWN-факт `sdd.approved_skip` → `_sdd_skip_actor` → None → DENY; `had_problem`-логика в `sdd_skip_fact` корректно отделяет «не читается» (UNKNOWN) от «нет файла» (MISSING — нормальный путь, проблем не создаёт). Три возможных состояния skip-файла (нет / без автора / валидный) дают соответственно прежний DENY / DENY с явной подсказкой / ALLOW с записью — молчаливых состояний нет.
5. **Тесты реальные.** 8 кейсов на настоящих git-репо через проверенные хелперы test_flow_transition (`make_repo(with_sdd=False)`, `make_registry`, `snapshot_for`, `commit_all`), проверяют и код решения (DENY/ALLOW), и содержимое (INVALID_GATE в blocking_reasons, «sdd.md отсутствует» и упоминание sdd-skip.md/approved_by в details, точная skip-строка `arch: sdd skipped by pm` в required_gates, отсутствие skip-строки при ready). Fact-тесты покрывают все три статуса skip-файла. Негативные сценарии покрыты — не только happy-path.

Дополнительно сверено: `ctx` в `check_action` создаётся заново на каждый вызов (flow_transition.py:2104), так что `extra_gates` через `setdefault(...).append` не накапливается между решениями; паттерн идентичен существующим использованиям (строки 971, 1244, 1269, 1669). Подавление `out2` при skip правомерно: `out2` содержит только находки факта `sdd.present`, а штраф complete-set гасится сознательно (комментарий в коде это фиксирует), при этом `out0` (change-пакет) и `d_status` (дельты) при skip продолжают работать — skip не отменяет остальные ворота этапа.

## Замечания

| # | Файл:строка | Серьезность | Замечание | Рекомендация |
|---|---|---|---|---|
| 1 | flow_state.py `sdd_skip_fact` (регэксп approved_by) | minor | `approved_by` ищется в любом месте файла, включая код-блоки и цитаты: sdd-skip.md с примером «```approved_by: pm```» в fence будет распознан как валидный skip с автором pm. На практике файл на 3–5 строк и пишется вручную под этот формат, риск теоретический. | Не блокирует. При желании — парсить только строки верхнего уровня (без отступа) или зафиксировать формат решением (single-line front-matter). |
| 2 | tests/test_p17_arch_gate.py | minor | Нет теста на «UNKNOWN sdd.md + валидный skip → DENY» — ключевая граница оси 1 зафиксирована только кодом и моей live-пробой, не сьютой. Регрессия условия `if sdd_status == "missing"` (например, расширение на unknown) тестами не поймается. | One-liner в следующем касании: репо с sdd.md-symlink наружу + sdd-skip.md → assert DENY. |
| 3 | flow_transition.py `_arch_review_done` (сообщение DENY) | minor | При missing-sdd без skip разработчик получает ДВЕ находки: generic MISSING_INPUT из `_fact_ready` («факт „sdd.present“: отсутствует в снимке…») и именованный INVALID_GATE. Дублирование не ошибочное (одно — про факт, другое — про ворота), но читается как шум. | Не блокирует. Можно глушить generic-находку для sdd.present, когда добавлен именованный INVALID_GATE — по аналогии с гашением out2 при skip. |

## Проверено

- **Целевая сьют:** `pytest tests/test_p17_arch_gate.py -q` → **8 passed** (0.4s).
- **Полный регресс:** `pytest tests/ -q` → **848 passed** (120s), без регрессий.
- **Live-пробы (adversarial, вне сьюты):** (1) UNKNOWN sdd.md + валидный skip → DENY, INVALID_GATE; (2) `approved_by:` из одних пробелов → DENY, INVALID_GATE.
- **Граница MISSING/UNKNOWN:** `safe_read` (flow_state.py:144) — FileNotFoundError → (None, None) без проблемы (MISSING), symlink наружу/ OSError → проблема с `source=rel` (UNKNOWN); `sdd_skip_fact` и `sdd_fact` используют одинаковую `had_problem`-дисциплину.
- **Свежесть ctx:** `check_action` инициализирует `ctx` на каждый вызов — extra_gates не протекают между решениями.
- **Диф-гигиена:** изменений вне трёх заявленных файлов нет; тестовый файл изолирован, хелперы переиспользуют проверенную инфраструктуру test_flow_transition, `~/.hermes` и пользовательские репо не затрагиваются.

## Резюме

Вердикт **approve**: ворота стали честнее (MISSING sdd.md — именованный INVALID_GATE вместо тихого generic), явный skip — единственный обход и он подписан автором и отражается в гейт-выводе; все пять осей фокуса брифа подтверждены кодом, тестами и живыми пробами. Замечаний блокирующих нет: 3 minor (парсер approved_by вне fence-осведомлённости, отсутствующий негативный тест на UNKNOWN+skip, дубль находки при DENY) — в следующий docs/test-чип, не в реверт.
