Вердикт: Одобрить
Ревьюер: code_reviewer (сабагент Claude Code)
Коммит: fde64ce05190fbe17305d4b685cdf4f6f10e2e28
Пакет: repo-cleanup (Флоу 4), план — PLAN-repo-cleanup.md

# repo-cleanup — ревью 001

Ревью статическое, адверсариальное: «что сломается после удаления/переноса».
Blocker и major нет. Есть 4 minor, все про точность текста. Поведение
конвейера ни одно из них не ломает.

## Замечания

| # | Серьезность | Файл:строка | Суть / сценарий отказа | Рекомендация |
|---|---|---|---|---|
| 1 | minor | backlog/J64-ТЗ-по-итогам-аудита-2026-11-02.md:340 | «7,1 МБ → ~5,1 МБ»: это `du` (место на диске с округлением до блоков, `du -sh skills` = 5.1M). Объем отслеживаемого текста по `git ls-tree -l`: 7 224 272 → 4 820 788 байт, то есть 6,89 → 4,60 МиБ (7,22 → 4,82 МБ). Цифра «~5,1» завышена примерно на 0,5 МБ относительно текста. Если сравнивать с другими замерами, получится, что удалено меньше, чем на самом деле. Подтверждаю наблюдение ПМ про ~4,6 МБ. Счет файлов 495 → 236 верный. | Следующей append-строкой (не правкой: правило append-only) уточнить «текст 6,9 → 4,6 МиБ (du 7,1 → 5,1 МБ)», либо указать, какой метрикой мерили. |
| 2 | minor | PLAN-repo-cleanup.md:23; backlog/J64-…:348 | «граф `backend/app` (4 узла)»: в удаленном `codegraph.json` `meta.py_dir` = `backend/app`, но все 4 узла — модули `scripts.*` (check_auth_timing, codegraph, flow_check, pr_validate). Это граф скриптов, а не `backend/app`. На решение не влияет: файл никто не читает. | При следующей записи в J64 писать «устаревший граф 4 модулей scripts/*». |
| 3 | minor | skills/README.md:62-64 | Утверждение «ни роль-промпты, ни паки, ни скрипты на них не ссылались» верно буквально. Но на удаленные скиллы ссылаются живые скиллы ролей: `roles-tools/claude-design/SKILL.md:20,24-38` (ui_designer грузит его «Всегда», agents/ui_designer_agent.md:16) велит «load `popular-web-designs` alongside» и говорит о «three design-related skills under `skills/creative/`»; `roles-tools/github/SKILL.md:12` и `references/issue-to-pr.md:33,41` ссылаются на `requesting-code-review` / `test-driven-development`; `roles-tools/systematic-debugging/SKILL.md:11,276,395` ссылается на `test-driven-development`. Сценарий: ui_designer на машине без локальной библиотеки `~/.hermes/skills` (новая машина, Pi-пак) получит указание загрузить скилл, которого нет. В Hermes текущей машины копии остаются, сейчас ничего не ломается. В плане это осознанно вынесено из объема (вендорские скиллы не правятся). | Добавить в абзац README одну оговорку: «вендорские roles-tools/* упоминают удаленные скиллы как related; они доступны только из локальной библиотеки». Либо завести бэклог-тюн на нейтрализацию ссылки в claude-design. |
| 4 | minor | skills/README.md:68-69 | Новое правило «скилл попадает в репо, только если на него ссылается роль, пак или скрипт» сразу нарушают оставленные `flow/{dev,qa,sa}-artifact-cleanup` и `pm-factory/{ai-factory-flow-control, factory-conveyor-audit}`. План это признает, README — нет. | Сослаться в README на исключение (отдельное решение) или сформулировать правило только для новых скиллов. Терпит до этого решения. |

## Проверено

- **Ссылки на удаленные скиллы** (по каждому из 41 имени + `skills/{creative,office,research}`, `engineering/`, `runtimes/`) в agents/, skills/pm-factory/pi/role-packs/** (README, role-agents.md, settings.example.json: ключей `skills` нет), scripts/, plugins/, templates/, docs/, AGENTS.md, README.md, .github/, tests/. Живых ссылок в промптах ролей, паках, скриптах, CI и тестах нет. Остались только ссылки скилл→скилл (замечание 3) и случайные совпадения: `notion`/`obsidian`/`powerpoint` в данных ui-ux-matrices, `~/research/` как пример пути в hermes-agent. Историю (archive/, backlog/) не учитывал.
- **Таблицы «Скиллы» ролей:** каждое имя из `| \`скилл\` |` в agents/*.md находится в skills/, кроме `ekotov-wiki-ops`. Он проектный и в репо фабрики не жил и до коммита (`git ls-tree fde64ce~1` — 0 вхождений), так что это не регресс.
- **Косвенное использование:** `factory_init.SKILL_DIRS` (scripts/factory_init.py:334-346) перечисляет 12 явных путей roles/flow/pm-factory, удаленных среди них нет. glob/rglob по `skills/` в scripts/tests/plugins нет. rsync/синхронизации с `~/.hermes/skills` в репо нет. `related_skills` никем не валидируется (grep по scripts/tests). `package_runner` и enforcer обращаются только к `skills/pm-factory/pi/role-packs`. В factory_bootstrap.py скиллов нет.
- **Удаленные строки реестра** (`popular-web-designs`, `baoyu-infographic`, `p5js`) указывали на `roles-tools/…`, где этих каталогов не было: удалены битые ссылки, это корректно. Строка README.md:288: 6 групп соответствуют `ls skills` (pm-factory, flow, roles, roles-tools, runtimes, engineering/spike). Подсчет «5 engineering + 2 runtimes = 7» сходится с `git ls-tree`.
- **Перенос PLAN-файлов:** `plan_release_paths` (flow_transition.py:314-335) и enforcer (`PLAN-{scope}.md`, enforcer.py:1221) ищут план только при prepare/делегации нового действия по scope. flow_check с PLAN-файлами не сверяет: J10 проверяет `code-reviews/<id>/` только для активных `openspec/changes/<d>/`, а там только `archive/`. Значит, каталоги code-reviews/{factory-paths,flow4-chore-scope,tests-hermetic,zone-policy-pipeline-paths}/ без корневых планов CI не ломают. Все 5 пакетов влиты в main (#214, #216, #217, #218 как zone-policy-dev-infra, #219). `PLAN-BUG-025.md` оставлен в корне обоснованно: репорт OPEN. Живых ссылок на старые корневые пути вне archive/backlog/code-reviews нет. Упоминание `PLAN-tests-hermetic.md` в PLAN-BUG-025.md:22 — проза без ссылки.
- **codegraph.json:** читателей нет. `scripts/codegraph.py` только пишет файл, тесты и CI его не открывают, factory_init копирует скрипт, а не json. Файл стоит в `.gitignore:6`, повторно в индекс не попадет.
- **Формат вердикта** `Вердикт: Одобрить` первой строкой распознает `VERDICT_APPROVE_RE` (flow_check.py:79) и `contains` манифеста. Так же оформлены прошлые ревью Флоу 4.
- **Ворота (свежий прогон):** `python3 scripts/flow_check.py .` → `flow_check: OK`. Дерево чистое, HEAD = fde64ce.

## Не проверено

- `openspec validate --all --strict`: CLI `openspec` на машине ревьюера не найден (command not found). Спеки коммит не трогает.
- Полный pytest-сьют не повторял (по поручению; данные ПМ: 1129 passed, 2 skipped).
- CI на GitHub (PR еще не открыт), а также поведение Hermes/Pi на машине без локальной `~/.hermes/skills` (замечание 3).
- Пп. 5 плана (удаление влитых веток на GitHub) — вне коммита.
