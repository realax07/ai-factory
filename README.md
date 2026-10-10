# AI Factory — конвейер разработки ПО из агентов

> **AI Factory** — производственный конвейер, в котором программное обеспечение разрабатывает не один «универсальный» LLM-агент, а **коллектив изолированных агентов-специалистов**: бизнес-аналитик, системный аналитик, разработчик, ревьюер, QA-контур из четырех ролей, архитектор, DevOps, валидатор дизайна. Порядок работы обеспечивается не дисциплиной, а **исполняемыми воротами**: скрипты и CI физически не пропускают шаги мимо процесса.
>
> Оперативные правила — [AGENTS.md](AGENTS.md), статус — [PLAN.md](PLAN.md), уроки — [backlog/MAP.md](backlog/MAP.md), контракты — [contracts/artifact_contract.md](contracts/artifact_contract.md).

---

## Установка

### Требования

| Компонент | Версия | Зачем |
|---|---|---|
| git | ≥ 2.40 | версии, PR-цикл, аудит-след |
| Python | ≥ 3.11 (скрипты — только stdlib) | все ворота и утилиты конвейера |
| [OpenSpec CLI](https://github.com/Fission-AI/OpenSpec) | ≥ 1.13 (`npm i -g @openspec/cli`) | формальные спеки + `openspec validate --strict` |
| GitHub-репозиторий с Actions | — | CI-ворота (flow.yml) |
| Hermes Agent (или среда с `delegate_task`) | — | запуск сабагентов-ролей |

### Установка на новую машину — bootstrap

```bash
git clone <ai-factory> && cd ai-factory
python3 scripts/factory_bootstrap.py            # окружение + state + крон вотчдога + приемочные тесты
```

Bootstrap: проверяет окружение (python ≥ 3.10, git, npx для openspec), создает state-каталоги (`~/.hermes/state/`, реестр, `flow_mode.json` с **дефолтом shadow**), ставит крон вотчдога (session_watchdog */2 + delegate_watchdog */5), гоняет приемочные тесты (348). Секреты НЕ переносит — кладутся вручную в `~/.hermes/.env`. Режим enforcing включается явно (`flow_mode.py set enforcing`), после shadow-прогона.

### Настройка GitHub (вручную, один раз на репозиторий)

Обязательная часть установки — без этого внешний контур не замкнут (машина честно рапортует `external_enforcement: UNKNOWN`):

1. **Ruleset на main** (Settings → Rules → Rulesets → New branch ruleset):
   - Enforcement: **Active**; Bypass: **Never** (даже админ не обходит);
   - Rules: **Require a pull request before merging**; **Block force pushes**; **Required status checks** → добавить `test-flow-control` (после первого прогона CI, иначе чека еще нет в списке) и `flow`.
2. **Проверка факта:** `gh api repos/<owner>/<repo>/rules/branches/main` — должен вернуть массив с `pull_request` и `required_status_checks` (содержащим `test-flow-control`); живой тест — прямой push в main отклоняется (GH013 «repository rule violations»).
3. **Токен машины** (`realax1990-boop`): права `write` достаточно для чтения rules через `/rules/branches/{branch}` (admin НЕ нужен для нового Rulesets API — в отличие от legacy protection endpoint, который дает 404).

Эталонная конфигурация (проверено живым пушем 2026-10-02): ruleset `main` — rules `pull_request`, `non_fast_forward`, `required_status_checks: [test-flow-control]`, bypass never.

### Развертывание на новый проект — одна команда

```bash
python3 ~/ai-factory/scripts/factory_init.py \
    --target /path/to/your/repo \
    --name "My Project"
```

Скрипт: создает структуру каталогов (openspec, test-model, architecture, docs/ba), копирует ворота и скрипты (flow_check, pr_validate, codegraph, smoke_static, session_archive, session_worktree, **delegate_gate**, **delegate_watchdog**, check_auth_timing, **pm_bounds_check**), CI-workflow, контракты, шаблоны; создает `CONSTITUTION.md` из шаблона; проверяет среду; прогоняет **post-init ворота** — `flow_check` на пустом проекте обязан вернуть OK. Идемпотентен: повторный запуск без `--force` ничего не перезапишет.

**Отношение «фабрика ↔ проект»: проект — тонкий клиент.** В проекте живут его код, спеки, артефакты и автономные CI-ворота (flow_check + flow.yml — работают без машины). Ядро детерминированного слоя (flow_state, flow_transition, session_check, gate_runner, flowctl, flow_mode, реестр сессий) — в фабрике, в одном экземпляре, и обслуживает все проекты по путям (`--repo`/`--registry` — параметры). Обновление правил = обновление фабрики в одном месте; проектные ворота синхронизируются factory_init (`--force`), рассинхрон промптов ловится flow_check.

Промпты ролей **копируются в проект при установке** — фабрика самодостаточна и не зависит от каталога `~/ai-factory` после установки. Рассинхрон с фабрикой ловится воротами: каждый промпт несет версию в шапке, `flow_check` сравнивает с эталоном фабрики при наличии машины-фабрики (WARNING) — обновление конвейера в проекте всегда осознанный шаг (`--force`).

---

## Зачем это существует

Обычная разработка с LLM-агентами страдает тремя болезнями:

1. **Контаминация ролей** — один «универсальный» агент пишет, тестирует и ревьюит сам себя; собственные ошибки ему не видны.
2. **Потеря решений** — договоренности живут в чате и исчезают; следующий запуск принимает решения заново.
3. **Отсутствие детерминизма** — процесс зависит от дисциплины конкретного запуска: обход флоу ничем не наказуем.

AI Factory отвечает на каждую: **каждая роль — изолированный сабагент** (физически не видит чужой контекст, проверено живым тестом), **передача — только артефактами в репозитории** (диалог не является источником правды), **порядок проверяется скриптом и CI** (нарушение = красный пайплайн, а не замечание).

---

## Стек и технологии

| Слой | Технология | Роль в конвейере |
|---|---|---|
| Спеки | [OpenSpec](https://github.com/Fission-AI/OpenSpec) | формальный формат Requirement/Scenario, change-пакеты, `validate --strict`, master-spec + archive |
| Оркестрация агентов | [Hermes Agent](https://hermes-agent.nousresearch.com/docs) (`delegate_task`) | изолированные контексты сабагентов, живые транскрипты, фоновый запуск |
| Практики спек | [GitHub Spec Kit](https://github.com/github/spec-kit) | источник заимствований (E12-спайк, [docs/e12-speckit-spike.md](docs/e12-speckit-spike.md)): constitution-артефакт, research.md, [P]-маркеры; замена отклонена — у spec-kit нет исполняемой state machine и мультиагентности |
| Ворота флоу | собственный `flow_check.py` (~310 строк, stdlib) | детерминированная state-machine по артефактам |
| CI | [GitHub Actions](https://github.com/features/actions) (`.github/workflows/flow.yml`) | оба валидатора на каждый push/PR |
| Контроль версий | git + branch protection | прямые push в main отклонены; только PR |
| QA API | [pytest](https://pytest.org) + [requests](https://requests.readthedocs.io) | регрессионный API-сьют |
| QA UI | [Playwright](https://playwright.dev/python/) | браузерные тесты |
| Code graph | собственный `codegraph.py` (stdlib AST) | машиночитаемый граф зависимостей для impact-анализа |
| Архитектурная карта | `architecture/map.md` | компоненты, допущения с пометками «проверено/не проверено», долг |
| Деплой | rsync + systemd + nginx; `deploy/deploy.sh` | канонический деплой со смоуком и DRY_RUN, откат по RUNBOOK |
| Токен-аналитика | [tiktoken](https://github.com/openai/tiktoken) | замер RU/EN (J5): EN-промпты экономят 41% |

### Языковой зонинг (J5)

Интерфейс **человека → русский**: спеки, кейсы, чеклисты, review, баг-репорты, impact, requirements, BACKLOG/PLAN — все, что читает Заказчик; дословность цитат важнее экономии. Интерфейс **агента → английский**: промпты ролей, сообщения скриптов-ворот, шаблоны, контракты (−41% токенов, точнее формулировки MUST/SHOULD для моделей). Перевод — ленивый, по мере очередных правок, не разовым стресс-переводом.

---

## Роли (кто что делает)

Все роли выполняются выделенными сабагентами. Оркестратор — роль ПМ. **ПМ — main-сессия; ПМ-сабагент НЕ внедряется** (решение Заказчика 2026-10-10, J1–J4 закрыты: сабагент ПМ порождал бы сабсабагентов — лишний уровень оркестрации; параллельные проекты решаются отдельным инстансом Hermes на другой VPS; контекст проекта — во внешней памяти, новый проект = новая директория + сброс сессии. Дизайн сохранен как артефакт: [agents/pm_agent.md](agents/pm_agent.md), `templates/pm_launch.md`, `scripts/pm_bounds_check.py` — bounds-проверки живы). ПМ — единственный контакт с Заказчиком и владелец общей картины. Реестр и зоны записи: [agents/README.md](agents/README.md).

| # | Роль | Промпт | Что делает | Вход → Выход |
||---|---|---|---|---|
| 1 | **БА** | [ba_agent.md](agents/ba_agent.md) | Диалог с Заказчиком, фиксация требований дословно (не придумывает) | диалог → УТВЕРЖДЕННОЕ `requirements.md` |
| 2 | **СА** | [sa_agent.md](agents/sa_agent.md) | ТЗ → формальная спека OpenSpec + SDD + research альтернатив | ТЗ → change-пакет + `sdd.md` |
| 3 | **qa_impact_analyst** | [qa_impact_analyst_agent.md](agents/qa_impact_analyst_agent.md) | Дельты vs существующий регресс: keep/revalidate/retire; вопрос внешних компонентов (E10) | дельты → impact-вердикты |
| 4 | **dev** | [dev_agent.md](agents/dev_agent.md) | Реализация одной задачи tasks.md (worktree, ветка, PR) | задача → код + PR |
| 4a | **dev_lead** | [dev_lead_agent.md](agents/dev_lead_agent.md) | Merge и консолидация результатов параллельных dev-сабагентов в интеграционную ветку (J9): ПМ в продуктовом репо git не касается | approved-ветки → merge + сводный отчет |
| 5 | **code_reviewer** | [code_reviewer_agent.md](agents/code_reviewer_agent.md) | Ревью диффа по 3 кругам (спека = закон / практики / интеграция) | PR → approve / return |
| 6 | **qa_checklist** | [qa_checklist_agent.md](agents/qa_checklist_agent.md) | Спека → чеклист CHK-N, границы/негатив, дефекты спеки | спека → чеклист |
| 7 | **qa_case_author** | [qa_case_author_agent.md](agents/qa_case_author_agent.md) | Чеклист → кейсы TC-N (1 кейс = 1 файл) | чеклист → кейсы |
| 8 | **qa_case_reviewer** | [qa_case_reviewer_agent.md](agents/qa_case_reviewer_agent.md) | Ревью кейсов (партиями ≤12, файл за файлом, append-замечания) | кейсы → approve / return |
| 9 | **qa_automation** | [qa_automation_agent.md](agents/qa_automation_agent.md) | Approved-кейсы → автотесты; явные порты стендов; баг-репорты | кейсы → сьют |
| 10 | **qa_regression_analyst** | (при первом релизе, G5) | Валидация меток регресса → манифест | метки → манифест |
| 11 | **architect** | [architect_agent.md](agents/architect_agent.md) | Ревью change-пакетов СА, архитектурная карта, допущения | пакет → ревью + `architecture/map.md` |
| 12 | **devops** | [devops_agent.md](agents/devops_agent.md) | Факты инфры командами ДО скрипта → RUNBOOK → deploy.sh | среда → RUNBOOK + deploy |
| 13 | **design_validator** | [design_validator_agent.md](agents/design_validator_agent.md) | Реализованный UI vs дизайн-артефакты (ловит «браузерные дефолты») | UI → вердикты соответствия |
| 13a | **ui_designer** | [ui_designer_agent.md](agents/ui_designer_agent.md) | Мокапы и дизайн-токены (HTML, зона `design/`), до dev-внедрения; Заказчик выбирает вариант | спека → мокапы + токены |
| — | **ПМ** | main-сессия (ПМ-сабагент не внедряется, решение 2026-10-10 — см. выше) | Диалог с Заказчиком, сборка задач, приемка фактами, push, PLAN/BACKLOG, диспатч сабагентов (через [delegate_gate](scripts/delegate_gate.py)) | — |
| 14 | **debug** (эскалационный, 2026-10-03) | [debug_agent.md](agents/debug_agent.md) | Изолированная диагностика по эскалации `needs-debug:` от любого сабагента (через ПМ): воспроизведение, среда/код/тест вердикт, база граблей проекта. **Запись в продукт запрещена** — фиксы текстом в отчете, код меняет исходный dev | эскалация → вердикт + база граблей |

**Самоулучшение (E16):** агент, поймав 2 одинаковые ошибки подряд, пишет «проблема → решение → предложение» в `agents/<роль>_improvements.md` и меняет подход — работа доделывается, урок накапливается. Транскрипты всех сессий архивируются (`session_archive.py`) с детерминированным разбором паттернов неуспеха (ретроспектива 48 сессий: топ-причина — среда исполнения; профилактика вшита в [AGENTS.md](AGENTS.md)).

---

## Флоу (порядок работы)

### Флоу 1: Новый функционал (полный цикл) — основной

```
Заказчик ⇄ БА → requirements.md (УТВЕРЖДЕН) → СА → change-пакет + sdd.md
                                                │
                              architect ревьюирует пакет до разработки
                                                │
                              (MODIFIED/REMOVED дельты? → qa_impact_analyst)
                                                │
     ┌──────────────────────────────────────────┘
     ▼  цикл на каждую задачу tasks.md ([P] = параллелятся в worktree'ах)
 dev → PR → CI (flow.yml) → code_reviewer (approve → merge | return → доработка)
     │
     ▼  после всех задач
 qa_checklist → чеклист → qa_case_author → кейсы → qa_case_reviewer (approve)
     │
     ▼
 qa_automation → сьют (pytest) → ревью кода тестов
     │
     ▼  релизный контур
 release-candidate → предрелизный регресс → design_validator (UI-дельты) → main
     │
     ▼  контракт 7
 АРХИВАЦИЯ: дельты слиты в openspec/specs/, пакет → changes/archive/
```

Когда применять: новое поведение, изменение существующего, новые сущности — всё, что меняет спеку.

### Флоу 2: Баг-фикс (быстрый цикл)

Баг = расхождение **реализованного** с **спекой**, поэтому БА и СА не участвуют: `BUG-NNN` в `test-model/bugs/` → dev фикс → ревью → merge → regression: keep. Если ожидание не выводимо из существующих Requirements — это фича (Флоу 1); мини-дельта СА обязательна при затрагивании API/схемы. Прецедент: BUG-001 (2026-09-19).

### Флоу 3: Hotfix на проде

Откат деплоя (бэкап БД + код из снапшота по RUNBOOK) → уведомление Заказчика немедленно → фикс по Флоу 2 параллельно → полный PR-цикл после стабилизации. Контур описан, не обкатан (прод не падал).

### Флоу 4: Обслуживание

Мини-ТЗ прямо в делегации → стандартный PR-цикл. Прецеденты: E5–E14 бэклога фабрики, уборка хвостов R2.

| Ситуация | Флоу | БА | СА |
|---|---|---|---|
| Новое поведение/сущность | 1 | да | да |
| Поведение ≠ спеке | 2 | нет | нет* |
| Прод сломан | 3 | нет | нет* |
| Поведение не меняется | 4 | нет | нет* |

---

## Гарантии (как обеспечен детерминизм)

Три независимых слоя: правила «на бумаге» + **исполняемые ворота** + физические замки.

| Ворота | Что ловит |
|---|---|
| [scripts/flow_check.py](scripts/flow_check.py) | Порядок артефактов: чеклист без спеки, кейсы без чеклиста, approved без ревью, автотесты без TC-трассировки, archive без слияния дельт; **I3**: API-эндпоинт вне спек; качество ТЗ (7 разделов, уникальность FR/NFR, запрет TBD, оценочные формулировки); **H1** «1 кейс = 1 файл». Exit 0/1/2. |
| **Детерминированный Flow Control** ([docs/README-flow-control.md](docs/README-flow-control.md)) | Исполняемая state-машина: `flow_state` (снимок фактов) → `flow_transition` (ALLOW/DENY/UNKNOWN по графам Флоу 1–5, этапные ворота Заказчика) → `session_check` (атомарная резервация зон, границы записи: renames/symlink) → `gate_runner` (ворота с digest/STALE, provenance review, audit JSONL) → `flowctl` (оркестратор). Режимы shadow/enforcing (`flow_mode.py`); **enforcing включен 2026-10-02** — DENY/UNKNOWN блокируют действие. 348 тестов, 7 ревью-циклов. |
| [scripts/pr_validate.py](scripts/pr_validate.py) | PR без маркера (BUG-NNN / change-id / [chore]/[docs]/[ops]) и без обязательных файлов; **J11**: Reviewer-Delegation сверяется с реестром — делегация обязана существовать, быть completed и иметь роль `code_reviewer` (self-review/чужая роль = ревью не засчитано); **J26**: PR с диффом `deploy/**`/`RUNBOOK.md` без маркера `[ops]` = FAIL (CI-ворота, `PR_CHANGED_DEPLOY`). |
| [scripts/check_auth_timing.py](scripts/check_auth_timing.py) | AST-контроль auth: bcrypt, dummy-логины, secrets вместо `==`. |
| [scripts/smoke_static.py](scripts/smoke_static.py) | Класс DEF-002: статик-ресурс, на который ссылается UI, но который не отдается (сверка ссылок с диском + прод-URL требует 200). |
| `.github/workflows/flow.yml` | Оба валидатора на каждый push/PR — нарушение нельзя смержить. |
| Branch protection | Прямой push в main отклонен GitHub (проверено живым тестом GH013). |
| [scripts/session_archive.py](scripts/session_archive.py) | Разбор транскриптов: traceback, module_not_found, exit codes, петли; вердикт clean/suspicious/degraded. |

| [scripts/delegate_gate.py](scripts/delegate_gate.py) | **Вход в машину**: делегация создается только через `flowctl prepare+run` (DENY/MISSING_INPUT/ZONE_CONFLICT → делегации не будет); finish с обязательными гейтами по флоу 1–5. |
| [scripts/delegate_watchdog.py](scripts/delegate_watchdog.py) | **Детектор обхода**: сверяет платформенный реестр делегаций (async_delegations — пишется при каждом `delegate_task` независимо от воли агента) с prepare-записями flowctl. Делегация мимо машины → BYPASS-инцидент в `~/.hermes/state/delegate_bypass_incidents.json`; забытый finish → STALE. Крон */5. Трехканальный отчет: Заказчик — машинный stdout (дельта по ack-файлу), ПМ-0 — `pm_instruction.txt` + крон `pm-instruction-relay` (*/2), ПМ-1 — stdout крона; анти-рекурсия (fingerprint-дедуп, cooldown 15 мин, потолок 3/ч). |

**Три слоя гарантии (2026-10-03, инцидент add-containerization):**
1. **Движок** — flowctl DENY на входе (зоны, approval_ref, роли) блокирует неправильное до старта.
2. **Вотчдог** — обход flowctl неизбежно виден в течение ~5 минут (реестр делегаций пишет платформа, агент не контролирует). Baseline с даты внедрения — история не инцидент.
3. **Правило** — видимый обход = нарушение независимо от результата работы (SELF_REVIEW/OPS_TASK_AS_DEV в контракте).

Инструкции агенту — не гарантия; гарантией является сочетание «нельзя + заметят + не засчитают».

Аудит-след git: каждый переход этапа виден (коммиты + append-only review-файлы). Изоляция контекстов: сабагент физически не видит диалог ПМ (проверено живым тестом 2026-09-16).

---

## Контракты (интерфейсы этапов)

Полностью: [contracts/artifact_contract.md](contracts/artifact_contract.md). Кратко:

1. **Заказчик → БА → СА**: `requirements.md` — 7 разделов, FR-N/NFR-N, MoSCoW, преамбула ответственности, статусная модель (ЧЕРНОВИК → … → УТВЕРЖДЕН — только Заказчик), `docs/ba/answers_roundN.md` каждого раунда обязателен.
2. **СА → Разработка**: change-пакет (proposal, specs/дельты, **research.md** — альтернативы до design, design, tasks с **[P]-маркерами**) + `sdd.md`; Must покрыт, каждый Requirement со Scenario, атомарные задачи. Вход: УТВЕРЖДЕН + answers. Ревью: **architect**.
3. **СА → qa_impact**: при MODIFIED/REMOVED дельтах — вердикт по каждому затронутому тесту до qa_checklist.
4. **Чеклисты → кейсы**: полное покрытие CHK, негативы/границы для валидаций, дефекты спеки эскалированы.
5. **Автор ⇄ Ревьюер**: new/ → reviews/ → approved/; партии ≤12 (алфавитный сплит, последовательный запуск); approve без blocker/major.
6. **Автотесты только по approved**, TC-трассировка обязательна, time.sleep запрещен.
7. **Архивация**: все tasks [x] + зеленый QA + решение ПМ → дельты в master-spec → пакет в archive (неслитый archive = FLOW-ERROR).

---

## Принципы (CONSTITUTION)

Проектные принципы живут в `CONSTITUTION.md` проекта (шаблон: [templates/constitution.template.md](templates/constitution.template.md), практика из spec-kit, заполняется при factory init). Семь базовых: спека — источник правды; скриптуемое проверяется скриптом; изоляция ролей; секреты никогда не в артефактах ([REDACTED]); **отчету не верят — факт проверяют**; простота прежде полноты; внешние допущения покрыты проверкой (урок E10).

Принципы конвейера: линза «сабагент vs правило» (новая роль только при повторяемости + изоляции + своей зоне + экономике токенов); здоровье сабагентов (пинг транскриптов каждые 5–10 мин, петли = stop + перезапуск, артефакты деградировавшей сессии не используются); экономия контекста (goal ≤2500 символов, ссылки вместо пересказа, PLAN.md как внешняя память ПМ).

---

## Артефакты (где что лежит)

### В репозитории фабрики (ai-factory)

| Путь | Что это |
|---|---|
| `AGENTS.md` | Оперативные правила, роутинг ревью, здоровье сабагентов, уроки E16 |
| `PLAN.md` / `backlog/` | Статус + журнал делегаций / уроки и тюны (карта MAP.md + файлы item'ов, J22) |
| `docs/process-context.md` | Наследуемый процессный контекст (среда, дисциплина, уроки) — читается при входе |
| `docs/README-flow-control.md` | Производственный процесс всех флоу с развилками и валидациями |
| `agents/*.md` | Промпты 13 ролей + [реестр](agents/README.md) |
| `contracts/artifact_contract.md` + `contracts/flow_control_contract.md` | Контракты 1–7 + контракт Flow Control |
| `scripts/factory_bootstrap.py` | **Установка фабрики на новую машину** (окружение, state, вотчдог, приемка) |
| `scripts/factory_init.py` | **Развертывание конвейера на проект** (E15) |
| `scripts/flow_check.py` | Ворота флоу (state machine) |
| `scripts/flow_state.py` / `flow_transition.py` | Снимок фактов / разрешение действий (Flow Control) |
| `scripts/session_check.py` | Резервация зон, post-check, reconcile |
| `scripts/gate_runner.py` | Единый запуск ворот, provenance, audit JSONL |
| `scripts/flowctl.py` | Оркестратор: prepare/run/finish/status/reconcile |
| `scripts/flow_mode.py` | Переключатель shadow/enforcing |
| `scripts/pr_validate.py` | PR-ворота |
| `scripts/pm_bounds_check.py` | Границы записи ПМ: защищенные пути конвейера, role-промпты, `code-reviews/**` (J11), deploy-дерево — только `[ops]` (J26), env `PM_PROTECTED_EXCLUDE` |
| `scripts/session_watchdog.py` | Вотчдог DM-роутинга: залипшие ключи, тайтл `main`, dropped-делегации, субагент-контаминация (§2.8). Крон */2 |
| `scripts/delegate_watchdog.py` | Детектор обхода делегаций. Крон */5 |
| `scripts/pm_instruction_monitor.py` | Change-detector канала ПМ-0 (для крона pm-instruction-relay) |
| `scripts/codegraph.py` | Граф зависимостей кода |
| `scripts/smoke_static.py` | Смоук статики (класс DEF-002) |
| `scripts/session_archive.py` | Архив транскриптов + разбор неуспеха |
| `scripts/session_worktree.sh` | Worktree-изоляция параллельных сессий |
| `templates/` | Constitution, task_delegation |
| `archive/` | Промежуточные артефакты завершенных спайков/аудитов (выжимки J20/J8, e12-спайк, shadow-r6) — живые документы в `docs/` |
| `docs/e12-speckit-spike.md` | Спайк GitHub Spec Kit (вердикт: гибрид) |
| `openspec/specs/` | Спеки конвейера (источник правды правил) |

### В репозитории проекта (пример — ekotov-wiki)

| Путь | Что это | Этап |
|---|---|---|
| `CONSTITUTION.md` | Принципы проекта | init |
| `requirements.md`, `docs/ba/` | ТЗ + дословные ответы Заказчика | БА |
| `sdd.md`, `openspec/**` | Системный дизайн, спеки, change-пакеты, archive | СА |
| `architecture/map.md` | Карта: компоненты, допущения (проверено/не проверено), долг | architect |
| `backend/`, `frontend/` | Код продукта | dev |
| `tests/**` | Автотесты | qa_automation |
| `test-model/**` | checklists / new / reviews / approved / bugs / impact / regression | QA-контур |
| `code-reviews/**` | Ревью кода | code_reviewer |
| `deploy/` | RUNBOOK + deploy.sh (DRY_RUN, смоук) | devops |
| `.github/workflows/flow.yml` | CI-ворота | init |

---

## Релизный контур

1. Предрелизный регресс: полный `pytest tests/` на release-candidate.
2. Свертывание промежуточных артефактов (G9): аудит-след не трогается.
3. PR release-candidate → main: зеленый CI + решение Заказчика + design_validator на UI-дельты.
4. Деплой: `deploy/deploy.sh` (сначала DRY_RUN); смоук: health + страница + CSS + полный smoke_static; откат — бэкап БД + код из снапшота (RUNBOOK).
5. Пост-релизно: qa_regression_analyst актуализирует манифест; эскалации спеки → следующий change.

---

## Пилотный проект: ekotov-wiki

Личная wiki/канбан-доска (FastAPI + Jinja2 + vanilla JS + SQLite WAL; nginx TLS, systemd). **5 релизов в проде через конвейер** (прод v=r5.2, 2026-10-01): Р1 запуск (18 раундов БА, 24 задачи, 8 доменов) → Р2 категории/настройки → Р3 визуальный фундамент → Р4 профиль/view-модалка → Р5 аватары (кроп-виджет, карточка V3). Роли: architect и devops отработали живые задачи; design_validator — сверка реализованного UI с макетом (Р5); qa_runner — прогон/разбор регресса. Испытания конвейера: 2 прод-инцидента миграции (репетиция на копии — новое правило), rollover-инциденты сессий (J19 — дисциплина heartbeat); ревьюеры дважды поймали major до прода (rsync-аватары, кеш static_v).

**В работе: Р6 — этап A «Микросервисы» (change `add-microservices-full`)**: выделение search-сервиса в контейнере (`services/search/`, копии роутеров с трассировкой, замороженный контракт OpenAPI), nginx-маршрутизация сервисного семейства через фронт (X-Service, 503-деградация), отрезка search-маршрутов от монолита (f0fe4ec, xfail TC-openapi-202 снят). Задачи 1.1–1.5 закрыты через delegate_gate с независимыми ревью; далее — вертикаль auth-сервиса, приемка Заказчика и прод-деплой (2.3/2.4 — явная развилка Заказчика).
