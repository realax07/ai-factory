# Манифест pipeline в планах (слой 1 диспетчера пакетов)

Раннер v0: `python3 scripts/package_runner.py <PLAN-файл>` (слой 2).
Секция `pipeline:` объявляется в YAML-блоке PLAN-<id>.md — план остается
единым артефактом ПМ, раннер лишь исполняет объявленное.

## Пример

````markdown
# PLAN-my-package: …

**Флоу: 4**. …

```yaml
pipeline:
  package: my-package
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [backend/**, tests/unit/**]
      inputs: [openspec/changes/my-package/spec.md]
      task: реализовать FR-1..FR-3 по спеке, тесты обязательны
    - id: check
      run: gate:python3 scripts/flow_check.py
    - id: review-plan
      run: hermes:pm
```
````

## Правила

- `run:` — ровно один из трех видов:
  - `pi:<роль>` — Pi роль-пак `skills/pm-factory/pi/role-packs/<роль>/`.
    Раннер создает worktree (`scripts/session_worktree.sh`) **от текущего
    HEAD репо** (не origin/main — иначе в сцене нет ветки ПМ с планом и
    карточками бага), кладет `role-agents.md` пака в корень worktree как
    `AGENTS.md`; если в worktree уже есть `AGENTS.md` проекта, проектный
    файл **не перезаписывается** — роль кладется рядом как `AGENTS.pi.md`
    с пометкой «читай вместе с AGENTS.md проекта» (Pi читает оба), бриф
    упоминает нужный файл. Задает `PI_ZONE_WRITE` из `zones` и вызывает
    `pi --no-session -e ~/.pi/agent/extensions/zone-guard.ts -p <бриф>`.
    Без `zones` раннер берет зону роли целиком из реестра `agents/roles.json`
    (`<id>` → change-id пакета, J65.1); `zones` в манифесте ее только сужает;
    у роли без зоны в реестре (auditor, debug) `zones` обязателен. Провайдер/модель берутся из
    `settings.example.json` пака (дефолт `zai-glm`/`glm-5.3`); ключ pi берет
    сам из `~/.pi/agent/models.json` — раннер секретов не касается.
  - `gate:<команда>` — shell-команда в worktree; ненулевой exit → STOP
    (exit 2, диагностика; воротные отказы НЕ ретраятся). Env стенда (E6;
    список — ключ манифеста `pipeline.gate_env_strip: [VAR, …]`, без ключа —
    `EKOTOV_WIKI_BASE_URL`, `EKOTOV_WIKI_DB_PATH` пилота, `[]` — не срезать
    ничего, J64.5) срезается у gate-команды
    (эквивалент `env -u`): с ним pytest коллекция цепляет `tests/web`
    (нужен стенд) и падает с collection error. **Gate-команда сама отвечает
    за скоуп тестов** — пример узкого gate::

        run: gate:python3 -m pytest tests/gallery -q -k gallery
        # НЕ gate:python3 -m pytest tests/ -q: без стенда tests/web
        # коллекционируется и роняет ворота.
  - `stand:<команда>` — **подъем стенда** (J62): shell-команда в worktree
    (типовой пример — `bash scripts/qa_stand_up.sh reset`). Ненулевой exit →
    STOP. Из stdout парсятся строки `export VAR=value` (формат
    `scripts/qa_stand_up.sh`: ведущие пробелы и кавычки допустимы); ни
    одного export → STOP («стенд не отчитался env» — без env последующие
    стадии гарантированно красные). Отчитавшиеся переменные сохраняются в
    runner-state (`stand_env`) и **прокидываются в env всех последующих
    pi/gate стадий пакета** (при resume — тоже, stand-стадия не
    переисполняется). **Гашение стенда НЕ выполняется автоматически**:
    сироту подберет reaper/gc (`scripts/stand_reaper.py`) или ПМ гасит
    вручную (`bash scripts/qa_stand_up.sh stop` в worktree); после
    «докатан» раннер печатает напоминание.
  - `hermes:<роль>` — **стоп-точка ПМ**: раннер печатает
    `ЖДУ ПМ: stage <id>, роль <роль>` + состояние и выходит с кодом 0.
    Дальше — ручной диспатч ПМ (делегация, приемка, push); повторный запуск
    раннера после ПМ-действий докатывает пакет: hermes-шаг помечен в state
    статусом `waited` и пропускается (раннер факт ПМ-работы не проверяет —
    запускай повтор, когда ПМ-шаг реально сделан).
