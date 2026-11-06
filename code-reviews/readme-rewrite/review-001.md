Вердикт: Вернуть

## Вердикт: return

Ревью нового README.md (ветка readme/rewrite, коммит cefd448d80e059df56b3715c73dc4692d105bc83)
против кода и документации фабрики. Старая версия — `origin/main:README.md`.
Ревьюер — независимый сабагент (Claude Code), файлы репо не правил.

Итог: структура и баланс хорошие, сверху вниз читается. Вернуть из-за двух major:
пример манифеста на реальном прогоне упадет в STOP, а раздел про flow-enforcer
обещает блокировку, которой в режиме по умолчанию нет. Остальное — minor.

## Замечания

| # | Серьезность | Где | Что не так | Как на самом деле | Рекомендация |
|---|---|---|---|---|---|
| 1 | major | README.md:177-200, 209-210 | Пример манифеста — Флоу 1, стадии `pi:dev` и `pi:code-reviewer` без `task_id`. README предлагает его «исполнить» после `--dry-run`. | `--dry-run` только разбирает манифест (прошел). При исполнении `pi:dev` во Флоу 1 — это `dev_task`, `check_dev_task` → `_require_task` (scripts/flow_transition.py:261-267) без task_id отдает `MISSING_INPUT` → STOP. `code_review` во Флоу 1 тоже требует задачу (flow_transition.py:1025-1027). Кроме того, `dev_task` Флоу 1 транзитивно требует утвержденный `requirements.md`, change-пакет, `sdd.md` и architecture review — на пустом проекте пример отказ дает гарантированно. Гайд сам пишет `task_id: "1.1"  # dev_task требует задачу` (docs/guides/pipeline-manifest.md:149, 269). | Либо перевести пример на Флоу 4 (`flow: 4`, `pi:dev` → `chore_task`, задача tasks.md не нужна; как первый пример гайда), либо добавить `task_id: "1.1"` в обе pi-стадии и строку, что для Флоу 1 до стадии dev нужны утвержденные требования и change-пакет с `tasks.md` (стадии ba/sa/architect или `hermes:pm`). |
| 2 | major | README.md:254-258 | «делегация без заголовка `flow: …` или с отказом движка блокируется на спавне, а боевые роли SA/архитектор/DEV/BA разрешены только через Pi» — подано как безусловная гарантия. | plugins/flow-enforcer/enforcer.py:34-36, 866: режим по умолчанию `FLOW_ENFORCER_MODE=permissive` — без маркеров делегация проходит, пишется только лог (block — только в `strict`). MODEL_ENFORCE (enforcer.py:101-115): боевой этап распознается эвристикой по ключевым словам goal; `[hermes:<роль5.3>]` → DENY, а без маркера исполнителя — только WARN («миграционный период»); выключается `FLOW_MODEL_ENFORCE=off`. Блокирует гарантированно только DENY движка у делегации с заголовком. | Переформулировать: «делегация с заголовком проходит `flowctl prepare --dry-run`, DENY блокирует ее на спавне; без заголовка — блок в режиме `strict`, в `permissive` (по умолчанию) пропуск с записью в лог; `[hermes:…]` на боевом этапе SA/архитектор/DEV/BA — DENY MODEL_ENFORCE». Режимы — ссылкой на plugins/README.md. |
| 3 | minor | README.md:147-148 | «Если оркестратор — Hermes, тот же запуск ставит плагин flow-enforcer». | factory_init ставит плагин всегда, без проверки, что оркестратор — Hermes: копирует в `$HERMES_HOME/plugins/flow-enforcer/` и правит `plugins.enabled` в `~/.hermes/config.yaml`, если такой блок есть (scripts/factory_init.py:63-142, 610). Кроме того, без `--skip-crons` пишет обертки кронов в `~/.hermes/scripts` и печатает таблицу рекомендуемых кронов (factory_init.py:481-482, 614-622) — в README не упомянуто. | «Тот же запуск ставит на машину плагин flow-enforcer (нужен только Hermes; `--skip-plugin` — пропустить) и обертки кронов в `~/.hermes/scripts` (`--skip-crons`)». |
| 4 | minor | README.md:145-147 | Про `--force` предупреждение только о `flow.yml`. | `--force` также пересоздает `CONSTITUTION.md` из шаблона (factory_init.py:537-541) и скелет `docs/glossary.md` (factory_init.py:397-411), а также промпты `agents/*.md` (524-533). Принципы проекта и накопленный глоссарий затираются молча. | Добавить: «…включая `flow.yml`, `CONSTITUTION.md`, `docs/glossary.md` и промпты ролей, — сохраните их или сверьте после». В перечне копируемого упомянуть промпты ролей `agents/` (с версией в шапке, рассинхрон ловит flow_check) — это было в старом README и важно для понимания тонкого клиента. |
| 5 | minor | README.md:88-98 | В требованиях нет Node.js/npm, нет команды установки Pi. | `factory_bootstrap.check_env` проверяет node/npx (factory_bootstrap.py:12); OpenSpec и Pi ставятся через npm. | Строка `Node.js + npm` (для OpenSpec и Pi) и в шаге 2 `npm i -g @earendil-works/pi-coding-agent`. |
| 6 | minor | README.md:130-134 | Ruleset: потерян практический нюанс старого README. | Чек `test-flow-control` появляется в списке required checks только после первого прогона CI (старый README:100). | Добавить в скобках «(после первого прогона CI — иначе чека нет в списке)». |
| 7 | minor | README.md:107-108 | «создает каталог состояния движка (`~/.hermes/state/`: реестр сессий, режим)». | bootstrap создает каталог, каталог архива и `flow_mode.json` (factory_bootstrap.py:83-95); реестр сессий не создает — его заводят flowctl/session_check при первой резервации. Путь — `AF_STATE_DIR`, по умолчанию `~/.hermes/state`. | «создает каталог состояния (`~/.hermes/state/`) и файл режима». |
| 8 | minor | README.md:173 | План — «`PLAN-<scope>.md` в корне проекта». | Легальны два пути: `PLAN-<id>.md` в корне и `openspec/changes/<id>/PLAN.md` (AGENTS.md, «Правило плана релиза»). Для Флоу 3 вместо плана — `incident_ref`. | Добавить второй путь одной фразой. |
| 9 | minor | README.md:62-64, 72 | «Каждая роль — системный промпт в agents/ и Pi роль-пак» — и тут же dev_lead «вне роль-паков». | dev_lead в agents/README.md:157 помечен «дизайн»; вход — `flowctl integrate` (J57). Пака нет — утверждение «вне роль-паков» верно, общая фраза ему противоречит. | «…и, кроме dev_lead, Pi роль-пак». В строке dev_lead можно указать вход `flowctl integrate`. |
| 10 | minor | README.md:219, 277 | Жаргон без пояснений для нового пользователя: provenance, digest/STALE, change-пакет, дельты/master-spec, Hermes (что это за платформа). | — | Короткие пояснения в скобках при первом упоминании (provenance — запись SHA/диффа/автора/ревьюера рядом с review; change-пакет — каталог `openspec/changes/<id>/` с дельтами спек и tasks.md; Hermes — агентная платформа оркестратора с `delegate_task`). |
| 11 | minor | README.md:219 | «zone-guard режет запись вне зоны». | Механически — только для `write`/`edit`, bash-канал эвристический (role-packs/README.md:10-15). Запись через bash ловит уже `flowctl finish` и повторная сверка диффа раннером. | «режет `write`/`edit` вне зоны; запись через bash ловит сверка диффа на finish». |
| 12 | minor | README.md:239-240 | ci_local: не сказано, что прогоняется только закоммиченный HEAD. | ci_local клонирует закоммиченный HEAD, незакоммиченные правки в прогон не попадают (старый README:80-85). | Добавить «(только закоммиченное)». |

