# Review 001: agents-core (J64.15 + J65.11)

Commit: 618836d (ветка от origin/main 0a77571)
Ветка: chore/agents-core
Ревьюер: code_reviewer — независимый сабагент; диф не писал
Прогоны:
- `pytest tests/unit/test_j65_agents_core.py tests/unit/test_j60_model_enforce.py -q -p no:cacheprovider`: 26 passed.
- `python scripts/flow_check.py .`: OK.
- `openspec validate --all --strict`: НЕ прогнан, в среде ревьюера нет `openspec`. ПМ должен прогнать его перед приемкой.
- `wc -l AGENTS.md`: 62 (предел ≤80 соблюден).
- `archive/agents-md/AGENTS-2026-11-13.md` побайтно равен `origin/main:AGENTS.md`.

## Итог

Сокращение сделано аккуратно. Почти все нормы старого текста нашлись в новом AGENTS.md, в docs/rules-enforcement.md, docs/project-pitfalls.md или в промптах и шаблонах, на которые ядро ссылается (agents/pm_agent.md, templates/task_delegation.md, agents/README.md).

Карта кодов отказа в целом верна. Выборочно сверены со scripts/ и plugins/: ZONE_OUTSIDE_POLICY, PLAN_FLOW_UNDECLARED / PLAN_RELEASE_MISSING, HUMAN_APPROVAL_REQUIRED (approval_ref → decisions/), MODEL_ENFORCE, FLOW_ID_INVALID, finish → `blocked` без отчета, запрет перезаписи в record-review, J3-защищенные пути в prepare, отсутствие TC у tests/unit.

Ссылки по номерам: правила 10, 11 и 12 переставлены. Было 10 скиллы, 11 цикл задачи, 12 worktree; стало 10 цикл задачи, 11 worktree, 12 скиллы. Перестановка не ломает ссылки, а чинит их: код и шаблоны (`flow_transition.py` п.10, `flowctl.py` п.10, `task_delegation.md` правило 10, роль-паки и `flow_control_contract.md` правило 11) и раньше имели в виду именно эти правила. Правила 3, 4, 6, 7 и 9 сохранили номер и смысл.

Возврат — из-за двух major:
1. Выпало исключение правила 17.
2. Для слабой модели есть противоречия в адресате правил и в push-политике.

## Замечания

