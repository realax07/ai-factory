# Code review 002: state-backup (J64.6)

Commit: 9a2fdfdc4083ea0f81df384166156b43be0b61de (ветка chore/state-backup; диф к review-001 — `git diff 9e0a020 9a2fdfd`)
Ревьюер: независимый сабагент code_reviewer (Claude Code); автор — другой агент. Файлы репо не правил.

Повторная проверка находок review-001. Репро major-находок повторены во временных каталогах (реальные ~/.hermes и ~/ai-factory-backups не трогались); tests/unit/test_j64_state_backup.py — 12 passed.

## Статус находок review-001

| # | Было | Статус | Проверка |
|---|---|---|---|
| 1 | major: restore без каталога `state/` разрушал state | исправлено | Пустой архив и архив с `state` типа файл → `RuntimeError: в архиве нет каталога state/`, `main` → exit 1 с «ОТКАЗ»; прежний state на месте (содержимое сохранено), сиротских `*.restore-*`/`*.before-restore-*` нет. Добавлена проверка после распаковки и откат второго rename (scripts/state_backup.py:175-193). |
| 2 | major: симлинк-state → пустой архив | исправлено | backup симлинка: `['state', 'state/flow_mode.json']`; после записи архив проверяется на `state/`, при сбое `.part` удаляется (стр. 115-125). |
| 3 | статусы, держащие зоны; реестр-список | исправлено | `HOLDING_STATUSES` включает finished/needs_attention; `[]` не падает. |
| 4 | `.part` и OSError при backup | исправлено | try/except вокруг записи, `.part` удаляется, OSError → RuntimeError. |
| 5 | права архива | исправлено | архив 0600, каталог 0700 (проверено). |
| 6 | коллизии имен в одну секунду | исправлено | `_unique`: два restore в одну секунду → `before-restore-<ts>` и `-1`. |
| 7 | сортировка/ротация | исправлено | `AUTO_RE` + ключ (ts, n); ротация трогает только автоматические имена. |
| 8 | команды RUNBOOK | исправлено | `session_check.py reconcile --registry …`, `factory_init.py --target … --name …`. |
| 9 | FLOW_MODE_FILE/FLOW_ENFORCER_STATE_DIR вне state | задокументировано | docstring и RUNBOOK. Принимаю. |
| 10 | тесты | исправлено | добавлены кейсы пустого архива, state-файла, симлинка, прав, ротации. |

## Новые замечания

| # | Серьезность | Где | Что не так | Рекомендация |
|---|---|---|---|---|
| 1 | minor | scripts/state_backup.py:184-186, main | `state.rename(previous)` вне try: при его OSError (права на родителя) — трейсбек вместо «ОТКАЗ», staging остается сиротой; state при этом не тронут. `main` ловит только RuntimeError. | Обернуть rename в тот же try с rmtree staging, либо в `main` ловить и OSError. |
| 2 | minor | scripts/state_backup.py:184-188 | Restore поверх state-симлинка заменяет ссылку обычным каталогом в месте ссылки (проверено: `is_symlink False`), данные цели ссылки остаются в `before-restore-*` (симлинк). Если state был вынесен на другой диск ссылкой, после restore он оказывается на диске ссылки. | Строка в RUNBOOK или restore в `state.resolve()`; не блокирует. |

## Вердикт: approve
