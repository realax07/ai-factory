# Review-001 — J42-review (code review push-политики L2+L4)

- **Задача:** J42-review (независимое code review, Флоу 4, scope=chore)
- **Ревьюируемая поставка:** ветка `pipeline/j42-push-policy`, head 9d16a6d, диф против main (196380c): 6 файлов, +527/-3 (`.github/workflows/flow.yml`, `plugins/flow-enforcer/enforcer.py`, `plugin.yaml`, `tests/test_j42_push_policy.py`, `docs/README-flow-control.md`, `README.md`)
- **Reviewer-Delegation: deleg_j42-review** (метка флоу 4; финальная простановка ПМ при приемке — id из реестра делегаций)
- **Метод:** чтение полного дифа по 5 осям фокуса брифа + живые прогоны: J42-сьют (32 passed), полный регресс фабрики (829 passed, 125s), собственные adversarial-пробы парсера и ворот в изолированном env (subshell/backtick/`bash -c`/`env`-обертки, кавычки, `--force`/`--force-with-lease`, `HEAD:refs/heads/main`, `refs/heads/main:main`, `:refs/heads/<allow>`, табы, `+refspec`, kill-switch `no`).

## Вердикт: approve

Поставка соответствует брифу и решению Заказчика (слои L1+L2+L4): L2 — push-триггер `pipeline/**` с финальным падающим шагом `::error::` только для голого пуша без открытого PR (для main и PR-событий шаг нейтрален условием `if`); L4 — flow-aware перехват Bash `git push` только в контексте активной делегации, ALLOW-ветка из `session['branch']`, консервативный контекст при неизвестном cwd, деградация без ALLOW — пропуск + WARNING (не ломает ПМ-контур), kill-switch `FLOW_ENFORCER_PUSH` работает. Все 32 новых теста — реальные сценарии (парсер, хук, L2-структура workflow), регресс delegate_task покрыт. Полный регресс 829 passed — зеленый.

## Замечания

| # | Файл:строка | Серьезность | Замечание | Рекомендация |
|---|---|---|---|---|
| 1 | plugins/flow-enforcer/enforcer.py:401-404 (`_shell_segments`) + `parse_git_push` | **minor** | **Обход парсера обертками/подshell.** Проверено живьем: `(git push origin main)`, `` `git push origin main` `` (backtick), `bash -c 'git push origin main'`, `env git push origin main` → `parse_git_push` возвращает None (первый токен ≠ `git`) → ворота пропускают. Политика заявляет перехват «составных команд», но подshell-скобки и обертки не разбираются. Не блокирует: main реально защищает L1 ruleset bypass-never + branch protection (проверка GH013), а L4 — best-effort сигнальный слой (сабагент может пушить и через не-Bash инструменты); обход возможен только сознательный. | Либо задокументировать границу слоя в доке («L4 не защищается от оберток/подshell — защита main = L1»), либо дешевый hardening: pre-фильтр сегмента на подстроку `git push` перед проверкой первого токена (тогда обертки падают в conservative-deny «refspec не проверяем»). |
| 2 | .github/workflows/flow.yml:3-6 | minor | **Удвоение CI на PR сабагентских веток.** Пуш в `pipeline/**` при открытом PR запускает ОБА события: `push` и `pull_request` → jobs `flow` и `test-flow-control` выполняются дважды на каждый пуш ветки. Шаг J42 нейтрален, но дублирование целиком job'а (openspec validate + flow_check + полный pytest) — реальная нагрузка: сабагентские ветки пушатся часто. На main и PR--only ветки удвоения нет (там поведение прежнее). | `concurrency: { group: flow-${{ github.head_ref \|\| github.ref_name }}; cancel-in-progress: true }` — отменяет устаревший из параллельной пары прогонов; либо условие на job'ах `github.event_name != 'push' \|\| !startsWith(github.ref_name, 'pipeline/')` с выносом шага J42 в отдельный легкий job. Следующим chore. |
| 3 | plugins/flow-enforcer/enforcer.py:452-453 | info | `--force` / `-f` / `+refspec` / `--force-with-lease` игнорируются парсером → force-push в ALLOW-ветку разрешен. Это согласуется с заявленной политикой (проверяется только принадлежность ветке), но rewrite истории PR-ветки сабагентом возможен. | Зафиксировать в доке как осознанное решение (или добавить deny на force при желании ужесточить). |
| 4 | .github/workflows/flow.yml:117 | info | Гигиена: `BRANCH="${{ github.ref_name }}"` — прямая интерполяция контекста в run; имя ветки вида ``pipeline/`...` `` теоретически дает script injection (backtick/`$` валидны в git-ref). Актор — только свои сабагенты/ПМ, риск низкий. | Паттерн `env: BRANCH: ${{ github.ref_name }}` + `run: ...` (как уже сделано для `GH_TOKEN`). |
| 5 | tests/test_j42_push_policy.py:284-286 | info | Тест `test_final_step_fails_bare_pipeline_push` проверяет структуру YAML, но не семантику `gh pr list` (нет живого CI-прогона с фейковым GH_TOKEN) — поведение «0 открытых PR → exit 1» покрыто только чтением кода. | Опционально: e2e-проверка шага на `act`/манекене `gh` — при весе шага в 6 строк допустимо оставить как есть. |

