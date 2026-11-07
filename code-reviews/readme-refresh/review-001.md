Commit: 00701500224ec7c5e32c450cbad5b14f07945125

Вердикт: Вернуть

Ревью ветки docs/readme-refresh (коммит выше, поверх origin/main 39d19a3):
README.md, docs/README-flow-control.md, skills/README.md, README роль-паков,
scripts/gen_role_docs.py, tests/unit/test_j65_pack_zone_docs.py. План —
PLAN-readme-refresh.md (Флоу 4). Ревьюер — независимый сабагент (Claude Code),
файлы репо не правил.

Итог: главный README и flow-control сверены с кодом, факты верны: раскладка
J66 (flow_check.py:373-387, режим warn/strict, битый файл — ошибка), этап
qa_automation во Флоу 2–5 сразу после первого этапа (flow_transition.py:1948-2030),
smoke `tests/unit/test_smoke.py` и `test-layout.json` в factory_init.py:471-485,
602-637, `test-layout.json` в защищенных путях (pm_bounds_check.py:69),
ограничение regress (flowctl.py:1820-1821). Генератор блока зон работает,
`gen_role_docs.py --check` — «таблицы актуальны», тесты
test_j65_pack_zone_docs.py + test_j65_roles_registry.py — 13 passed.
Вернуть из-за одного major: в README code-reviewer пример запуска остался со
старым путем review-файла и после правки зоны противоречит ей.

Проверки:
- `python3 scripts/gen_role_docs.py --check` → `gen_role_docs: таблицы актуальны`.
- `pytest tests/unit/test_j65_pack_zone_docs.py tests/unit/test_j65_roles_registry.py` → 13 passed.
- Регекс `PI_ZONE_WRITE='[^'\n]*'` применяется только к README паков из
  `pack_targets` (паки с политикой): двойные кавычки regress-runner
  (`PI_ZONE_WRITE="зона1:зона2"`, regress-runner/README.md:35) и
  `PI_ZONE_WRITE='<зоны-роли>'` в role-packs/README.md:64 не задеваются; debug и
  auditor не генерируются. Идемпотентность: `apply` заменяет все между
  маркерами, `apply_pack_example` дает фиксированную точку — повторный прогон
  без изменений (`--check` = 0).
- Префикс-форма блока совпадает с тем, что прокидывает раннер без `zones:` в
  манифесте: `policy_zones` подставляет change-id вместо `<id>`
  (package_runner.py:383-390), затем `normalize_zone` (package_runner.py:1608-1609);
  в README порядок обратный (normalize, потом `<id>` → C123) — результат тот же,
  `<`/`>` не glob-символы. Повторов префиксов в текущем реестре нет, поэтому
  дедупликация генератора (раннер не дедуплицирует) расхождения не дает.

## Замечания

