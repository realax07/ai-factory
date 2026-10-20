# Review-001 — J58-review (code review дифа: impact-карта + механическая сверка diff→правила)

- **Задача:** J58-review (независимое code review, Флоу 4, scope=chore)
- **Ревьюируемая поставка:** ветка `chore/j58`, диф `main...HEAD`, коммит 137f257; 8 файлов, +666/-2 (scripts/impact_rules.json, scripts/pr_validate.py, scripts/factory_init.py, templates/impact.template.md, docs/README-flow-control.md, agents/README.md, tests/test_j58_impact_gate.py, tests/test_gate_harness.py)
- **Reviewer-Delegation:** j58-review (Флоу 4, маркер flow=4 role=code_reviewer)
- **Метод:** чтение дифа по 5 осям фокуса брифа + живые прогоны: целевой сьют (29 TC-J58 внутри полного регресса), полный регресс фабрики сериально — **877 passed, 2m22s**, собственный прогон `pr_validate.py .` на фабричном репо (PR-VALIDATE OK), целевые пробы механики (IR-01 misfire, bug-гейт, битый JSON).

## Вердикт: approve

Архитектура правильная: правила — данные (JSON), код ворот не меняется при расширении; карта — артефакт change-пакета, механика — общий фильтр для всех маркеров (обобщение J50). Ось фокуса проверены:

1. **Правила vs исторические кейсы — сходятся.** IR-01 на weather: позитив-тест (openapi.yaml + contracts/openapi.json в диффе) точно повторяет сценарий #211, где openapi перегенерировали — правило молчит. IR-02 на weather: deploy.sh + RUNBOOK в диффе — молчит (тест IR-02-positive). IR-03 на video-1.1: pages.py забамплен — молчит. Негативы дают DENY с id правила, label и hint (урок релиза в подсказке — хорошая практика).
2. **[BUG-NNN] — подтверждено живой пробой.** `check_impact_gate(repo, "bug", "BUG-001")` → [] на фабрике с 4 правилами: карта не требуется (ветка `flow_type == "change"` единственная требует артефакт), механика при этом работает для ЛЮБОГО маркера — негатив `check_impact_rules` ловит расхождение независимо от flow_type (TC-J58-012/013).
3. **Fail-open при битом JSON — осознанный, но с дырой (замечание 2).** Дихотомия в docstring корректна: файла нет — легитимное состояние нового проекта (молча, без WARN — тест фиксирует отсутствие WARN), битый JSON — WARN в stderr (проба подтвердила FLOW-WARNING + пропуск). Но WARN не блокирует PR, который сам ломает rules.json.
4. **Инт-тесты реальные.** `test_j58_changed_files_git_fallback` — настоящий git-репо в tmp_path (init, config, commit, правка) → `("M", "a.txt")`; не мок. Идемпотентность шаблона проверяется перезаписью проектного контента. Статус-фильтр (IR-02 молчит на 'M', консервативный DENY при неизвестном статусе — fail-closed в нужную сторону).
5. **Полный регресс сериально: 877 passed.** Включая 29 новых TC-J58 и дополненный gate-harness (эталон green-репо обязан impact.md — иначе change-ворота в harness DENY-или бы все поставки).
6. **Дифф-контекст честный.** Приоритет env `PR_CHANGED_FILES` (конвенция CI `STATUS\tpath`, bare-path → статус None → консервативно) над fallback `git diff --name-status main...HEAD` + незакоммиченные — та же схема, что у regress-ворот. `_sc.change_id_problem` — переиспользование J51, дублей валидации нет; change-PR без пакета не дублирует отказ check_change (TC-J58-020).
7. **Самоприменимость текущего PR — OK.** CI (flow.yml:103) гоняет pr_validate на самой фабрике; собственный прогон на этом диффе — PR-VALIDATE OK (дифф не трогает services/contracts/frontend/migrate — правила молчат).

## Замечания

| # | Файл:строка | Серьезность | Замечание | Рекомендация |
|---|---|---|---|---|
| 1 | scripts/impact_rules.json (IR-01 `when: ^contracts/`) × flow.yml:103 | major | Ложное срабатывание на фабричных PR: CI гоняет pr_validate на самой фабрике, у фабрики есть contracts/artifact_contract.md и flow_control_contract.md, но НЕТ contracts/openapi.json. Живая проба подтвердила: правка contracts/artifact_contract.md → DENY «перегенерируй contracts/openapi.json» — артефакта в репо не существует, любое будущее изменение фабричных контрактов заблокировано. Правила писались под целевой проект (deploy/, backend/app/pages.py), а применяются и к фабрике. | Одно из: (a) IR-01 require с условием существования (требовать только если contracts/openapi.json есть в репо); (b) сузить when до `^services/[^/]+/openapi` (убрать `^contracts/` — триггер по контракту сервиса и так покрывает кейс weather); (c) при загрузке правил в load_impact_rules требовать require.path только среди существующих в HEAD файлов. Не блокирует J58: текущий дифф проходит. |
| 2 | pr_validate.py `load_impact_rules` | minor | Битый JSON = fail-open с WARN в stderr: PR, сам ломающий impact_rules.json (опечатка в регэкспе не ловится вообще — `except re.error: continue` глушит и битое правило), проходит CI, механически обесценивая гейт. Дихотомия «нет файла — легитимно / битый — инцидент» задокументирована, но инцидент не имеет последствий. | Если rules.json входит в дифф PR и не парсится — DENY (файл ворот сломан в этом же PR). Битые регэкспы в правилах — WARN с id правила вместо тихого `continue`. |
| 3 | pr_validate.py `check_impact_rules(repo, ...)` | minor | `repo` обязан быть Path: строка падает TypeError на `repo / IMPACT_RULES_REL` (проба это подтвердила). Все текущие вызовы (main, тесты) передают Path — дефекта нет, но контракт неочевиден. | `Path(repo)` в начале, либо type-хинт в docstring. |
| 4 | tests/test_j58_impact_gate.py:171-176 | minor | `test_j58_chore_with_rule_violation_denies_but_no_map` не проверяет заявленное в имени: первый `check_impact_gate` зовется на диффе БЕЗ триггеров (пусто), затем механика проверяется отдельным вызовом `check_impact_rules` — сценарий «chore-PR с нарушением правила получает DENY механики и не получает требования карты» целиком не собирается. | Один вызов `check_impact_gate` с env PR_CHANGED_FILES=«M\tcontracts/api.yaml»: errs содержит IR-01 и не содержит «impact-карта». |

## Проверено

- Ось фокуса 1–5 из брифа (см. выше); негативные сценарии правил (все 4 правила имеют негатив-тест), статус-фильтры, fail-open/fail-closed ветки, идемпотентность factory_init, дублирование отказов change-ворот — нет.
- Полный регресс фабрики сериально: 877 passed (pytest tests/, 2m22s).
- Собственный прогон pr_validate на фабричном репо: OK.
- Доки: секция J58 в README-flow-control по всем 5 флоу — сходится с кодом (change = карта + механика, остальные = механика); agents/README (СА-выход, code_reviewer-вход) — согласованы с воротами; шаблон impact.template.md — секции соответствуют hint-подсказкам правил.

## Не проверено (честно)

- Исторические диффы weather #211 / video-1.1 напрямую не доступны из фабричного репо — сверка логическая, через позитивные тесты, повторяющие файловые составы тех кейсов по брифу.
- Поведение GitHub-_actions с env PR_CHANGED_FILES не проверялось (конвенция не используется текущим flow.yml — fallback git рабочий, что подтверждено прогоном).