## Проверено (по осям фокуса)

1. **push_gate не блокирует ПМ и не ломает delegate_task:** вне делегации (пустой реестр / реестра нет / статус не из `WORKTREE_ACTIVE_STATUSES`) — пропуск (тесты + живые пробы); flow-aware контекст корректен: ПМ в главном дереве при активной worktree-делегации НЕ блокируется, сабагент в worktree — блокируется; ветка без worktree владеет деревом repo; cwd неизвестен → консервативно все активные делегации; деградация «активная делегация без branch» → пропуск + WARNING (не fail-close ПМ-контур). Регресс `delegate_task` покрыт `test_delegate_task_still_validated` (strict-mode блок без маркеров жив) — хук ветвится по `tool_name` корректно, Bash без `git push` — без директивы.
2. **Обходы:** составные команды `&&`/`;`/`|`/`||`/`\n` разбираются посегментно, нарушение в любом сегменте → block (тест `test_composite_command_denied` + проба); `refs/heads/`-нормализация, `HEAD:<ветка>` и `origin <ветка>` — легальные формы; `HEAD:refs/heads/main` и `refs/heads/main:main` → dst=main → DENY; `:ref`/`-d`/`--delete` → DENY; `--all`/`--mirror`/`--tags`/`refs/tags/*`/`tag <x>` → DENY; голый `git push` / `git push origin` / `git push origin HEAD` → DENY «не проверяем»; `>2` refspec → DENY; `--dry-run` нейтрален (не меняет remote). Дыра оберток/подshell — замечание 1 (minor, не критично из-за L1). Кавычки вокруг ALLOW-ветки дают conservative-DENY (safe-направление).
3. **Kill-switch:** `FLOW_ENFORCER_PUSH` ∈ {0, false, no} → ворота полностью выключены (тест `test_disable_env` + живая проба `no`); прочие значения/отсутствие → включен.
4. **flow.yml:** push-триггер расширен только `pipeline/**`, `pull_request` не тронут; шаг J42 — последний в job flow, условие `github.event_name == 'push' && startsWith(github.ref_name, 'pipeline/')` — на main/PR событиях не выполняется; проверка по `gh pr list --head <branch> --state open` — именно ОТКРЫТЫЙ PR. Дубль job'а на PR-пушах сабагентских веток — замечание 2 (minor).
5. **Тесты:** 32 — реальные сценарии, не структурная шлифовка: 13 парсер-кейсов (включая негативные и `git pushx`), 15 хук-кейсов (DENY main/чужой/тег, композит, worktree-контекст обе стороны, деградация, kill-switch, не-Bash инструмент, регресс delegate_task), 4 L2-кейса на структуру workflow. Фикстуры изолированы (tmp-реестр/логи, без `~/.hermes/state`).

**Регресс фабрики:** `env -u GITHUB_EVENT_PATH pytest tests/ -q` → **829 passed** (125s; 797 до J42 + 32 новых — сходится).

## Что НЕ проверено (честно)

- Живой CI-прогон workflow с новым триггером (нужен пуш в remote; проверена структура YAML и семантика по коду).
- Поведение `gh pr list` при форк-PR/нескольких открытых PR с одной головой — не моделировалось.
- Конкурентный доступ к реестру делегаций во время чтения `active_push_context` — read-only, риск ограничен консервативным fail-open.

## Резюме

Поставка аккуратная и точно по брифу: L2 — детерминированный красный сигнал на голый пуш сабагентской ветки, L4 — умный ALLOW-гейт без ложных блоков ПМ-контура, с честной деградацией и рабочим kill-switch'ем; тесты и регресс зеленые (829). Два minor к следующему chore — задокументировать/поджать границу L4 против оберток-обходов и снять удвоение CI на PR-пушах `pipeline/**` через concurrency; три info — гигиена (force в ALLOW-ветку, интерполяция ref_name, e2e для gh-шага). Не блокирует вливание.
