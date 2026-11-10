Вердикт: Одобрить

## Вердикт: approve

Повторное ревью ветки chore/j64-tails (worktree /Users/ekotov/AI/ai-factory-t)
после исправлений по review-001. Задачи J64.9, J64.11, J64.17.
Commit: 028f142569343f47352138d3ca14a0a1345bae11 (дифф `4393e03..028f142`).
Ревьюер — тот же независимый сабагент (Claude Code). Код не правил, ruleset
репозитория не менял (только GET).

Итог: major закрыт, все 7 minor закрыты, регрессий нет. Остались три
косметических nit и один риск, который проверится на репетиции. Ни то, ни
другое не блокирует.

## Проверено фактами

- `test_j64_tails.py` + `test_j65_pack_zone_docs.py`: 16 passed.
  `gen_role_docs.py --check`: таблицы актуальны.
- `ruleset_check.py --repo realax07/ai-factory`: exit 0, `--json` →
  `{"ok": true, ...}`. Новые проверки target/conditions боевой ruleset
  пропускают: target=branch, include=[refs/heads/main].
- Команда снимка из RUNBOOK (`gh api …/rulesets/24385697 --jq '{name, target,
  enforcement, bypass_actors, conditions, rules}'`) дает валидный JSON с
  enforcement=active и полными параметрами правил.
- В debug-паке и `agents/debug_agent.md` упоминаний `test-model/regress`
  больше нет (grep).

## Закрытие замечаний review-001

| # | Было | Статус | Факт |
|---|---|---|---|
| 1 | major: бриф debug велит писать лог в test-model/regress | закрыто | debug/README.md:58 — «Отчет — ответом; запись в репо — только append в docs/project-pitfalls.md» |
| 2 | minor: без поля bypass_actors скрипт давал ложный OK | закрыто | ruleset_check.py: `Unknown` → exit 2 с сообщением UNKNOWN; тест `test_ruleset_without_bypass_field_unknown` |
| 3 | minor: settings/README/заголовок про zone-guard | закрыто | settings.example.json, README.md:13, role-agents.md:28 — «append через bash, границу держит сверка диффа на finish» |
| 4 | minor: «одним коммитом» и «никаких коммитов» в промпте | закрыто | debug_agent.md:26-27 — «коммит делает ПМ или раннер после приемки» |
| 5 | minor: снимок в /tmp, восстановление через UI | закрыто | RUNBOOK шаг 1: `SNAP=~/ruleset-main-<ts>.json` с полями тела PUT; шаг 5: `gh api -X PUT … --input $SNAP` и повторный ruleset_check |
| 6 | minor: post-mortem без обязательных заголовков, имя одно на все эпизоды | закрыто | RUNBOOK шаг 6: `<date>-S2-emergency-merge-<slug>.md`, шаблон с `## Таймлайн` / `## Root cause` / `## Action items` (как в flow_transition.POST_MORTEM_SECTIONS) |
| 7 | minor: не проверялась цель ruleset | закрыто | ruleset_check.py: проверяет target == branch и refs/heads/main или ~DEFAULT_BRANCH в include |
| 8 | minor: тестам не хватало кейсов | закрыто | добавлены non_fast_forward, «не нацелен на main», нет bypass_actors (exit 2), ruleset не найден (мок `_gh`, exit 2) |

Наблюдение вне объема (WRONG_ROLE для Hermes-делегации debug) записано
кандидатом в бэклог J64. Этого достаточно.

## Замечания

| # | Серьезность | Где | Что не так | Рекомендация |
|---|---|---|---|---|
| 1 | minor (nit) | skills/pm-factory/pi/role-packs/debug/README.md:58 | Опечатка «фикса текстом..» — две точки. | Убрать лишнюю точку. |
| 2 | minor (nit) | scripts/ruleset_check.py:105-109 | С `--json` при UNKNOWN в stdout ничего не печатается, есть только stderr. Машинный потребитель не получит JSON. | При `--json` печатать `{"ok": false, "unknown": "<причина>"}`. |
| 3 | minor (nit) | skills/pm-factory/pi/role-packs/debug/role-agents.md (раздел «Выход») | Осталась фраза «если guard блокирует запись вне зоны» — при tools read/bash guard не участвует. | Переформулировать: «если запись в pitfalls невозможна — текст в отчете ПМ». |
| 4 | риск (на репетицию) | docs/runbook-emergency-merge.md, шаг 5 | В снимке GET есть поля параметров `pull_request` (`require_extra_approval_for_unattributed_changes`, `required_reviewers`). Принимает ли их PUT без ошибки, без реального PUT не проверить. | На репетиции J64.9 выполнить и восстановление из снимка (PUT `--input`), а не только disabled → active. Результат отметить в резолюции. |

## Вердикт: approve
