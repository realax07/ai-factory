# Review-001: установщики фабрики (chore/installers)

Commit: 6b9f01f866543b2034fd3bbba5a73c3ee519fac7 (поверх origin/main 71cd9f2)
Диф: `git diff origin/main...HEAD` — scripts/factory_bootstrap.py, scripts/factory_init.py,
scripts/flow_check.py, scripts/pr_validate.py, README.md, agents/README.md,
docs/README-flow-control.md, tests/unit/test_installers.py, tests/unit/test_j58_impact_gate.py.
Ревьюер — независимый сабагент (Claude Code), автор кода — другой агент; файлы репо не правил.

Проверено прогоном (scratchpad, HERMES_HOME/AF_STATE_DIR/PI_AGENT_DIR — временные):
- `tests/unit/test_installers.py` + `test_j58_impact_gate.py` — 45 passed;
- `factory_init.py` на чистом git-репо без Hermes: плагин и кроны пропущены, `test-model/checklists`
  нет, шаблон в `templates/impact.template.md`, post-init flow_check exit 0 (rc=1 init — только из-за
  отсутствия openspec CLI на машине ревьюера);
- `factory_bootstrap.py --skip-tests` с временным Hermes: flow_mode.json в AF_STATE_DIR (не в
  HERMES_HOME/state), zone-guard скопирован, обертки в HERMES_HOME/scripts, crontab не пишется;
- обход `_x` (находка 1) — воспроизведен.

Итог: bootstrap и init по существу исправлены верно — файл режима теперь один с flow_mode.py
(STATE и flow_mode._STATE_DIR вычисляются из одного env при импорте, FLOW_MODE_FILE — на вызове
в обоих местах, не расходятся), системный crontab только читается, политика кронов 2026-10-23
соблюдена (обертки + таблица, delegate-watchdog «на паузе», digest — НЕ СОЗДАВАТЬ), models.json
проверяется только `is_file()`, zone-guard — filecmp без перезаписи. Импорт factory_init из
bootstrap побочных эффектов не дает (flow_check на уровне модуля — только regex/константы).
Ссылок на старый путь шаблона в действующих файлах (pr_validate, flow_preflight, impact_rules.json,
sa_agent.md, openspec-authoring, docs) не осталось. Возврат — из-за ослабления ворот flow_check.

## Замечания