- `optional: true` (опциональные стадии, «шаги могут быть опциональными,
  типа дизайнера») — только для pi/gate-стадий: отказ НЕ останавливает
  пакет. Gate fail / verdict fail / pi fail / таймаут → стадия помечается
  в state статусом **`skipped`**, в журнал плана и stderr пишется
  **WARNING**, раннер идет дальше (при pi-успехе — обычный проход, включая
  gate/verdict). Обязательные стадии (без `optional`) — STOP как раньше.
  На resume skipped-стадии не переисполняются (аналог done/waited —
  ретраев нет). У stand/hermes ключ не действует: молчаливый пропуск
  stand-стадии только переносит гарантированный отказ глубже (env стенда
  нужен следующим стадиям), hermes — ручная точка ПМ. Типовое применение —
  design/design_check (задачи без фронт-дельты) и deploy (боевой деплой —
  вне автомата).
- Последовательность v0 — строгая, без параллелей; `depends[]`
  игнорируется с WARNING, если нарушает порядок.
- `gate` (опциональное поле pi-шага) — команда-проверка в worktree после
  успешного pi; ненулевой exit → STOP.
- `verdict` (опциональное поле pi/gate-стадии, J62 → J65.4) — **вердикт-ворота**:
  отображение `{file: путь}`. После успешной стадии раннер читает вердикт
  файла (в worktree) **единым парсером** `flow_check.parse_verdict` — тем же,
  что у pr_validate и gate_runner:
  - вердикт — заголовок `## Вердикт: approve|return` (или Одобрить/Вернуть),
    решает **последний** такой заголовок файла (повторная проверка,
    дописанная в конец, отменяет прежний вердикт);
  - approve → проход; return, «Не одобрить», заголовок с обоими словами
    (шаблон) → STOP exit 2 **«ЖДУ ПМ: возврат ревью»**; заголовка нет
    (вердикт прозой, `Вердикт: …` без `##`) → STOP;
  - на pi-стадии строка `Commit: <sha>` (также `**Commit:**`, `- Commit:`),
    если есть, обязана совпасть с HEAD до стадии ревью — иначе STOP STALE;
    gate-стадия «коммита до ревью» не знает — там не сверяется;
  - на pi-стадии approve/return фиксируется **аудит-запись provenance** —
    `<план>.runner-reports/<stage>-<попытка>.provenance.json`: reviewed commit
    (HEAD до ревью), digest диффа от начала пакета, ревьюер — делегация
    стадии, авторы — pi-стадии других ролей с коммитом после предыдущего
    ревью. Запись — для аудита, рядом с review-файлом sidecar не кладется
    (его читают ворота flow_transition/J10 со своей семантикой); финальный
    PR пакета по-прежнему требует `Reviewer-Delegation` для J10.

  Стадия в state — `stopped`; повторный запуск переисполняет ее, ретраев нет.
  Ключ `contains` устарел: принимается и игнорируется с WARNING::

      - id: code_review
        run: pi:code-reviewer
        zones: [code-reviews/my-package/review-001.md]
        verdict:
          file: code-reviews/my-package/review-001.md
- Таймаут вызова: env `PIPELINE_TIMEOUT` (сек), дефолт 1800; таймаут и
  ненулевой exit pi/gate/stand → STOP: exit 2, хвост stdout/stderr ≤30 строк.
