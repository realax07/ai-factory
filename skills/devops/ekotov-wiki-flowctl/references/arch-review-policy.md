# Архитектурный контур ekotov-wiki: arch-review политика

Источник решения — decisions/2026-10-08-arch-review-policy.md («давай» Заказчика).
Правило двухуровневое: arch-review не должен быть ни молчаливо отключен, ни обязателен для всего подряд.

## Триггер обязательности (arch-review ДО первой dev-задачи)

arch-review обязателен, если change:
- затрагивает `services/**`;
- меняет контрактные границы `backend/**` (API, схемы, новые эндпоинты межсервисного взаимодействия);
- затрагивает `deploy/**`;
- несет MODIFIED/REMOVED-дельты контрактообразующих спек (auth, deploy, границы сервисов).

Вердикт — против `architecture/map.md` + спек контрактов; файл `test-model/reviews/<change>/review-NNN-architecture.md`.

## Явный skip (UI-only и прочее вне триггера)

ПМ фиксирует decision-файлом: «arch не требуется, зона <обоснование>» — не молча.
Пример обоснования: дельты поведенческие (UI-представление), контракты и границы сервисов не тронуты.

## Известная дыра движка (P17 в бэклоге — не включать до завершения активного пакета)

`_arch_review_done` (flow_transition.py) требует sdd.md только при `sdd_status == "ready"`;
отсутствие sdd.md трактуется как MISSING → проверка молча пропускается. Все пакеты без sdd.md
проходили arch-этап незаметно. Фикс: явный INVALID_GATE при sdd.md=MISSING на пакете с
обязательным arch + механизм skip-решения (факт в snapshot или approval_ref). Не включать
посреди активной волны — заблокирует dev-задачи.

## Чек для ПМ на prepare нового пакета

1. Сканируй дельты пакета на триггер (зоны + контрактообразующие спеки).
2. Триггер сработал → до dev: prepare architecture_review (роль architect), verdict в reviews.
3. Не сработал → decision-skip файл + ссылка в approval-ref последующих prepare.

## Флоу 4 (chore) и механика J51: грабли prepare/run/finish (2026-10-17, живой пилот)

- Скоуп Флоу 4 — ЛИТЕРАЛ `chore` (CHORE_RE `^chore$`): любой другой change-id (даже `chore-j51-pilot-a`) = DENY AMBIGUOUS_STATE. Действие — `chore_task`, роль — `dev` (chore_task зарезервирован dev: новые роли типа regress_runner под него не проходят — отдельное действие под новую роль заводить отдельно).
- Ветви worktree деривятся из ПЕРВЫХ 8 СИМВОЛОВ correlation-id: `j51-pilot-A/B` дают одну ветку `flow/j51-pilo` — второй prepare падает WORKTREE_UNAVAILABLE и деградирует в общее дерево. Брать id, различимые в первых 8 символах (`plt-A-j51`/`plt-B-j51`), до починки деривации (J52).
- Порядок adapter=manual ЖЕСТКИЙ: prepare → `flowctl run --correlation-id` (отметить старт) → делегация → finish. Пропущенный run делает finish невозможным («статус prepared: приемка невозможна»), а run после факта ловит STALE_SNAPSHOT (снимок устарел — «повтори prepare»).
- needs_attention-сессии ДЕРЖАТ зоны (reconcile не освобождает, молча не удаляет): не воевать с машиной — взять уникальные пути зоны для новой сессии; старые гасит вотчдог/ручная разборка.
- J51-механика: prepare `--create-worktree` кладет worktree в ALLOW (деградация = WARN, не FAIL); enforcer блокирует WORKTREE_MISSING при параллельных делегациях одного repo без разных деревьев (выключатель FLOW_ENFORCER_WORKTREE=0); `flowctl regress --change C` пишет артефакт test-model/regress/<C>/regress-<N>.md (commit hash, worktree, хвост лога), `--final` → regress-final.md; pr_validate требует regress-final для change-пакетов (REGRESS_FINAL_MISSING/STALE, commit == HEAD ветки). change-id валидируется fullmatch + запрет `..` (path traversal) на обоих концах.
- Вердикты итераций ревью (review-002/004 и т.п.) сабагенты-ревьюеры регулярно оставляют НЕЗАКОММИЧЕННЫМИ в рабочем дереве (untracked едет за чекаутами между ветками): перед merge каждого PR проверять git status/git log по файлу ревью; незакрепленный вердикт коммитит ПМ с атрибуцией (Reviewer-Delegation id + пометка «восстановлен ПМ из отчета») — иначе след ревью теряется при удалении ветки/дерева.
