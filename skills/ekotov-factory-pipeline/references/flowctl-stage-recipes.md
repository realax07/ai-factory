# flowctl: рецепты этапов (Флоу 1/2)

Проверенный порядок подготовки любого этапа; dry-run — всегда первый прогон.

## 1. Decision-файл ДО prepare (P0.4)

`decisions/YYYY-MM-DD-<slug>.md` с машиночитаемым блоком decision-record:

- `action` в блоке должен ТОЧНО совпадать с `--action` этапа — разрешение чужого действия не переносится (типовая ошибка: ставишь общий «start», а этап требует конкретное действие).
- Поле `commit` обязательно — влитой SHA PR, которым решение попало в main.
- `scope.project` = значению `--project` (для ekotov-wiki это `wiki`, НЕ ekotov-wiki-par — иначе «решение относится к другому scope»).
- Валидация P0.4 читает блок до prepare: неполный блок = DENY уже на prepare; правка decision = отдельный PR (ветка → commit → PR → merge), затем prepare от свежего main.

## 2. `--dry-run` — первый прогон

Все DENY (формат decision, action, project-scope, зоны) видны в dry-run за один прогон. Боевые попытки без dry-run дают лишние PR и DENY-записи в реестре. Диагностику причин DENY тоже делай в dry-run (grep по `"details"` в JSON-выводе).

## 3. Зоны `--path`

- Каталог `openspec/changes/<id>/**` политикой НЕ матчится (glob посегментный, `*` = один сегмент).
- Рабочий набор для create_change (role sa): конкретные файлы proposal.md, requirements.md, research.md, design.md, tasks.md + литеральное `openspec/changes/<id>/specs/**` (литеральное совпадение принимается).
- Зона роли фиксирована: pm — PLAN.md/BACKLOG.md/README.md; ba — requirements.md, docs/ba/*; code_reviewer — code-reviews/*/review-*.md. CLI может только сузить политику, расширить — нельзя.
- Пустая зона = MISSING_INPUT на prepare: даже «статусным» этапам (approve_requirements) передавай зону роли явно (pm → `--path 'PLAN.md'`).

## 4. Цикл этапа

`prepare` → `run --correlation-id <id>` (отметить старт) → делегация сабагенту → `finish --report <файл отчета>`.

- Порядок ОБЯЗАТЕЛЕН: `finish` на сессии в статусе prepared отказывает («приемка невозможна»), а `run` после факта ловит STALE_SNAPSHOT (снимок устарел — «повтори prepare», контракт §6) — с ретроспективным закрытием делегации не выкрутиться. Отметь run ДО старта сабагента.
- Проверь snapshot-дайджест между prepare и run: любое изменение дерева (даже untracked PLAN) делает снимок устаревшим.
- После мержа PR сабагента: checkout main + pull ПЕРЕД следующим prepare (snapshot-дайджест готовится из HEAD).

## 4a. Worktree-per-delegation (J51.1) и живые ловушки пилота

- `prepare --create-worktree` создает выделенное дерево и вшивает путь в ALLOW — при параллельных делегациях одного repo энфорсер требует разные деревья (WORKTREE_MISSING). Деградация (git worktree недоступен) — WARN в ALLOW, не FAIL; при параллели WARN = работа в общем дереве = гонки, не принимай.
- **Ветка деривится из ПЕРВЫХ 8 СИМВОЛОВ correlation-id**: id с общим префиксом (`j51-pilot-A`/`j51-pilot-B` → обе `flow/j51-pilo`) коллизируют — второй prepare падает «branch already used by worktree» и деградирует. Бери id, различимые в первых 8 символах, или чини деривацию (J52).
- needs_attention/reserved сессии ДЕРЖАТ резервацию зон: новый prepare с пересекающимися --path ловит ZONE_CONFLICT, а `reconcile` статус не освобождает («ничего не удалять молча»). Обход до починки (J52): уникальные пути для новых prepare; системный сброс — за явным решением ПМ.
- `flowctl regress --change C` (J51.2): дифф → домены (frontend→tests/web, backend→tests/api, иначе tests/), артефакт `test-model/regress/<C>/regress-<N>.md` (append-only, commit hash, worktree), `--final` → regress-final.md (его и только его считает воротами merge pr_validate: PASS + commit==HEAD + свежесть). change-id валидируется (fullmatch + запрет `..`) в обоих концах — не пиши свой путь к артефакту мимо валидатора.
- Регресс-домен granularity: `tests/**` гоняет весь домен — для точечного пилота это минуты на полный сьют; гранулярность по подкаталогам — в J52.

## 5. Маркеры PR по типу работ (pr_validate)

- PR создания пакета (create_change) — маркер `[docs]`: change-маркер триггерит полный QA-хвост pr_validate (test-model impact/checklists/approved/reviews), появляющийся только в финальном PR пакета после dev/QA волн.
- Финальный PR пакета — change-маркер + полный QA-хвост.
- `--id` для pr_validate — change-id/BUG-NNN, не номер PR.
- `gh pr edit` может падать (GraphQL Projects-classic deprecation) — не чинить: close + новый PR с того же head; свежий CI-прогон отслеживай по branch (`gh run list --branch`), а не по PR — старый прогон от прошлого title остается в checks PR.

## 6. Ожидание чеков и мерж

Цикл по `gh pr checks <n>` с подсчетом pass/fail/pending (не `gh pr checks --watch` — держит 300с+ и роняет kernel по таймауту); мерж только при fail=0 и pending=0; после мержа — checkout main + pull.
