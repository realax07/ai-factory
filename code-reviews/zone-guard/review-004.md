# Code review 004: zone-guard (J64.10)

Commit: f1ad90f (диф `323b262..HEAD`, исправления по review-003)
Ветка: chore/zone-guard
Ревьюер: code_reviewer (независимая сессия; автор диффа — другая делегация; платформенный deleg_id оркестратор не передал)
Прогоны: `python -m pytest tests/unit/test_j64_zone_guard.py tests/unit/test_package_runner.py tests/unit/test_installers.py tests/unit/test_j65_pack_prompt_zones.py tests/unit/test_j65_pack_zone_docs.py -q -p no:cacheprovider` — 123 passed, 0 skipped (node v25.9.0). Под node сравнил старый regex (`origin/main`) с guard'ом на трёх наборах: 36 команд review-002, 39 команд review-003 и 42 новые (обходы через исключение текстовых команд, pipe в шелл, `rg --pre`, кавычки, `\`-перенос, ложные блокировки). Пути: петля symlink, висячий symlink.
Итог: approve. major-1 и minor 2–3 из review-003 закрыты. Новых blocker/major нет, остаётся три minor.

Закрытие review-003:
- **major-1: закрыт.** Блокируются `git -C "$WT" push`, `git -C '/a b' push`, `git -c "user.name=x" push`, `git -C"x" push` и `git \⏎ push`. Сверх старого regex теперь ловятся `docker compose -f "deploy/x.yml" up -d` и `--env-file '.env' down`, а также `docker compose -p proj up`. Тесты покрывают все эти формы.
- **minor-2: закрыт.** `grep docker README.md`, `grep -rn docker scripts/`, `rg -n docker deploy`, `egrep 'docker (rm|run)'` и `/usr/bin/grep docker f` проходят.
- **minor-3: закрыт.** Петля symlink получает отказ (`realResolve` → null).
- **Обходы через исключение текстовых команд: не найдены.** Блокируются `echo x; git push`, `grep x && git push`, `grep x f || git push`, `(grep x f) && git push`, `printf '%s' "$(git push)"`, `rg $(docker rm a)`, `echo x | xargs git push`, `grep -e x -e 'y' $(git push)`, `` echo `git push` ``, `echo "$(docker rm a)"`, `grep x | docker rm a`, `echo done⏎git push`, `grep -rn "docker" . && docker rm x`.
- **Против старого regex.** Сравнение по всем трём наборам: старый regex блокировал, новый guard пропускает только (а) намеренно снятые ложные блокировки — `git commit -m "…push…"`, `git stash push`, `git grep push`, `docker compose config [--services]`, `echo docker rm`, `echo "use: git push" >> notes.md`; (б) pipe строки в шелл — см. minor-1.
- **Ложных блокировок частых команд dev/qa нет.** Остались только безопасные: `git commit -m 'docker rm'`, `git commit -m "a; git push"`, `LC_ALL=C grep docker f`, `echo ${HOME} git push`. См. minor-3.

## Замечания

### minor

1. **skills/pm-factory/pi/zone-guard.ts (`inTextCommand`/`TEXT_COMMANDS`): pipe текста в шелл.** Проходят `echo git push | sh` и `echo 'docker rm a' | sh -s`, которые старый regex ловил. `printf 'git push' | bash` не ловили ни старый regex, ни новый guard. Это тот же класс косвенного вызова, что и `G=git; $G push` (честно вне охвата). Нечаянно агент так не пишет, но это типичный обход после отказа. Простое исправление: не применять исключение текстовой команды, если в строке есть pipe в интерпретатор (`|\s*(sudo\s+)?(sh|bash|zsh|dash|ksh)\b`). Тест: обе формы в blocked.
2. **zone-guard.ts (`TEXT_COMMANDS`): `rg --pre <cmd>` и `ack --pager <cmd>` исполняют команду.** Например, `rg --pre 'git push' x` проходит. Это надуманная форма, вне охвата эвристики; достаточно строки в «Ограничение (честно)» в шапке.
3. **Безопасные ложные блокировки.** Слово, стоящее после кавычки, считается вызовом: `git commit -m 'docker rm …'` и `git commit -m "a; git push"` получают отказ, хотя это текст сообщения коммита. Префикс `VAR=val` перед grep (`LC_ALL=C grep docker f`) не распознается как текстовая команда. Это fail-closed, вреда нет. Если в прогонах будут жалобы, можно пропускать вхождения внутри аргумента `-m`/`--message` у git и снимать `VAR=val` перед первым словом в `inTextCommand`.

## Вердикт: approve
