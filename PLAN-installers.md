# PLAN-installers: исправление установщиков фабрики

**Флоу: 4** — обслуживание: установщики `factory_bootstrap.py` (машина) и
`factory_init.py` (проект); правила конвейера не меняются.

## Задача

Заказчик (2026-11-07): «поправь также инсталляторы фабрики». Сверка
установщиков с текущими правилами (политика кронов 2026-10-23, пути машины
J64.5, J23, J58, J66) и прогон init на чистом проекте.

## Найдено и исправлено

- **bootstrap ставил системный crontab** (`*/2 session_watchdog`,
  `*/5 delegate_watchdog`) вопреки политике кронов 2026-10-23 (кроны Hermes
  через обертки-делегаты, session-watchdog `*/5`, delegate-watchdog на
  паузе). Теперь: обертки `factory_init.install_crons` + таблица
  рекомендуемых кронов, только при наличии Hermes; crontab не правится,
  записи прежнего bootstrap — WARN «удалить вручную».
- **bootstrap писал flow_mode.json в `HERMES_HOME/state`** мимо
  `AF_STATE_DIR` и `FLOW_MODE_FILE` — движок читал другой файл. Теперь —
  `flow_mode.mode_file()/set_mode()`; существующий режим без флага не
  меняется.
- **bootstrap не проверял OpenSpec и Pi**, pytest искал в PATH, а не в
  своем python. Теперь: openspec (рекомендуемая 1.14.0), node/npm, pytest
  через `sys.executable -m pytest`, `pi` (WARN); zone-guard Pi ставится в
  `PI_AGENT_DIR/extensions/` (отличающаяся копия не перезаписывается),
  наличие `models.json` — подсказка. Флаг `--skip-pi`. Описание `--with-e2e`
  несуществующего флага убрано.
- **factory_init: post-init ворота нового проекта были красные** — шаблон
  impact-карты J58 лежал в `openspec/changes/_template/`: `flow_check`
  (контракты 1/2) и `openspec validate --strict` («Change must have at least
  one delta») принимали его за change-пакет. Шаблон перенесен в
  `templates/impact.template.md`; `flow_check` пропускает только легаси `_template/`
  с одним `impact.md` (WARN); прежнее место — WARN и в init.
- **factory_init создавал упраздненный `test-model/checklists`** (J23) — убран.
- **factory_init без Hermes** ставил плагин и обертки кронов в несуществующий
  `~/.hermes` — теперь оба шага пропускаются с пометкой (оркестратор —
  другой кодагент).
- Шапка `factory_init` — актуальный состав установки; README «Установка»,
  реестр скриптов в docs/README-flow-control.md, agents/README.md (путь
  шаблона), pr_validate (подсказка пути шаблона).

## Возврат ревью review-001 (1 major, 9 minor) — исправлено

Пропуск `openspec/changes/_*` снимал контракты 1/2 с любого такого каталога
(change `_x` уходил из-под ворот) — сужен до легаси-шаблона: `_template/` с
единственным `impact.md` (WARN «удали каталог»), любой другой `_*` —
проверяется как пакет (TC-INST-006). Явный `--flow-mode shadow` при боевом
enforcing — WARN; `from __future__ import annotations` (проверка python <
3.10 достижима); таймаут команды — не «MISSING»; подсказка «поставишь Hermes
— перезапусти»; изоляция reload-модулей в тестах; TC-INST-005 проверяет rc;
устаревшие тексты: скилл flow-control (bootstrap и вотчдог-крон),
process-context (`*/2` → `*/5` через обертку), README.

## Тесты

TC-INST-001…006 (`tests/unit/test_installers.py`); TC-J58-019 — шаблон не под
`openspec/` [test-adapted].

## Внимание при выкатке

На VPS: если в системном crontab есть записи `session_watchdog.py` /
`delegate_watchdog.py` от старого bootstrap — удалить (`crontab -e`); кроны —
через Hermes (`docs/README-flow-control.md`, «Кроны и вотчдоги»).

## Критерий закрытия

Полный сьют зеленый, init на чистом проекте — post-init flow_check OK и
`openspec validate --all --strict` OK, ревью approve, CI зеленый.