## Баланс: что потеряно из старого README

Важное для установки и уверенной работы — перечислено в замечаниях 3, 4, 5, 6, 12.
Дополнительно (не блокирует, на усмотрение ПМ):

- Таблица «что лежит в репозитории проекта и чья это зона» (старый README:348-361):
  новому пользователю полезно знать, куда роли кладут requirements.md, openspec/,
  test-model/, code-reviews/. Сейчас этого нет ни в README, ни ссылкой. Достаточно
  одной ссылки на таблицу зон в agents/README.md в разделе 6.
- Значения путей по умолчанию (`AF_STATE_DIR=~/.hermes/state` и т.д.) и
  `factory_paths.py --doctor/--compare` — убраны обоснованно; команда
  `factory_paths.py` есть, этого достаточно.
- Контракты 1–7, CONSTITUTION, релизный контур, языковой зонинг, стек — правильно
  вынесены; ссылки на contracts/ и docs/ сохранены.

Лишнего в README нет: J-номера и история инцидентов убраны, таблицы скриптов
сжаты до групп со ссылкой на полный реестр.

## Понятность и структура

Порядок «что это → как работает → кто что делает → установка → как пользоваться →
гарантии → устройство и связи → проекты» соблюден. Раздел 4.3 «что происходит на
стадии» и 4.5 «как ПМ-агент работает с harness» прямо закрывают запрос Заказчика.
Таблица гарантий с колонкой «Граница» — честная и полезная. Замечание 10 — единственное
по понятности.