| № | Уровень | Место | Проблема | Рекомендация |
|---|---|---|---|---|
| M1 | major | AGENTS.md:33 (п.17) | **Выпало правило.** Старый §Оркестрация 2.1 разрешал делегацию на SA, архитектора, DEV и BA «только с обоснованием в журнале делегаций PLAN.md (Pi-инфраструктура недоступна, срочный хотфикс)». Новый п.17 запрещает это без исключений. Норма с обоснованием не нашлась ни в docs/, ни в agents/, ни в skills/. При этом сообщение отказа энфорсера (`enforcer.py:829`) по-прежнему говорит «делегация — только с обоснованием в журнале PLAN.md», а `plugins/README.md:92` описывает `FLOW_MODEL_ENFORCE=off (недоступность Pi)`. glm-flash получит два несовместимых указания. | Дописать в п.17: «Исключение — Pi недоступен или срочный хотфикс: тогда допустима делегация Hermes, и до спавна запиши обоснование строкой в журнал делегаций PLAN.md». |
| M2 | major | AGENTS.md:3, 6, 20, 24, 41, 44 | **Противоречия для читателя-сабагента.** По строке 3 файл читают и ПМ, и сабагенты. (а) Строка 6: «Твоя роль по умолчанию — ПМ». Сабагент на glm-flash может принять роль ПМ. (б) Push: п.4 говорит «сабагент пушит только свою ветку pipeline/<change> и открывает PR». Строка 41 требует «зона и запрет push» в goal, строка 44 — «Пушит ПМ после приемки». Непонятно, пушит сабагент или нет. (в) П.8 требует от каждой сессии коммит в PLAN.md, backlog/ и MAP.md. У сабагента эти пути вне зоны, и это противоречит п.4. Так было и в старом тексте, но ядро для слабой модели должно снять противоречие. | (а) «Роль задает goal. Нет роли в goal — ты ПМ.» (б) Одна формулировка, например: «Сабагент: коммит в свою ветку pipeline/<change>, push только этой ветки, если goal это разрешает, иначе без push. В main пушит только ПМ после приемки». Строку 41 привести к ней же: «зона и push-политика». (в) П.8: «ПМ: каждую сессию заканчивай коммитом… Сабагент: заканчивай коммитом артефактов своей зоны». Правила только для ПМ (8, 13, 14, 20 и разделы «Оркестрация» и «Режим работы ПМ») пометить «(ПМ)». |
| m1 | minor | agents/dev_agent.md:121, devops_agent.md:59, qa_automation_agent.md:103; agents/pm_agent.md:33; skills/…/ai-factory-conveyor/SKILL.md:138, 218; docs/process-context.md:28; skills/…/references/subagent-delegation.md:14; docs/runbook-emergency-merge.md:9; scripts/flow_transition.py:893 | Ссылки на снятые разделы AGENTS.md: «§Эскалация needs-debug» (теперь «Эскалация и здоровье сессий»); «Оркестрация» п.3 (нумерации больше нет); «Правило плана задачи» (теперь п.13); «Внешние агенты-copilot» (теперь п.21, обоснование — в archive/); «Push-политика» (теперь п.4); «таблица в AGENTS.md» (теперь список); «Этапные ворота Заказчика» (устарело еще до этого PR). | Заменить на номера правил или новые имена разделов. Для обоснований дать путь archive/agents-md/AGENTS-2026-11-13.md. |
| m2 | minor | docs/rules-enforcement.md:15, 22, 27 | В карте не те идентификаторы. `push_denied` и `worktree_missing` — имена событий лога, а коды блокировки — `PUSH_POLICY` и `WORKTREE_MISSING`. `worktree_gate_unavailable` ничего не проверяет: это fail-open, при нечитаемом реестре блокировки нет (`enforcer.py:375`). Ворота worktree выключаются через `FLOW_ENFORCER_WORKTREE=0`. `ZONE_OUTSIDE_POLICY` выдает `flowctl prepare` и раннер (`flowctl.py:653`, `package_runner.py:1432`), а не session_check. `FLOW_ID_INVALID` выдают flow_state и flowctl, в flow_ids — только грамматика. | Строка 11: `WORKTREE_MISSING` (pre_tool_call delegate_task, отключается env), `worktree_gate_unavailable` отметить как деградацию. Строка 4: `PUSH_POLICY`, ZONE_OUTSIDE_POLICY отнести к flowctl prepare / раннеру. Строка 16: flowctl/flow_state (`FLOW_ID_INVALID`) по грамматике flow_ids. |
| m3 | minor | AGENTS.md:46 | «tests/** — qa_case_reviewer» противоречит J66 и п.6 этого же файла: unit-тесты dev ревьюит code_reviewer вместе с кодом (SKILL.md:138). | «tests/api\|web\|integration/** и test-model/ — qa_case_reviewer; tests/unit/** — code_reviewer вместе с кодом». |
| m4 | minor | AGENTS.md (несколько мест) | Мелкие нормы, которые выпали без замены. В основном они есть в pm_agent.md и шаблонах, но в ядре их нет: (1) второй легальный путь плана релиза `openspec/changes/<id>/PLAN.md`: п.14 называет только `PLAN-<change>.md`, и слабая модель сочтет план в пакете невалидным; (2) return → доработка → повторное ревью (п.10); (3) ветку после приемки удаляет ПМ (п.11); (4) в goal ревьюера писать «прогоны не повторять» (строка 57); (5) перед докладом «жду команды» сверить три случая паузы; (6) после `factory_init --force` сверить required-checks и триггеры проекта; (7) при входе обновить чеклист PLAN.md; (8) реестр active_sessions: при спавне добавить запись, при приемке удалить (п.10 упоминает файл без действия; действие есть в pm_agent.md); (9) внешний агент обязан резервировать зону через session_check (п.21; правило есть в subagent-delegation.md). | Дописать (1), (2) и (8) в правила — это действия. Остальное оставить в pm_agent.md и шаблонах. |
| m5 | minor | AGENTS.md:26, 32, 25 | Формулировки для glm-flash. П.10: путь в скобках без глагола. П.16 смешивает две темы: «Обход ворот — только строкой…» читается как разрешение агенту обойти ворота самому. П.9: многоточие вместо образца строки. | П.10: «Перед спавном сверь пути записи с ~/.hermes/state/active_sessions.json; пересекаются — запускай по очереди». П.16 разделить: «Строку `flow: bypass --by customer` пиши только по зафиксированному решению Заказчика; сам ворота не обходи». П.9 — дать готовый образец: `prepare: PASS \| reserve: PASS \| zone-check/gates: PASS \| provenance: SKIPPED (код)`. |
| m6 | minor | tests/unit/test_j65_agents_core.py:52-55 | TC-J65-AGC-003 ловит только порядок «AGENTS.md п.N» и «AGENTS.md правило N». Обратный порядок не ловит: «правило 11 AGENTS.md» есть в templates/constitution.template.md, contracts/flow_control_contract.md:172 и templates/task_delegation.md:37. Тест проверяет только, что номер существует, но не смысл: перестановку 10/11/12 он бы не заметил. | Расширить regex на обратный порядок. Для п.10 и п.11 добавить проверку ключевого слова в тексте правила (параллель или зоны; worktree). |
| m7 | minor | PLAN-agents-core.md:16-17; archive/README.md | PLAN утверждает, что «Нумерация 1–12 сохранена». Фактически правила 10–12 переставлены: старые 10→12, 11→10, 12→11. Из-за этого старые ревью и бэклог читаются неверно, например J11 «Изоляция ролей (AGENTS.md п.10)». | Записать соответствие старых и новых номеров в PLAN и archive/README.md. |

## Не проверено

- `openspec validate --all --strict` и ci_local: нет инструмента в среде ревьюера.
- Живой Hermes, flow-enforcer: в enforcer.py изменился только текст сообщения, проверено по диффу и test_j60.

## Вердикт: return
