# Code review 003: zone-guard (J64.10)

Commit: 323b262 (диф `200dda3..HEAD`, исправления по review-002)
Ветка: chore/zone-guard
Ревьюер: code_reviewer (независимая сессия; автор диффа — другая делегация; платформенный deleg_id оркестратор не передал)
Прогоны: `python -m pytest tests/unit/test_j64_zone_guard.py tests/unit/test_package_runner.py tests/unit/test_installers.py tests/unit/test_j65_pack_prompt_zones.py tests/unit/test_j65_pack_zone_docs.py -q -p no:cacheprovider` — 123 passed, 0 skipped (node v25.9.0). Под node сравнил старый regex (`origin/main`) с новым guard'ом: набор review-002 (36 команд) плюс 39 новых — `\t`, `\`-перенос, `command`, кавычки в значениях флагов, алиасы, grep/rg по слову docker, compose с `-p`/`--env-file`, `docker-compose`, `make`/`npm run`. Пути: `.git`/`.GIT`/`.Git`, symlink наружу, висячий symlink, цепочка висячих, петля symlink, `..` в разных формах, `..foo`, абсолютный путь, глубокий несуществующий хвост.
Итог: return. major-1 из review-002 закрыт по всему набору, minor 2–4 закрыты. Новый major — регресс против старого regex: значение флага в кавычках и перенос строки `\` прячут `git push`.

Закрытие review-002:
- **major-1 закрыт.** Все 13 форм обхода из review-002 блокируются: `then/do/{/!`, `timeout`, `xargs`, `sudo -u`, `nice -n`, `$(…)`, `` `…` ``, `sh -c`, `bash -c`. Ни одна команда, которую блокировал старый regex, из набора review-002 не проходит. Пропускаются только намеренно снятые ложные срабатывания: `git commit -m "…push…"`, `git stash push`, `docker compose config`.
- **minor-2 закрыт.** Висячий symlink наружу и цепочка висячих получают отказ. `..` в любой форме (`src/a/../b.py`, `src/etc/../x`, `src\..\x`) — тоже отказ. `src/..foo/a` при этом разрешен: проверяется сегмент `..`, а не подстрока. Регистр `.git` не важен.
- **minor-3 закрыт.** `docker compose config` и `config --services` проходят.
- **minor-4 закрыт.** Формы обхода из review-002 и висячий symlink покрыты тестами.
- **Новые формы из запроса.** `git\tpush`, `command git push`, `nohup git push &`, `git --no-pager push`, `printf … | git push`, `git push 2>&1 | tail` блокируются. `eval 'git push'` тоже блокируется. Алиасы через переменные (`G=git; $G push`) проходят — это честно вне охвата, как и сказано в шапке. Сверх прежнего теперь ловятся `docker compose -p proj up` и `echo "… | docker rm"` (fail-closed).
- **Ложные блокировки частых команд dev/qa:** pytest, `git status/diff/log/commit/stash push/grep`, `git log --grep=push`, npm/npx, `make docker-up`, `npm run docker:build`, `docker compose ps/logs/config`, `docker ps --format '{{…}}'`, `docker inspect -f`, `docker --version`, `which docker`, `cat services/docker/compose.yml`, `ls deploy/docker` проходят. Ложно блокируется поиск по слову docker — см. minor-2.

## Замечания

### major

1. **skills/pm-factory/pi/zone-guard.ts:181-185 (`tokensAfter`): звено обрывается на кавычке и на переводе строки. Значение флага в кавычках и перенос `\` прячут подкоманду.** Проверено под node (старый regex: PUSH, новый guard: ok):
   - `git -C "$WT" push`
   - `git -C '/a b' push`
   - `git -c "user.name=x" push`
   - `git -C"x" push`
   - `git \⏎  push origin HEAD` (перенос строки)

   После `-C` токенов нет, потому что звено закончилось на `"`, и `subcommand` возвращает пустую строку. `git -C "$WT" push` — частая форма именно в этом конвейере (пути worktree). Перенос `\` — частая форма длинных команд. Старый regex ловил обе, а `git push` (решение Заказчика «всем») в git diff не оставляет следа. Та же причина у `docker compose -f "deploy/x.yml" up -d` и `docker compose --env-file '.env' down`: старый regex их тоже не ловил, но в шапке они заявлены как пойманные («`compose -f x up` — отказ»). Рекомендации:
   - до разбора склеивать `\`+перевод строки в пробел;
   - в `tokensAfter` не обрывать звено на `"`/`'`, а снимать кавычки с токенов. Закрывающую кавычку `sh -c "…"` это не ломает: `api"` после очистки — обычный аргумент;
   - флаги со склеенным значением (`-C"x"`, `-C/path`) пропускать как флаги — это уже работает, проблема только в обрыве на кавычке.

   Тест: все пять форм выше плюс два docker-примера в blocked.

### minor

2. **zone-guard.ts:200-210 (`dockerMutation`): неизвестная подкоманда считается мутацией, и поиск по слову docker блокируется у dev/qa.** Блокируются `grep docker README.md`, `grep -rn docker scripts/`, `rg -n docker deploy`, а также надуманный `pytest tests/docker -k run`. Решение fail-closed, вреда нет, но частый поиск стоит агенту итерации. Можно пропускать вхождение, если перед ним стоит `grep`/`rg`/`ag`/`echo` того же звена, или хотя бы упомянуть в тексте отказа «закавычь слово: grep 'docker'».
3. **zone-guard.ts:94-95 (`realResolve`): петля symlink (`src/loop -> loop`) после 40 уровней возвращает исходный путь, и запись разрешена.** Ядро ответит ELOOP, файл не появится, поэтому это не дыра. Fail-closed здесь — вернуть отказ: например, `realResolve` возвращает `null`, а `inWriteZone` отдает `false`.

## Вердикт: return