| # | Серьезность | Где | Что не так | Рекомендация |
|---|---|---|---|---|
| 1 | major | scripts/flow_check.py:623-627 | Пропуск ЛЮБОГО каталога `openspec/changes/_*` снимает с него все проверки активного пакета: контракты 1/2 (requirements.md, proposal/design/tasks, дельты), sdd.md, J10 (ревью закрытых задач), и — главное — проверку `CHANGE_ID` (kebab-case), которая до этого коммита и закрывала такой каталог. Воспроизведено: `openspec/changes/_x/` с `proposal.md` и дельтой `specs/foo/spec.md` — старый flow_check: 5 FLOW-ERROR, новый: `OK`. `openspec validate --strict` дельту такого пакета принимает (если она корректна), `openspec archive _x` сольет ее в master-spec — изменение as-is мимо контрактов 1/2. flowctl такой scope не пропустит (flow_ids: `^[a-z0-9]+(?:-[a-z0-9]+)+$`), но flow_check — CI-ворота на мердже, и именно они должны ловить пакет, созданный руками. | Сузить исключение до легаси-шаблона: `d.name == "_template"` и в каталоге нет ничего, кроме `impact.md` (нет `specs/`, proposal/tasks) — тогда WARN «прежнее место шаблона, удали»; любой другой `_*` (или `_template` с дельтами) — как раньше, через все проверки (включая kebab-case ошибку). Тест: `_x` с дельтой → FLOW-ERROR; голый `_template/impact.md` → OK + WARN. |
| 2 | minor | scripts/factory_bootstrap.py:121-124; tests/unit/test_installers.py:79-80 | Явный `--flow-mode shadow` теперь понижает существующий enforcing (раньше `shadow` был дефолтом флага и существующий файл не трогал). Повторный bootstrap с флагом молча снимает боевой режим с `by=bootstrap-flag`; по AGENTS.md переключение режима — решение Заказчика. Новой дыры нет (`flow_mode.py set` доступен и так), но установщик не должен делать это незаметно; тест закрепляет понижение как норму. | При существующем файле и флаге, отличном от текущего режима, — не менять и печатать WARN «режим меняет Заказчик: flow_mode.py set … --by customer» (или требовать `--force-mode`); как минимум — WARN при понижении enforcing → shadow. |
| 3 | minor | tests/unit/test_installers.py:47-52 | `importlib.reload(flow_mode)` под monkeypatch-env навсегда переписывает `flow_mode._STATE_DIR`/`DEFAULT_MODE_FILE` (константы модуля) на tmp_path теста; monkeypatch откатывает env, но не модуль. Тот же объект модуля используют все последующие тесты сьюта (в т.ч. через `from flow_mode import …` — глобалы общие) — их дефолтный файл режима указывает в tmp_path чужого теста. Сейчас безвредно (последний reload — в тесте без файла режима → shadow), но порядок-зависимо. | Фикстура с teardown: после теста восстановить env и сделать `importlib.reload(flow_mode)`/`factory_bootstrap` повторно, либо вместо reload — `monkeypatch.setattr(flow_mode, "DEFAULT_MODE_FILE", …)` и `monkeypatch.setattr(fb, "STATE", …)`. |
| 4 | minor | tests/unit/test_installers.py:149-165 | TC-INST-005 заявляет «init OK», но rc процесса не проверяется (и не может — rc зависит от openspec CLI на машине). Проверяется только post-init flow_check. | Либо проверять отсутствие строк `FACTORY-INIT WARNING`, кроме ожидаемых, либо поправить формулировку TC («post-init flow_check exit 0»). |
| 5 | minor | scripts/factory_bootstrap.py:85, 116, 162 | Проверка `python < 3.10` недостижима: аннотация `str \| None` (state_dirs) вычисляется при определении функции, на 3.8/3.9 скрипт падает TypeError на импорте до check_env. | `from __future__ import annotations` в начале модуля. |
| 6 | minor | scripts/factory_bootstrap.py:67-73, 98-99 | Таймаут (60 с) сводится к rc 127 и печатается как MISSING/«нет» — для зависшего `pi`/`openspec` диагноз ложный. | Различать: таймаут → `TIMEOUT` (для обязательных — тоже fail, но с честным текстом). |
| 7 | minor | scripts/factory_init.py:615 | Комментарий шага 3a-4 по-прежнему говорит `openspec/changes/_template/impact.md`. | Заменить на `templates/impact.template.md`. |
| 8 | minor | skills/pm-factory/ai-factory-conveyor/references/flow-control.md:8 | Скилл ПМ: bootstrap ставит «вотчдог-крон» — после коммита неверно (обертки Hermes, crontab не правится). Рядом устаревшее `*/2` в docs/process-context.md:15 (политика — `*/5`), вне дифа, но та же тема. | Обновить строку скилла (и process-context) под политику кронов 2026-10-23. |
| 9 | minor | scripts/factory_init.py:81-84, 683-685 | «Hermes не найден» определяется по существованию каталога HERMES_HOME. Если Hermes ставится после init (каталога еще нет) — плагин и обертки молча не ставятся с текстом «не нужен». | Текст: «пропуск — каталога Hermes нет; поставишь Hermes — перезапусти init (или `--skip-plugin` явно)». README «Установка» — та же оговорка одной фразой. |
| 10 | minor | README.md (Установка, абзац bootstrap) | «ставит zone-guard исполнителя Pi (шаг 2)» читается как шаг bootstrap, у которого шаги 1/5…5/5 (zone-guard — 3/5). | «(см. шаг 2 ниже)». |

Проверенное без замечаний: check_env (rc/ok-логика, need_pytest = not --skip-tests, pytest через
`sys.executable -m pytest`), install_zone_guard (filecmp shallow=False, copy2, содержимое
models.json не читается), legacy_crontab_entries (только `crontab -l`, комментарии игнорируются,
нет crontab → []), setup_crons (WARN legacy, без Hermes — True без записи), main/exit-коды (0 —
только при env/pi/cron/tests ok), удаление `test-model/checklists` из MKDIRS (flow_state.py:396 и
flow_check.py:854 отсутствие каталога переносят — `is_dir()`), pr_validate/agents/README/
docs/README-flow-control — пути и описание точны.

## Вердикт: return