## Проверено

- factory_bootstrap.py: режим по умолчанию shadow, кроны session_watchdog */2 и
  delegate_watchdog */5, полный `pytest tests/` как приемка, секреты не переносит.
- flow_mode.py: `set enforcing --by customer` — рабочий синтаксис.
- factory_init.py: каталоги, COPY_FILES/FLOW_CONTROL_FILES, скиллы, промпты, CONSTITUTION,
  глоссарий, post-init flow_check, `--force`, `--skip-plugin`, `--skip-crons`.
- package_runner.py: виды стадий pi/gate/stand/hermes, state `<план>.runner-state.json`
  рядом с планом, ретраев нет, resume, жизненный цикл prepare → run → pi → finish →
  коммит стадии, STOP-коды ZONE_OUTSIDE_POLICY/ZONE_CONFLICT/DENY, вердикт — подстрока.
- Пример манифеста: `--dry-run` разбирает его; зоны `pi:dev [backend/**, tests/**]` и
  `pi:code-reviewer [code-reviews/add-widget/review-001.md]` через
  `role_zone_policy.narrow_zones` — violations пусты, ZONE_OUTSIDE_POLICY не будет
  (`code-reviewer` → `code_reviewer`, package_runner.py:809-810).
- Маркер «Одобрить»: role-pack code-reviewer пишет `## Вердикт: Одобрить` — `contains` совпадет.
- flow_transition.py: коды PLAN_RELEASE_MISSING, PLAN_FLOW_UNDECLARED, HUMAN_APPROVAL_REQUIRED есть.
- enforcer.py: перехват только `delegate_task`, режимы, MODEL_ENFORCE.
- role-packs/README.md: модели ролей в таблице README совпадают (glm-5.3 для sa/architect/dev/ba,
  flash — остальные, Kimi K3.1 — аудитор вручную); dev_lead пака не имеет.
- flow_ids.py: все примеры scope из таблицы 4.1 (`add-widget`, `BUG-042`, `S1-prod-down`,
  `chore`, `repo-cleanup`, `fix-typo`) — OK.
- docs/README-flow-control.md: цепочки флоу 1–5 соответствуют таблице 4.1 по сути.
- .github/workflows/flow.yml: jobs `test-flow-control` и `flow`, в flow — openspec validate,
  flow_check, pr_validate, push-gate.
- tests/conftest.py: изоляция HOME/HERMES_HOME (герметичность сьюта).

## Не проверено

- Реальное исполнение примера манифеста (не только dry-run) — вывод о STOP сделан по коду.
- Поведение раннера в shadow-режиме (блокирует ли DENY стадию) — не прогонялось.
- Ссылки и якоря, ci_local и flow_check — по данным ПМ, не повторялись.
- Описания проектов в разделе 7 по их репозиториям.

## Исправления по возврату (ПМ)