- Состояние: `<план>.runner-state.json` рядом с планом (путь печатается
  в начале прогона и в диагностике STOP — файл не «теряется» после
  прогона); resume пропускает done/waited-стадии, чужой state (другой
  package/plan) — RUNNER-STOP. Хвост stdout/stderr каждой стадии
  (≤50 строк) сохраняется в state (`stdout_tail`/`stderr_tail`) и в лог
  `<план>.runner.log` — вывод успешных стадий тоже доступен после
  прогона. После каждого stage — строка в секцию «## Журнал раннера»
  плана.

## Ворота pi-стадии

pi-стадия проходит тот же жизненный цикл ворот, что и делегация
`delegate_task` (движок фабрики, `scripts/flowctl.py`):

1. **Вход** — `flowctl prepare --repo <wt> --worktree <wt> --path <zones>`
   по этапу роли в STAGE_TABLE флоу пакета (`--change <package>`). **Снимок
   фактов — из worktree пакета:** работа прошлых стадий (change-пакет СА,
   ревью архитектора) живет в ветке пакета, а не в основном клоне; поэтому
   PLAN-<package>.md и входы пакета должны быть **закоммичены** до запуска
   раннера (worktree создается от HEAD), а правки ПМ на hermes-стопах
   (утверждение требований и т.п.) — коммитом в ветку пакета (путь worktree
   печатается на стопе). Зона в реестре — по основному клону репозитория
   (`session_check.git_main_root`), конфликт с делегациями виден. Проверки: план релиза, требования,
   политика зон роли (`agents/README.md`, CLI только сужает), конфликт зон с
   активными сессиями того же repo (`ZONE_CONFLICT` — реестр общий с
   делегациями). Отказ (DENY/UNKNOWN) — STOP до pi с кодом причины;
   затем `flowctl run`.
2. **Агент** — pi в worktree; ролевой AGENTS-файл раннера после pi
   удаляется (в дифф и коммит стадии не попадает).
3. **Выход** — `flowctl finish --gate-scope post_agent`: фактический
   git diff ⊆ суженная зона + гейты этапа (flow_check …). `returned`/
   `blocked` — STOP с дефектами (`OUT_OF_ZONE`, FAIL гейта). `provisional`,
   где не выполнен только `pr_validate` (нет PR-контекста), стадией
   засчитывается: `pr_validate` — ворота PR в CI (flow.yml).
4. **Коммит стадии** в ветку пакета (`[pipeline] <package>/<stage>: pi:<роль>
   (correlation <id>)`, без SESSION.md) и закрытие резервации
   (finished → closed): следующая стадия стартует от чистого дерева.

Ключи стадии для ворот (необязательные): `action` — этап STAGE_TABLE, если
роль участвует в нескольких (по умолчанию — первый этап роли во флоу);
`task_id` → `--task` (dev_task Флоу 1 требует задачу tasks.md);
`approval_ref` → `--approval-ref` (этап с утверждением Заказчика, например
create_change).

- **Роль без этапа во флоу** (ba, regress_runner, devops вне Флоу 3) —
  решение flowctl не выносится: резервация зоны по политике роли и
  post-check диффа (`session_check`), WARNING `ROLE_WITHOUT_STAGE`. Роль
  вне политики зон (debug, auditor) — STOP `ZONE_OUTSIDE_POLICY`.
- **Зоны стадии — в рамках политики роли.** Зона шире политики — STOP
  `ZONE_OUTSIDE_POLICY` (например, `test-model/reviews/**` у code-reviewer:
  политика — `code-reviews/*/review-*.md`). Для zone-guard зона с glob в
  середине сводится к конкретному префиксу (`code-reviews`); точная сверка
  — по диффу на выходе.