| # | Серьезность | Где | Что не так | Как на самом деле | Рекомендация |
|---|---|---|---|---|---|
| 1 | major | skills/pm-factory/pi/role-packs/code-reviewer/README.md:59 | Бриф примера запуска: «Review-файл: test-model/reviews/C123/review-<задача>-001.md с маркером «Одобрить»/«Вернуть»». Строкой выше (56) — `PI_ZONE_WRITE='code-reviews/C123'`, блок зоны (24-25) и проза (31) — `code-reviews/<id>`. | Политика code_reviewer — `code-reviews/<id>/review-*.md` (agents/roles.json). По примеру ревьюер пишет вне `PI_ZONE_WRITE`, zone-guard отклонит запись, а под раннером session_check даст OUT_OF_ZONE. Плюс «маркером» противоречит строкам 35-36: вердикт читается только из заголовка `## Вердикт:` (flow_check.parse_verdict). Цель правки — свести README паков с политикой, а пример запуска в том же файле остался старым. | Бриф: «Review-файл: code-reviews/C123/review-<задача>-001.md с заголовком `## Вердикт: Одобрить|Вернуть` и строкой `Commit: <sha>`». |
| 2 | minor | README паков, общий абзац после блока (например dev/README.md:31, architect:31, code-reviewer:29, ba:31, design-validator:29, qa-impact-analyst:29) | «Обе строки задают ОДНУ зону». | Это верно только для glob-хвостов `/**`. Для зон с glob в середине или в имени `normalize_zone` дает префикс шире зоны (docstring package_runner.py:535-548): `code-reviews/<id>/review-*.md` → `code-reviews/<id>`, `test-model/reviews/<id>/review-*-architecture.md` → `test-model/reviews/<id>`, `docs/ba/*` → `docs/ba`, `test-model/impact/*.md` → `test-model/impact`, `test-model/bugs/*` → `test-model/bugs`. Раньше в блоках были только `/**`, и фраза была верной. Теперь сгенерированный блок ей противоречит в 6 паках. | Например: «env — префикс-форма той же зоны; для зон с маской в имени файла префикс шире (guard — грубая граница), точную сверку диффа делает session_check». Абзац общий, его можно добавить в генерируемый блок, чтобы не править 13 файлов руками. |
| 3 | minor | skills/pm-factory/pi/role-packs/sa/README.md:33 | «Вызывающий подставляет реальный change-id вместо `<id>` (раннер делает это сам из `package:` манифеста)». | Раннер подставляет `<id>` только в зоны, взятые из политики при отсутствии `zones:` (package_runner.py:447-451 → policy_zones). Явные `zones:` манифеста идут в `PI_ZONE_WRITE` без подстановки. | «(раннер делает это сам, если `zones:` в стадии не задан)». |
| 4 | minor | skills/pm-factory/pi/role-packs/README.md:49-50 | «расхождение J64.11 закрыто». | По README — да. Но промпты паков, которые раннер кладет в worktree как AGENTS.md, расходятся с политикой (code-reviewer/role-agents.md:12,15,27 — `test-model/reviews/**`; architect и devops — по плану тоже). Под раннером такой промпт отправляет запись за пределы guard-зоны. План переносит это «вне объема», но фраза «закрыто» это скрывает. | «…закрыто для README; промпты `role-agents.md` — отдельный пункт (J64.11/бэклог)». Остаток добавить в backlog, если его там еще нет. |
| 5 | minor | skills/pm-factory/pi/role-packs/qa-case-reviewer/README.md:35; design-validator/README.md:53; qa-case-reviewer/README.md:56 | (а) «зона `test-model/approved/**` входит в дефолт пака (вторая строка блока выше)»: вторая строка генерируемого блока — env-префикс, approved там во второй позиции первой строки. (б) Брифы «с маркером «Одобрить»/«Вернуть»». | Вердикт-ворота читают только заголовок `## Вердикт:` (J65.4). | (а) «входит в зону (блок выше)». (б) «с заголовком `## Вердикт: …`». |
| 6 | minor | skills/pm-factory/pi/role-packs/dev/README.md:38-39 | Подряд две скобки: «…(явные `zones:` манифеста только сужают политику) (или правит env под конкретный пакет)». | — | Объединить в одну фразу. |
| 7 | minor | docs/README-flow-control.md:332; README.md:393 | «TC-ID — только у приемочных уровней» / «обязателен для приемочных уровней». | Без TC освобожден только `unit` (`TEST_LAYOUT_NO_TC = ("unit",)`, flow_check.py:382). `smoke_cross` и `archive` тоже требуют TC-ID, но приемочными уровнями они не названы. | «TC-ID обязателен везде, кроме `tests/unit/`». |
| 8 | minor | scripts/gen_role_docs.py:106-109 | `_normalize_zone` вызывает `sys.path.insert(0, …)` при каждом вызове: около 50 вызовов на прогон, `sys.path` растет дублями. Импорт `package_runner` тянет `factory_paths`, `flow_check` и движок. Для `--check` в тестах это допустимо, но лишнее. | Функционально верно, `--check` работает. | Один импорт (на уровне модуля или с кэшем `functools.cache`) и `if path not in sys.path`. |
| 9 | minor | scripts/gen_role_docs.py:131, 147-151, 165-167 | (а) Пак с политикой, у которого README без маркеров `roles:pack-zone`, роняет весь прогон (и `--check`) с `ValueError` traceback без имени файла. (б) Пак из реестра без README тихо пропускается (`is_file()` в pack_targets). (в) `CHANGE_ID_PLACEHOLDER` объявлен после использующей его функции и дублирует `role_zone_policy.CHANGE_ID`. | Работает на текущем дереве. | (а) Ловить ValueError и печатать путь. (б) Предупреждать о пропуске. (в) Брать `rzp.CHANGE_ID` или объявить константу рядом с `EXAMPLE_ID`. |
| 10 | minor | scripts/gen_role_docs.py:124-127 | `apply_pack_example` заменяет ВСЕ `PI_ZONE_WRITE='…'` в README пака полной политикой. Пример с сознательно суженной зоной будет молча перезаписан. | Сейчас таких примеров нет, но в docstring это не сказано. | Одна строка в docstring/README паков: «примеры в одинарных кавычках — всегда полная политика; суженные примеры — в двойных кавычках». |
| 11 | minor | tests/unit/test_j65_pack_zone_docs.py:47-54, 31-43 | TC-J65-PZ-002 проходит вхолостую, если в README пака нет примера `PI_ZONE_WRITE='…'` (findall пуст). TC-001 сравнивает префиксы множеством, без порядка, и с `normalize_zone` реестра, а не с тем, что раннер отдает реально (`policy_zones` + normalize). Нет проверки, что генератор не трогает двойные кавычки и файлы вне pack_targets. | Заявленное в docstring (блок = политика, пример = префикс, debug/auditor не тронуты) проверяется. Регрессии регекса и пустые примеры не ловятся. | В TC-002 `assert values` для паков с примером запуска. Сравнивать префикс-строку целиком: `":".join(pr.normalize_zone(z) for z in pr.policy_zones(pack, "C123"))` против примера. Добавить кейс `apply_pack_example` на тексте с `PI_ZONE_WRITE="a:b"` — без изменений. |

## Что еще в README репозитория (п. 5)

Сверены agents/README.md (зоны dev/qa_automation J66, строки 28, 32, 110),
plugins/README.md, tests/README.md, agents/archive/README.md, skills/README.md:
устаревшего, относящегося к J65.1/J65.4/J66, не найдено, кроме уже названного
(code-reviewer README:59, брифы «с маркером» в паках ревьюеров). Пак debug
(debug/README.md:26, 51) не генерируется и сохраняет «Обе строки задают ОДНУ
зону» без блока зон. Это развилка J64.11, на нее ссылаются README паков.
Промпты `role-agents.md` расходятся с политикой (замечание 4). Это не README,
их надо зафиксировать в бэклоге.

## Вердикт: return
