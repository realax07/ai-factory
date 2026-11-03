Вердикт: Одобрить

# BUG-025 — ревью 001 (code_reviewer)

- Ветка: fix/bug-025-tests-usersite, коммит e7774368fe68c92a2f7be4976d52be14c9614a5f
- Флоу: 2 (багфикс). Вход: test-model/bugs/BUG-025-tests-usersite-home.md, PLAN-BUG-025.md
- Дифф: tests/conftest.py (+PYTHONUSERBASE в pytest_configure/unconfigure), tests/test_bug025_usersite_home.py (TC-BUG-025-001..004), репорт, план.

## Замечания

blocker/major — нет.

| # | Серьезность | Место | Сценарий | Рекомендация |
|---|---|---|---|---|
| 1 | minor | tests/conftest.py:127 | `PYTHONUSERBASE=""` (пустая строка) в окружении: `setdefault` ее сохраняет, а Python трактует пустое значение как «не задано» и считает user base из (фейкового) HOME — дефект воспроизводится. Экзотика, но дешево закрыть. | `if not os.environ.get("PYTHONUSERBASE"): os.environ["PYTHONUSERBASE"] = site.getuserbase()` (сохраненное старое значение для восстановления — как сейчас). |
| 2 | minor | tests/test_bug025_usersite_home.py:57-61 (TC-003) | В CI/venv pytest стоит не в user-site, поэтому TC-003 зеленый и без фикса (проверено мутацией: в режимах `-s`/PYTHONPATH он проходит). Дефект в CI ловят только TC-001 и TC-004. Ложной уверенности не создает, но в докстринге/репорте TC-003 подан как «прямой симптом». | Оговорить в докстринге TC-003, что он информативен только на user-site стенде; ловля в CI — за TC-001. |
| 3 | minor | tests/test_bug025_usersite_home.py:70-89 (TC-004) | При падении assert между `mod.pytest_configure(cfg)` и `mod.pytest_unconfigure(cfg)` каталог `af-test-home-*` из mkdtemp остается в системном tmp. Окружение не течет: HOME/PYTHONUSERBASE откатывает monkeypatch, HERMES_HOME — тот же экземпляр monkeypatch из `isolated_home` (откат к значению сессии). | Опционально: try/finally вокруг пары configure/unconfigure. |
| 4 | minor (инфо) | tests/conftest.py:127 | Подпроцессы теперь видят реальный user base: `pip install --user` из теста писал бы в реальный ~/.local (или ~/Library/Python), а импорт user-site модулей может писать `__pycache__` туда же. В текущем сьюте `pip`/`--user` в тестах нет (grep tests/ scripts/), это ожидаемое поведение фикса — state (HOME/HERMES_HOME) по-прежнему изолирован. | Ничего не делать; при появлении тестов с pip — изолировать их PYTHONUSERBASE отдельно. |

## Разбор по существу