- **Отказ после входа:** обязательная стадия — STOP, зона и дерево держатся
  (`needs_attention` / `finished`) до разбора; повторный запуск раннера
  сначала освобождает зону прошлой попытки (`released`, worktree и файлы
  сохранены), затем проходит ворота заново. optional-стадия — `skipped`:
  ее изменения (и коммиты агента поверх базы стадии) откладываются в
  `git stash` worktree с меткой `package_runner: <package>/<stage> попытка N`
  (не удаляются и не попадают в дифф следующей стадии), зона освобождается.
- **Перед коммитом** дифф повторно сверяется с зоной резервации: файл вне
  зоны, появившийся после приемки (артефакт гейта), — отказ стадии.
- Запись цикла flowctl `provisional` (не выполнен только `pr_validate`)
  получает пометку раннера (`package_runner`: коммит, «pr_validate — на PR
  CI пакета»); повторный `flowctl finish` по закрытой резервации движок
  отклоняет (`blocked`) — зона не переоткрывается.
- Env раннера для ворот: `PIPELINE_OPENSPEC_CMD` — команда OpenSpec CLI для
  гейта `openspec_validate` (дефолт flowctl — `npx openspec`);
  `AI_FACTORY_HOME` — где искать движок, если раннер запущен из копии вне
  фабрики. Движка нет — pi-стадия STOP `FACTORY_ENGINE_MISSING`.
- Реестр и state — как у делегаций (`~/.hermes/state/active_sessions.json`,
  `flowctl_state.json`); env `PIPELINE_FLOW_REGISTRY` /
  `PIPELINE_FLOW_STATE` переопределяют. Отчет стадии для finish —
  `<план>.runner-reports/<stage>-<попытка>.md`.

### Опциональные стадии (`optional: true`)

Комментарий Заказчика: «шаги могут быть опциональными, типа дизайнера».
Ключ стадии `optional: true` — семантика для pi/gate-стадий:

| Отказ | Обязательная (по умолчанию) | `optional: true` |
|---|---|---|
| gate fail / gate-таймаут | STOP exit 2 | `skipped` + WARNING, дальше |
| pi fail / pi-таймаут | STOP exit 2 | `skipped` + WARNING, дальше |
| verdict fail (нет маркера) | STOP «ЖДУ ПМ: возврат ревью» | `skipped` + WARNING, дальше |
| pi + gate ok, verdict ok | `done` | `done` (обычный проход) |

- `skipped` пишется в state; в «Журнал раннера» плана — строка с WARNING;
  в лог `<план>.runner.log` — статус SKIPPED с хвостами stdout/stderr.
- resume: skipped-стадии НЕ переисполняются (аналог done/waited, ретраев нет).
- stand/hermes ключ игнорируют: stand без env стенда роняет следующие стадии
  (молчаливый пропуск только переносит отказ глубже), hermes — ручная точка.

### Dev по задачам tasks.md (`per_task: true`, J64.13)

Правило 11 и J31: одна задача tasks.md — одна dev-сессия. Ключ `per_task:
true` у pi-стадии (без `task_id` и `verdict`) разворачивает ее в
под-стадии `<id>-<задача>` перед запуском:

```
    - id: dev
      run: pi:dev
      per_task: true            # → dev-1.3, dev-1.3-review, dev-1.2, …
      review: code-reviewer     # пара ревью на каждую задачу
      task: реализовать задачу по спеке
```

- только `pi:dev`, без `task_id`, `verdict` и `optional`;
- задачи — открытые `- [ ] N.M` из `openspec/changes/<package>/tasks.md`
  worktree пакета (tasks.md может создать SA этим же прогоном), кроме
  QA-раздела 6 и меток `[ops]`/`[docs]`/`[design]`;
- порядок — по зависимостям «(после N.M)» / «depends:», при равенстве —
  порядок файла; цикл, нет tasks.md, зависимость на открытую не-dev или
  несуществующую задачу — STOP сразу;
