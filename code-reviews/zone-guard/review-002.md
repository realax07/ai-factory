# Code review 002: zone-guard (J64.10)

Commit: 200dda3 (диф `ab4fd39..HEAD`, исправления по review-001)
Ветка: chore/zone-guard
Ревьюер: code_reviewer (независимая сессия; автор диффа — другая делегация; платформенный deleg_id оркестратор не передал)
Прогоны: `python -m pytest tests/unit/test_j64_zone_guard.py tests/unit/test_package_runner.py tests/unit/test_installers.py tests/unit/test_j65_pack_prompt_zones.py tests/unit/test_j65_pack_zone_docs.py -q -p no:cacheprovider` — 123 passed, 0 skipped (node v25.9.0). Сравнение старого regex (`origin/main`) с новым guard'ом под node на наборе из 37 bash-команд. Пробы путей: `.git`/`.GIT`/`.Git`, symlink в зоне, висячий symlink, `src/etc/../x`, абсолютные пути. pi локально не установлен: семантику `--no-extensions` я не проверял, она принята по описанию в докладе (docs pi, CLI → Resources).
Итог: return. major-1 из review-001 закрыт, minor 1–4 и 6 закрыты, minor 5 закрыт частично. Новый major: переписанная bash-эвристика пропускает `git push` и docker-мутации, которые старый regex ловил.

Закрытие review-001:
- **major-1: закрыт.** `scripts/package_runner.py:2047-2050` запускает `--no-session --no-extensions -e <эталон>`. Тест проверяет флаг и то, что `-e` ровно один. Отключение прочих расширений на стадиях раннера допустимо и даже правильно: в settings всех паков есть только zone-guard, у auditor свой `-e auditor-readonly.ts`. README аудитора запрещает класть его в `~/.pi/agent/extensions/`, так что раннер его и раньше не грузил, регресса нет. Посторонние расширения хоста на стадии — неконтролируемый вход, и выключить их — плюс для детерминизма. MCP в pi по устройству не встроен (провайдеры — в `models.json`, не в расширениях). Если появится пак, которому расширение нужно, его придется передавать явным `-e` из репо, и это стоит записать в README паков.
- **minor-1: закрыт.** `.git/` закрыт для любой зоны, в том числе `*`/`**`. На регистронезависимой ФС macOS `.GIT/hooks/x` и `.Git/config` тоже получают отказ: realpath возвращает фактический регистр. Пробой проверено.
- **minor-2: закрыт** в заявленном объеме: symlink-каталог наружу (`src/etc -> /etc`) получает отказ. Остатки — в minor-2 ниже.
- **minor-3: закрыт.** Проба импортирует настоящий `.ts` с каждым набором флагов, так что ветка `--experimental-strip-types` теперь достижима.
- **minor-4: закрыт.** Добавлен `test_guard_paths_edge_cases`: экранирование, литерал `[`, абсолютные пути, `*`/`**` при `.git`, symlink наружу.
- **minor-5: закрыт частично.** Ловятся `compose -f x up`, `container/image rm`, `sudo docker`, `/usr/bin/docker`. Ложные блокировки `git commit -m "…push…"` и `git stash push` ушли. Но см. major-1 ниже.
- **minor-6: закрыт.** Комментарий о зеркале исправлен.
- **Асинхронный realpath в tool_call.** Обработчик `async`, pi его ждет. `realNearest` идет вверх до существующего предка и всегда завершается: на корне `parent === cur` дает выход. cwd тоже раскрывается (`/tmp` → `/private/tmp` на macOS), поэтому `rel` считается корректно. Ошибки fs ловятся, исключение наружу не уходит, гонок с состоянием нет: каждый вызов независим.
- **Ложные блокировки частых команд dev/qa: нет.** Проходят `pytest …`, `python -m pytest … 2>&1 | tail`, `git status/diff/log/commit/stash push`, `npm ci && npm test`, `npx playwright test`, `docker compose ps/logs -f`, `compose -f … ps`, `docker --version`, `docker inspect -f '{{…}}'`. Блокируются, как и раньше: `docker compose exec …` (мутация по решению) и `docker compose config`, ложно — см. minor-3.