- **Кэширование `site.USER_BASE`.** `site.getuserbase()` вызывается в `pytest_configure` до подмены HOME, значение кэшируется в модуле `site`; повторные вызовы (в т.ч. в TC-004 после monkeypatch HOME) возвращают реальный base — это и нужно. Проверено: на python3.14 даже при `-s` `site.USER_BASE` вычислен при старте (`python3.14 -s -c "import site; print(site.USER_BASE)"` → реальный путь).
- **venv / ENABLE_USER_SITE=False.** Дочерний интерпретатор venv игнорирует user-site, PYTHONUSERBASE безвреден. Эмуляция (`-s` + PYTHONPATH): фикс 4 passed.
- **`python -s` / PYTHONNOUSERSITE.** PYTHONNOUSERSITE наследуется подпроцессом — user-site выключен, фикс не мешает (4 passed). `-s` не наследуется `sys.executable`-подпроцессом: ребенок увидит реальный user-site — так же, как до J64.2, не регрессия.
- **PYTHONUSERBASE задан заранее.** `setdefault` не трогает, unconfigure восстанавливает прежнее (TC-004 вторая половина; прогон с предзаданным PYTHONUSERBASE и пустым HOME — 4 passed). Исключение — пустая строка (замечание 1).
- **macOS framework vs Linux.** Ребенок — тот же `sys.executable`, схема `osx_framework_user` (`{base}/lib/python/site-packages`) или `posix_user` (`{base}/lib/python3.X/site-packages`) одинакова у родителя и ребенка; TC-001 сравнивает итоговый `getusersitepackages()`, а не формулу. На Linux base = `~/.local` из HOME — тот же механизм дефекта, фикс применим.
- **Изоляция state.** HOME и HERMES_HOME по-прежнему временные (TC-002 сравнивает `Path.home()` ребенка с env HOME и с реальным HOME из `_factory_home[1]`).
- **TC-004 и окружение сьюта.** Импорт копии conftest без побочных эффектов уровня модуля (только определения; фикстуры не регистрируются — модуль не плагин). Каждый configure/unconfigure — парный, mkdtemp удаляется rmtree. После теста monkeypatch возвращает PYTHONUSERBASE/HOME/HERMES_HOME сьюта. Утечек в окружение сьюта не найдено.
- **Трассировка.** TC-BUG-025-001..004 в докстрингах тестов и модуля — по образцу test_bug024_regress_meta_fresh.py; репорт и план ссылаются на диапазон.
- **Расхождение формата.** Первая строка выполнена по требованию оркестратора (`Вердикт: Одобрить`); роль-промпт (code_reviewer_agent.md, J10/J52) требует `## Вердикт: approve` и `Reviewer-Delegation:` — если ворота парсят этот файл, ПМ должен сверить формат.

## Проверено (команды и факты, 2026-11-03)

- `HOME=<scratchpad>/vps-home python3.14 -m pytest tests/test_bug025_usersite_home.py -q -p no:cacheprovider` (worktree, фикс): 4 passed.
- Мутация (копия дерева `git archive e777436`, строка `setdefault` заменена на `pass`):
  - стенд user-site (pytest только в user-site): 3 failed (TC-001, TC-003, TC-004), 1 passed;
  - CI-подобно (pytest через PYTHONPATH, user-site включен): 2 failed (TC-001, TC-004);
  - venv-подобно (`-s` + PYTHONPATH): 2 failed (TC-001, TC-004).
  Вывод: TC-001 ловит дефект во всех трех режимах, не только на стенде.
- Фикс в режимах `-s`+PYTHONPATH, PYTHONPATH, PYTHONNOUSERSITE=1, предзаданный PYTHONUSERBASE + пустой HOME: 4 passed в каждом.
- `python3 scripts/flow_check.py .` (worktree): OK.
- grep `pip|--user|PYTHONUSERBASE|getuserbase` в tests/ и scripts/: тестов с pip --user нет.

## Не проверено

- Реальный venv (эмулирован `-s`; venv в среде нет, ставить пакеты не стал).
- Linux/VPS и python ≠ 3.14 — только рассуждение по схемам sysconfig; подтверждение на VPS — за Заказчиком (по плану).
- Полный сьют и j51/j52/j54 — не повторял, по данным ПМ (59 passed на стенде; 1129 passed, 2 skipped полный).
- `openspec validate --all --strict` — не гонял (спеки не менялись).
- CI (GitHub Actions) — не запущен на момент ревью.

## Закрытие minor (ПМ, после ревью)

- №1 пустой `PYTHONUSERBASE`: `setdefault` заменен на `if not os.environ.get(...)`; TC-BUG-025-004 дополнен случаем `""`.
- №2 TC-003: в докстринге оговорено, что тест информативен только на user-site стенде; в CI/venv дефект ловит TC-001.
- №3 TC-004: цикл configure/unconfigure в try/finally — временный HOME удаляется и при падении assert.
- №4 (информационно) — без изменений.
- Формат файла (`Вердикт: Одобрить` против `## Вердикт: approve` J52) — известное расхождение, вынесено в J64.12/J65.4.

Прогон после правок: стенд user-site, полный сьют — 1129 passed, 2 skipped; flow_check OK.