- `review: <роль-пак>` — после каждой dev-под-стадии пара
  `<id>-<задача>-review` (этап code_review по задаче, вердикт
  `code-reviews/<package>/review-<задача>-001.md`): ворота dev_task
  следующей задачи требуют закрытую зависимость с approve-ревью (J10).
  Задачи зависят друг от друга, а `review:` не задан — STOP на развертке;
  чекбокс задачи в tasks.md закрывает dev (его зона);
- каждая под-стадия — своя pi-сессия с `--task N.M` (ворота dev_task по
  задаче), свой коммит; список задач фиксируется в state при первой
  развертке — resume идет по тому же списку;
- ревью по волне UI (J20) — независимые задачи без `review:` и отдельная
  стадия ревью с `task_id` волны.

## Полный пример манифеста Флоу 1 (требования → релиз)

Скелет конвейера Флоу 1 для пакета `my-package`: требования → approve →
создание change → архитектурное ревью → design/design_check (опциональные)
→ dev → код-ревью → QA-кейсы → ревью кейсов → автоматизация →
impact-анализ → регресс → архивация → релиз → deploy (опциональная,
релизная инфра). Стадии `hermes:` — ручные стоп-точки ПМ (диспатч
делегаций, приемка, push, merge); раннер их «докатывает» при повторном
запуске после ПМ-действий.

````markdown
# PLAN-my-package: <название пакета>

**Флоу: 1**. Спека: openspec/changes/my-package/. Пакет едет раннером v0.

```yaml
pipeline:
  package: my-package
  flow: 1
  stages:
    - id: requirements
      run: pi:ba
      zones: [requirements.md, docs/ba/*]
      inputs: [docs/backlog/my-package.md]
      task: черновик требований по брифу Заказчика
    - id: approve
      run: hermes:pm          # СТОП-ТОЧКА: ПМ выносит черновик требований
                              # Заказчику и вносит правки; repeat раннера —
                              # когда требования утверждены
    - id: create_change
      run: pi:sa              # СА пишет proposal/spec/design/tasks
      zones:
        - openspec/changes/my-package/proposal.md
        - openspec/changes/my-package/design.md
        - openspec/changes/my-package/tasks.md
        - openspec/changes/my-package/specs/**
        - sdd.md
      approval_ref: decisions/my-package-requirements.md  # этап с утверждением
      inputs: [requirements.md, docs/ba/answers_round1.md]
      gate: openspec validate --strict
    - id: arch_review
      run: pi:architect
      zones:
        - architecture/**
        - test-model/reviews/my-package/review-001-architecture.md
      inputs:
        - openspec/changes/my-package/proposal.md
        - openspec/changes/my-package/design.md
      verdict:
        file: test-model/reviews/my-package/review-001-architecture.md
    - id: design              # дизайн-макеты/токены ДО кода (J36); опциональна:
      run: pi:ui-designer     # задачи без фронт-дельты — падение → skipped,
      zones: [design/**]      # пакет едет дальше (не STOP)
      inputs: [openspec/changes/my-package/design.md]
      optional: true
    - id: design_check
      run: pi:design-validator
      zones: [test-model/reviews/my-package/review-001-design.md]
      inputs: [design/]
      verdict:
        file: test-model/reviews/my-package/review-001-design.md
      optional: true          # отказ вердикта → skipped, не STOP
    - id: dev
      run: pi:dev
      zones: [backend/**, frontend/**, services/**, src/**, tests/unit/**]
      task_id: "1.1"          # задача tasks.md (dev_task требует задачу);
                              # на все задачи пакета — per_task: true (J64.13)
      inputs:
        - openspec/changes/my-package/spec.md
        - openspec/changes/my-package/design.md
      gate: python3 scripts/flow_check.py
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/my-package/review-001.md]
      verdict:                # вердикт-ворота: return / нет заголовка
        file: code-reviews/my-package/review-001.md   # → STOP «ЖДУ ПМ:
                              # возврат ревью», ПМ возвращает дифф dev, repeat
    - id: qa_cases
      run: pi:qa-case-author
      zones: [test-model/new/my-package/**]
      inputs:
        - openspec/changes/my-package/spec.md
        - openspec/changes/my-package/sdd.md
    - id: case_review
      run: pi:qa-case-reviewer
      zones: [test-model/reviews/**, test-model/approved/**]
      inputs: [test-model/new/my-package/]
      verdict:
        file: test-model/reviews/my-package/review-cases-001.md
    - id: qa_stand             # подъем стенда (J62): stdout стенда
      run: stand:bash scripts/qa_stand_up.sh reset   # (export EKOTOV_WIKI_*)
                              # прокидывается в env qa_auto/design/regress;
                              # гашение НЕ автоматом — reaper/gc подберет
    - id: qa_auto
      run: pi:qa-automation
      zones: [tests/api/**, tests/web/**, test-model/bugs/*]
      inputs: [test-model/approved/my-package/]
    - id: impact
      run: pi:qa-impact-analyst
      zones: [test-model/impact/my-package.md]
      inputs:
        - openspec/changes/my-package/specs/
        - test-model/regression/manifest.md
    - id: regress
      run: pi:regress-runner  # роль без этапа во Флоу 1 — ворота зоны
      zones: [test-model/regress/my-package/**]
      inputs: [test-model/impact/my-package.md]
    - id: archive
      run: hermes:pm          # СТОП-ТОЧКА: ПМ приемлет пакет (задачи tasks.md,
                              # мокапы в design/archive/, кейсы approved/),
                              # push ветки и PR
    - id: release
      run: hermes:pm          # СТОП-ТОЧКА: ПМ merge PR после зеленого CI,
                              # тег релиза, архивация change-пакета
    - id: deploy              # релизная инфра (devops, J62-остаток): runbook,
      run: pi:devops          # деплой-скрипты (бэкап/EXPECTED_COMMIT/смоук/
      zones: [deploy/**, ops/**]            # DRY_RUN), миграции — в worktree.
      optional: true          # БОЕВОЙ деплой прод-стека — только по
                              # утверждению ПМ (hermes-стоп), накатку
                              # выполняет Заказчик; падение стадии →
                              # skipped + WARNING, пакет едет дальше
```
````