- **Major 1** пример манифеста: переведен на Флоу 4 (`log-cleanup`, chore_task — задача tasks.md не нужна ни dev, ни code_review во Флоу 4). Проверено движком, а не только разбором: на свежем репо с этим планом `flowctl prepare --dry-run --flow 4 --role dev --action chore_task` → ALLOW, zone_violations пусто; без плана → PLAN_RELEASE_MISSING. Для Флоу 1 добавлена оговорка: `task_id` по задачам tasks.md, утвержденные требования и change-пакет; пример — в гайде.
- **Major 2** flow-enforcer: описано по коду — permissive по умолчанию (без заголовка — проход с логом, strict — блок), невалидный scope/отказ движка — блок; MODEL_ENFORCE: `[hermes:<роль>]` — отказ, без маркера — WARN.
- №3: плагин и обертки кронов factory_init ставит всегда (`--skip-plugin`, `--skip-crons`).
- №4: `--force` перезаписывает ворота, flow.yml, промпты agents/, CONSTITUTION.md, docs/glossary.md; копирование промптов в проект упомянуто.
- №5: Node.js/npm в требованиях, команда установки Pi.
- №6: подсказка про появление чека `test-flow-control` после первого прогона CI.
- №7: bootstrap — каталог состояния и flow_mode.json, реестр — при первой резервации.
- №8: второй путь плана (`openspec/changes/<id>/PLAN.md`), Ф3 — incident-ref, Ф5 — без плана.
- №9: «у ролей, которые исполняет Pi, есть роль-пак» + ссылка на таблицу зон.
- №10: словарь терминов (свернутый блок): Hermes/Pi, пакет/scope, change-пакет, дельта/master-spec, зона/резервация, ворота, provenance/STALE.
- №11: zone-guard — write/edit; запись через bash ловит сверка диффа на finish.
- №12: ci_local — только закоммиченный HEAD.

## Повторная проверка (f734aa3)

Вердикт: Одобрить

Проверен коммит f734aa3 (README.md, diff против cefd448).

### Major — закрыты

- **Major 1 (пример манифеста).** Пример переведен на Флоу 4 (`log-cleanup`).
  Перепроверено независимо, на свежем git-репо, где лежит только план,
  извлеченный из README (state и реестр — во временном каталоге):
  `package_runner.py --dry-run` → exit 0; `flowctl prepare --dry-run --flow 4`
  для `dev/chore_task` с зонами `backend/**`, `tests/**` → ALLOW,
  `zone_violations: []`, проверены `plan.release`; для `code_reviewer/code_review`
  с зоной `code-reviews/log-cleanup/review-001.md` → ALLOW (во Флоу 4 задача
  tasks.md не нужна, flow_transition.py:1025-1030). `flow_ids.py 4 log-cleanup` → OK.
  Оговорка про `task_id` и входы Флоу 1 со ссылкой на гайд — точная.
- **Major 2 (flow-enforcer).** Новая формулировка (README.md 4.5 п.4)
  соответствует enforcer.py: permissive по умолчанию — проход с логом, strict —
  блок; отказ движка — блок; MODEL_ENFORCE: `[hermes:<роль>]` → отказ, без
  маркера исполнителя → WARN.

### Новые формулировки

- Плагин и кроны factory_init: верно — ставятся всегда, `--skip-plugin` /
  `--skip-crons` (factory_init.py:610-622).
- Пути плана: `PLAN-<scope>.md` в корне или `openspec/changes/<id>/PLAN.md`;
  Ф3 — incident-ref, Ф5 — без плана — совпадает с AGENTS.md («Правило плана
  релиза», J43.1).
- Bootstrap: «реестр появится при первой резервации» — верно.
- Якорь `agents/README.md#таблица-зон-записи-норма-для-всех-ролей` —
  заголовок существует (agents/README.md:18).
- Словарь терминов: определения корректны.

### Остаточные замечания (minor, не блокируют)

| # | Где | Что | Рекомендация |
|---|---|---|---|
| R1 | README.md, абзац про `--force` (раздел 3, шаг 4) | «`--force` перезаписывает все, что ставит factory_init» — неточно: каталоги скиллов при `--force` не перекопируются (factory_init.py:510-516: существующий каталог — skip без учета force). | «…все копируемые файлы (каталоги скиллов — нет)…» или убрать «все». |
| R2 | README.md, словарь, пункт Hermes | «диалог с Заказчиком в Telegram» — канал зависит от установки, в коде фабрики не зафиксирован. | «диалог с Заказчиком в мессенджере» или без канала. |

### Баланс

README вырос до 405 строк (+~40 строк текста). Словарь свернут в `<details>`, и
основной поток не утяжелен. Добавленные фразы заменили неточные, а не
наслоились. Перегрузки нет.

### Не проверено

- Реальный прогон pi-стадий (нужны Pi и ключ провайдера) — только движок и dry-run.
- Ссылки, ci_local, flow_check по новому коммиту — по данным ПМ.
- Остаток повторной проверки (R1 каталоги скиллов при --force, R2 канал Hermes) — исправлен (ПМ).
