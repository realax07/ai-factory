Вердикт: Одобрить

## Вердикт: approve

Ревью BUG-026 (Флоу 2): `factory_init` не копировал `scripts/flow_ids.py`.
Коммит `2b506848d115c772f50dd58fe4c8385bdbedb036`, ветка `fix/bug-026-init-flow-ids`.
Ревьюер — независимый сабагент code_reviewer (Claude Code), автор коммита — другой исполнитель.
Платформенного `deleg_<id>` у этой сессии нет, поэтому строки `Reviewer-Delegation` нет. Provenance-sidecar пишет ПМ (`gate_runner record-review`).

Blocker и major нет. Фикс полный: других мест, где нужен `flow_ids.py`, нет. Тест ловит класс дефекта и краснеет без фикса.

## Замечания

| # | Серьезность | Файл:строка | Сценарий | Рекомендация |
|---|---|---|---|---|
| 1 | minor | `tests/test_bug026_init_imports.py:49-50` | При падении TC-001 в `assert ..., missing` выводится весь словарь, вместе с пустыми списками всех 20+ скриптов. Нужная строка (`flow_state.py: ['flow_ids']`) тонет и обрезается: проверено, вывод без фикса начинается с `'scripts/factory_paths.py': []...`. | В сообщение отдавать отфильтрованный словарь: `bad = {k: v for k, v in missing.items() if v}; assert not bad, bad`. |
| 2 | minor | `tests/test_bug026_init_imports.py:60` | TC-002 импортирует standalone только 4 модуля. Остальные копируемые скрипты (`gate_runner`, `session_check`, `flow_mode`, `pr_validate`, `delegate_gate` и др.) по импорту закрыты только статикой TC-001. Ее не хватит, если скрипт импортирует модуль не из `scripts/` (не stdlib и не пакет). Проверено вручную: все 22 копируемых `.py` импортируются через `python -I` в изолированном каталоге, побочных эффектов нет. Расширение дешевое. | Параметризовать TC-002 по `Path(p).stem for p in COPIED`. |
| 3 | minor (вне зоны пакета, необязательно) | `docs/README-flow-control.md:240-256` | В таблице скриптов Flow Control нет `flow_ids.py` и `factory_paths.py`, хотя оба ставятся в проект и импортируются движком. Пробел появился до этого пакета. | Отдельный пункт Флоу 4: добавить строки `flow_ids.py` (flow_state/flow_transition/flowctl, import) и `factory_paths.py`. |

## Проверено

- Фикс (`scripts/factory_init.py:316`): `scripts/flow_ids.py` стоит первым в `FLOW_CONTROL_FILES`, до импортирующих его модулей. Цикл установки (`factory_init.py:497`) копирует отсутствующий файл и без `--force` (`dst.exists() and not args.force`). Значит, проект, поставленный до фикса, чинится обычным повторным `factory_init`, `--force` не нужен. Флаги `--skip-*` списка файлов не касаются.
- Полнота по импортам: `flow_ids` импортируют `flow_state.py:41`, `flow_transition.py:44` и (через них) `flowctl`. Все они в `FLOW_CONTROL_FILES`. Сам `flow_ids.py` зависит только от `re` и (внутри функции) `sys`.
- Ссылки копируемых скриптов на другие скрипты через subprocess и пути (`SCRIPTS / "flow_check.py"`, `pm_bounds_check.py`, `pr_validate.py` в gate_runner; `flowctl.py` в delegate_gate; `delegate_gate.py` в delegate_watchdog; `flow.yml`) ведут только в копируемые файлы. `importlib`, `runpy` и `spec_from_file_location` в копируемых скриптах не используются (единственный `__import__("os")` — stdlib).
- `check_mirrors.DEFAULT_FILES` (`scripts/check_mirrors.py:29`) сверяет только CI-автономные зеркала (`flow_check`, `pr_validate`, `impact_rules.json`, `factory_paths`). `flow_check` и `pr_validate` `flow_ids` не импортируют, так что `flow_ids.py` туда не нужен. Пробела нет.
- Энфорсер (`plugins/flow-enforcer/enforcer.py:168-182`) грузит `flow_ids` из `factory_home()/scripts`, а не из проекта, и при неудаче откатывается на встроенную копию. Фикс на него не влияет.
- AGENTS.md («скопируй `scripts/flow_check.py` и `flow.yml`», «проект — тонкий клиент»): `flow_check` от `flow_ids` не зависит, инструкция по-прежнему верна.
- `tests/test_audit_installer_crons.py:45` (TC-AUD-301) проверяет наличие отдельных файлов, добавленная строка его не ломает.
- AST-тест (TC-001): `ast.walk` обходит все узлы, поэтому видит импорты внутри функций и try/except (например, `import flow_check` в `flow_state.py:535`, `from flow_check import ...` в `pr_validate`). Относительные импорты (`level>0`) пропускаются. Это корректно: `scripts/` не пакет, относительных импортов в нем нет. Модули не из `scripts/` отсекаются пересечением с `local`, ложных срабатываний на stdlib нет. Есть слепая зона, малая и приемлемая: динамические импорты и модули вне `scripts/` (см. замечание 2).
- Standalone-проверка (TC-002): `-I` отключает PYTHONPATH, user-site и путь скрипта/cwd. stdlib при этом доступен, а копии зависят только от stdlib. `-I` воспроизводит голый проект строже, чем просто `cwd`, и это достоинство. HOME наследуется. Импорт `factory_paths` и движка ничего не пишет при import-time (mkdir в `factory_paths.py:214` стоит внутри функции). Тест к HOME не чувствителен.
- Прогон (pytest в окружении ревьюера недоступен, `No module named pytest` для python3.14/3.15). Тестовые функции запущены прямым раннером на python3.14:
  - HEAD `2b50684`: `PASS test_copied_scripts_bring_their_imports`, `PASS test_engine_copies_import_standalone`;
  - копия дерева (`git archive HEAD`) без строки фикса: `FAIL` у обоих; TC-002 — `flow_state.py line 41: import flow_ids` (ModuleNotFoundError).
- Standalone `python3.14 -I` импорт всех 22 копируемых `.py` в изолированном каталоге: все `ok`.

## Не проверено

- Полный сьют `ci_local` (1227 passed, 2 skipped) и `flow_check`: в окружении ревьюера нет pytest, принимаю по данным ПМ.
- Живой `factory_init --force` на реальном проекте (ekotov-wiki): поведение цикла установки проверено чтением кода.
- CI на PR.

## Закрытие minor (ПМ)

- №1: сообщение assert TC-BUG-026-001 — только файлы с недостающими импортами.
- №2: TC-BUG-026-002 импортирует все копируемые `.py`, а не 4 модуля.
- №3 (таблица скриптов в docs/README-flow-control.md) — в пакете актуализации документации (docs/refresh-2026-11).
