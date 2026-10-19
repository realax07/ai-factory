# Review-001 — J57-review (code review дифа: flowctl integrate + push_gate PM_PUSH_POLICY)

- **Задача:** J57-review (независимое code review, Флоу 4, scope=chore)
- **Ревьюируемая поставка:** ветка `chore/j57`, диф `main...HEAD`, коммит 0d6d1bb; 5 файлов, +645/-3 (scripts/flowctl.py, plugins/flow-enforcer/enforcer.py, tests/test_j57_j9_return.py, docs/README-flow-control.md, agents/README.md)
- **Reviewer-Delegation:** j57-review (Флоу 4, маркер flow=4 role=code_reviewer)
- **Метод:** чтение дифа против брифа по 5 осям фокуса (REFUSE активных сессий, идемпотентность ветки, честность маркер-проверки, легитимные пуш-пути, риск самоблокировки ПМ фабрики) + живые прогоны: целевой сьют (11 passed) и полный регресс фабрики (840 passed, 128s).

## Вердикт: approve

Поставка соответствует брифу и канону J9: сборка — детерминированная механика (`flowctl integrate`), merge/конфликты — семантика dev-lead, ПМ git продукта не трогает (механическая гарантия `PM_PUSH_POLICY`). Все 11 новых тестов и полный регресс фабрики — **840 passed**. Ось фокуса проверены:

1. **REFUSE активных сессий — честный.** `INTEGRATE_ACTIVE_STATUSES = ("reserved", "running", "needs_attention")` байт-в-байт синхронно с `WORKTREE_ACTIVE_STATUSES` энфорсера (enforcer.py:303); сверка кода подтвердила. Фильтрация `_session_in_repo` (repo/worktree, точное совпадение или префикс с `/` — без ложного «proj» ≈ «proj2») → REFUSE затрагивает только сессии этого репо (тест `test_integrate_active_session_of_other_repo_does_not_block`). Fail-closed: нечитаемый реестр → exit 2, ветка не создается.
2. **Идемпотентность — реальная.** Существующая `integration/<cid>` не пересоздается (exit 1, `INTEGRATION_BRANCH_EXISTS`); тест явно сдвигает origin/main вперед и проверяет, что ветка не перетерта (работа dev-lead'а не стирается). Имя ветки — та же деривация `branch_name_for` (`_branch_id_ok` + sha1-фолбэк), т.е. проверенная логика J52-w1.1, а не новая.
3. **cid-логика — консервативная.** Автовывод только при единственном correlation_id/change сессий репо; неоднозначно/пусто → `CID_REQUIRED` (exit 2), явный `--cid` спасает. Пустой реестр для репо не приводит к ветке с выдуманным именем — fail-closed.
4. **push_gate: легитимные пути не сломаны.** Делегированный пуш (ids непустой) идет прежним кодом — `pm_integration_gate` вызывается только при `not ids`; тест подтверждает ALLOW pipeline-ветки из worktree и по-прежнему DENY main из-под делегации `[PUSH_POLICY]`. Фабрика исключена дважды: прямая сверка с `factory_home()` в `_repo_is_product` (работает даже если factory попал в env-список — тест `test_push_gate_factory_excluded`) и фильтр `project == 'ai-factory'` в деривации. Пуш вне продуктового репо (не в списке/деривации) → `None`, прежнее поведение.
5. **Маркер-проверка честная.** `_head_integrated`: маркер в subject HEAD ИЛИ `merge-base --is-ancestor HEAD origin/main` — только remote-tracking; фолбэка на локальный main нет (и комментарий в коде объясняет почему: при пуше main локальный main и есть HEAD — проверка вырождалась бы в always-true). git недоступен → `(False, '')` — fail-closed DENY. Merged-путь без маркера покрыт тестом.
6. **Риск самоблокировки ПМ фабрики — снят.** ПМ фабрики пушит docs-заявки в конвейерное репо: `_repo_is_product` возвращает False для фабрики всегда (см. ось 4), `pm_integration_gate` в этом случае не находит offenders → `None`. Тест фиксирует.
7. **Дерево продуктовых репо — best-effort задокументирован.** `FLOW_ENFORCER_PRODUCT_REPOS` (env, приоритет) или деривация из реестра (project ≠ ai-factory с существующим `~/project/.git` — как `pm_bounds_check --all-projects`); оба пути и их статус описаны в docs/README-flow-control.md.
8. **Тесты реальные.** 11 кейсов на настоящих git-репо в tmp_path (init, commit, update-ref refs/remotes/origin/main, worktree), tmp-реестр и tmp-логи через autouse-фикстуру — `~/.hermes/state` и пользовательские проекты не затрагиваются. Проверяются побочные эффекты (ветка создана/не создана, куда указывает, HEAD репо не переключен), а не только код возврата.

## Замечания

| # | Файл:строка | Серьезность | Замечание | Рекомендация |
|---|---|---|---|---|
| 1 | enforcer.py `INTEGRATE_MARKERS` / `_head_integrated` | minor | Маркер ищется подстрокой в subject HEAD: коммит «fix упоминание [pipeline] в доке» прошел бы как интегрированный. Конвенция унаследована от J42 (pm_bounds-канон тех же маркеров), так что поведение консистентно с существующей политикой. | Не блокирует. При желании — `subject.startswith("[integrate] ")` / `("[pipeline] ",)` для строгого префикса, синхронно с pm_bounds_check. |
| 2 | enforcer.py `pm_integration_gate` | minor | Проверяется HEAD репо на каждый push-аргумент: пуш НЕ-HEAD ветки продуктового репо проверяется по чужому (HEAD) сабджекту/предку, а не по типу пушаемого ref. На практике ПМ пушит main (HEAD), и по брифу политика — про ПМ-push сборки; узкое место. | Не блокирует. При желании парсить refspec из `p["command"]` и сверять tip пушаемой ветки. |
| 3 | docs/README-flow-control.md (хвост таблицы) | minor | Строка «Прогон всего: … (446 green)» — устаревшая: фактический сьют 840 passed. Строка до-существующая (диф меняет соседнюю строку таблицы, число не трогал), расхождение не введено J57. | One-liner в следующем docs-чipped-коммите: 446 → актуальное число или убрать конкретную цифру. |
| 4 | flowctl.py `cmd_integrate` (cid-автовывод) | minor | При нуле сессий репо (все закрыты и вычищены из реестра) автовывод cid невозможен → exit 2 даже для валидного сценария «собрать после полного finish»; caller обязан звать с `--cid`. Это осознанный fail-closed (задокументирован в help), но UX-шероховатость. | Не блокирует. Можно добавить подсказку «сессии вычищены — укажи --cid явно» в note при пустом repo_sessions. |

## Проверено

- **Целевой сьют:** `pytest tests/test_j57_j9_return.py -q` → **11 passed** (0.7s).
- **Полный регресс:** `pytest tests/ -q` → **840 passed** (128s), без регрессий.
- **Синхронизация статусов:** `INTEGRATE_ACTIVE_STATUSES` (flowctl.py) ≡ `WORKTREE_ACTIVE_STATUSES` (enforcer.py:303) — сверено grep'ом, оба `("reserved", "running", "needs_attention")`.
- **Контракт статусов реестра:** `sc.registry_load` переиспользуется (тот же загрузчик, что у session_check); неизвестный статус не попадает в активные — консервативно против REFUSE, но это ok (REFUSE — про гонку с живой работой).
- **Доки ↔ код:** docs/README-flow-control.md («Делегация и сборка пакета (J57)») и agents/README №14 точно описывают префиксы пакета (`flow/`, `chore/`, `pipeline/`), статусы REFUSE, маркеры `[integrate]`/`[pipeline]`, env-переменную и деривацию — расхождений с кодом нет.
- **Границы команды:** `integrate` создает ветку локально, не пушит и не мерджит (в коде только `git branch <name> <base>`); подсказка в note честно отдает merge dev-lead'у.

## Резюме

Аккуратная, хорошо тестированная поставка: механика integrate — fail-closed по всем фронтам (реестр, cid, база), идемпотентность защищена тестом на стирание работы dev-lead'а; push_gate-политика не задевает ни делегированные пуши, ни конвейер фабрики, а дыра «локальный main как фолбэк» закрыта до того, как стала багом. Четыре minor — гигиена (подстрочный маркер, HEAD-vs-refspec, устаревший счетчик в доке, UX пустого реестра) — не препятствие для вливаения.