## Замечания

### major

1. **skills/pm-factory/pi/zone-guard.ts:137-176 (`links`/`commandAt`/`gitPush`/`dockerMutation`): регресс запретов. Команды, которые старый regex блокировал, теперь проходят.** Проверено под node: старый regex дает PUSH/DOCK, новый guard — ok.
   - `if true; then git push; fi`, `for b in a; do git push origin $b; done`, `{ git push; }`, `! git push`: шелл-ключевые слова `then/do/else/{/!` не входят в префиксы, поэтому `commandAt` останавливается на них.
   - `timeout 60 git push`, `xargs git push`, `nice -n 10 docker rm x`, `timeout 30 docker compose up -d`: обертки `timeout/xargs` не в `PREFIX_WORDS`. У `nice -n 10` значение флага `10` принимается за слово команды.
   - `sudo -u ci git push`, `sudo -u root docker rm -f api`: значение флага `-u` принимается за слово команды.
   - `echo $(git push)`: токен `$(git` не очищается, ведущий `$` не снимается.
   - `sh -c "docker rm api"`: старый regex ловил, новый нет. `bash -c 'git push'` не ловил ни один.

   Почему это major: `git push` («запрещен всем») и docker-мутации («всем, кроме devops») — прямые решения Заказчика 2026-11-11. Ни push, ни docker-мутация не оставляют следа в git diff, так что сверка диффа на finish (J63) их не ловит, и на стороне агента guard остается единственным барьером. Формы `if …; then git push; fi` и `timeout N <cmd>` модели пишут часто. Охват запрета не должен становиться уже, чем у прежнего regex. Рекомендации:
   - в `commandAt` пропускать шелл-ключевые слова (`if then else elif do while until ! { (`) и обертки (`timeout`, `xargs`, `watch`, `stdbuf`, `ionice`, `doas`, `nice`), а также значения их флагов (`sudo -u X`, `nice -n N`, `timeout` с длительностью);
   - снимать префикс `$(` и обратные кавычки; для `sh|bash -c '<строка>'` рекурсивно проверять строку;
   - либо оставить старый regex страховкой для push и docker и разбирать токены только ради снятия известных ложных срабатываний (`commit -m`, `stash push`, `echo/grep` текста).

   Тест: все команды из этого списка дают block.

### minor

2. **zone-guard.ts:92-118: остатки symlink.**
   - (а) Висячий symlink в зоне: `src/dangling -> <вне worktree>`. `realpath` падает, `realNearest` берет предка `src`, и запись разрешена, хотя создала бы файл снаружи. Нужно проверять `lstat` последнего компонента и при symlink раскрывать `readlink`.
   - (б) `src/etc/../x` при `src/etc -> /etc`: `path.resolve` схлопывает `..` лексически и дает `wt/src/x`, запись разрешена. Если write-инструмент pi отдает путь в ОС без лексической нормализации, ядро запишет в `/x`. Нужно сверить, как pi резолвит `path`, либо отказывать при `..` в исходном `target`. Оба случая требуют, чтобы агент сначала сам создал symlink, поэтому это minor.
3. **zone-guard.ts:125-135: ложная блокировка `docker compose config`.** Для compose `config` — чтение (рендер файла), но `config` стоит в `DOCKER_GROUPS`, а после группы нет повторной проверки. Старый regex блокировал так же. Также `echo "pipe | docker rm x"` блокируется, потому что `links` режет по `|` внутри кавычек; это безопасно (fail-closed), просто учесть.
4. **tests/unit/test_j64_zone_guard.py:177-187: нет кейсов на формы из major-1** (`then/do/{/!`, `timeout`, `xargs`, `sudo -u`, `nice -n`, `$(…)`, `sh -c`) и на висячий symlink. Нужна таблица «старый regex блокировал → новый блокирует».

## Вердикт: return