### Пояснение hermes-стопов

- `approve` — единственная точка воли Заказчика: утверждение требований.
  Раннер останавливается со статусом `waited`; повторный запуск — когда ПМ
  зафиксировал утвержденную спеку.
- `create_change` — pi:sa пишет change-пакет (зоны openspec + sdd), strict-валидация
  как gate; arch_review — pi:architect с вердикт-воротами «Одобрить».
- `design`/`design_check` — мокапы ДО кода и их валидация (J36), обе стадии
  `optional: true`: падение/отказ вердикта → skipped + WARNING, пакет едет
  дальше; задачи без фронт-дельты — стадии можно удалить (или отметка
  design-not-required).
- `deploy` — pi:devops (J62-остаток), `optional: true`: подготовка релизной
  инфры в worktree (runbook, деплой-скрипты, миграции, чек-листы). БОЕВОЙ
  деплой прод-стека — только по утверждению ПМ (hermes-стоп); живой прод
  devops читает, реальные накатки выполняет Заказчик.
- Эскалация `pi:debug` (СРЕДА/КОД/ТЕСТ) — НЕ стадия: ПМ запускает при застревании
  dev/qa-стадии параллельно источнику (J35).
- `archive`/`release` — ручные: приемка артефактов, push, PR/merge, тег.
  Раннер факт ПМ-работы не проверяет — repeat запускается, когда шаг
  реально сделан (иначе — повторное «ЖДУ ПМ» без вреда: стадия уже `waited`).
- Останов по verdict/gate/stand (`ЖДУ ПМ: …` на stderr, exit 2) — тоже
  ручной контур: разбор ПМ, правка (доработка dev, возврат ревью, гашение
  чужого стенда) и repeat раннера; остановленная стадия переисполняется
  целиком (ретраев нет).
