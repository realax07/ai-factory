# Карта прод-окружения ekotov-wiki

Фиксируются факты, проверенные командами. Перепроверять перед каждым деплоем — окружение может измениться.

## Компоненты

- **Приложение**: FastAPI/uvicorn, `127.0.0.1:8377`, корень `/opt/ekotov-wiki` (service `ekotov-wiki`, systemd). `/opt` — файловая копия **без `.git`**: обновление только rsync из локального клона `~/ekotov-wiki` (исключения: `.git/`, `.env`, `backend/.venv/`, `__pycache__/`, `.pytest_cache/`).
- **Системный юзер сервиса и владелец файлов/БД**: `wiki`. Все операции — `sudo -u wiki`; Заказчик запускает скрипты из-под root.
- **Фронт-вебсервер**: nginx, TLS на **10443** (не 443), конфиг `/etc/nginx/sites-enabled/ekotov-wiki`: `location /static/` → `alias /opt/ekotov-wiki/frontend/static/` с `expires 7d; Cache-Control: public`; остальное → proxy на 8377. Self-signed сертификат (Заказчик открывает `https://<ip>:10443` с подтверждением).
- **БД**: SQLite `/var/lib/ekotov-wiki/wiki.db`. Бэкапы: `/var/backups/ekotov-wiki/wiki-pre-<релиз>-<дата>-<время>.db` через `sqlite3 ".backup"` (без остановки сервиса).
- **Венв**: `/opt/ekotov-wiki/backend/.venv`; зависимости — `backend/requirements.txt`.
- **Снапшот для отката кода**: `~/ekotov-wiki-R1-snapshot` (копия /opt; `.env` туда не копируется — используется живой из /opt).

## Конвенции

- Миграция категорий: `python -m app.migrate_categories` (идемпотентна, автосверка, exit 1 при расхождении); схема — `python -m app.db`. Оба — **строго из cwd=`backend`** и `DB_PATH=/var/lib/ekotov-wiki/wiki.db`.
- Кеш-бастинг: `templates.env.globals["static_v"]` в `backend/app/pages.py`, бамп при каждом релизе со статикой.
- Деплой-скрипты живут в репо: `deploy/deploy.sh` (канонический, параметризован APP_DIR/DB_PATH/PORT/PROD_URL/SERVICE/EXPECTED_COMMIT/DRY_RUN; в шаге 0 сверяет хеш клона) + обертки вида `deploy/deploy-<цель>.sh` для Заказчика (вычисляют EXPECTED_COMMIT из HEAD на лету). Прежний `~/deploy-*.sh` устарел. Git-вызов под root в клоне требует `-c safe.directory=<клон>`.
- Клон `~/ekotov-wiki`: ветка main — источник истины; сабагенты конвейера пушат ветки, ПМ мержит. Прод — только rsync, клоны/ветки НЕ трогает.

## GitHub-защита main (rulesets, проверено API 2026-10)

Ruleset на main: rules `pull_request` + `non_fast_forward` + required check `test-flow-control`, enforcement active, bypass never. Прямой push в main отклоняется (GH013) — merge только `gh pr merge` после зеленых чеков. Токен машины (роль write) читает правила через `GET /repos/{repo}/rules/branches/main` (legacy `/branches/main/protection` дает 404 и без защиты — не выводить «защиты нет» из 404, проверять живым probe-push).

Правило для ПМ: локальный merge в main с последующим push — нарушение (был случай, откачен); CI-job переименовывать ДО добавления его в required checks — первый PR после включения нового required check навсегда BLOCKED (чек с новым именем появляется только после мержа переименования).

## Ядро Flow Control в проекте (с 2026-10)

В `scripts/` живут и ядро Flow Control: `flow_state.py`, `flow_transition.py`, `session_check.py`, `gate_runner.py`, `flowctl.py`, `flow_mode.py`, `role_zone_policy.py` (источник — фабрика `~/ai-factory/scripts/`, синхронизация при обновлении фабрики). Режим — `flow_mode.py show/set` (shadow/enforcing; текущий — enforcing). Журналы: `decisions/` (решения Заказчика), `releases/` (релизные решения). Контракт — `contracts/flow_control_contract.md`, скелет флоу для сабагентов — `skills/factory-flow/`.

## Устаревшее/историческое

- static_v: r4.x → **r5.2** (финал; перед деплоем зафиксирован r5.1, добит хотфиксами до r5.2 — не деплоившийся промежуточный бамп перезаписывается, одно значение на фактически выкатываемый релиз).
- Регресс-эталон Р5: api 187 passed / 9 skipped / 2 xfailed; web 150 passed / 1 skipped.
- Смоук-маркер релиза: `curl -sk https://<ip>:10443/login | grep -o 'v=r5\.[0-9]'` — двумя командами (health + маркер) подтверждается и живость прода, и факт выкатки.
- Прод-деплой подтвержден 2026-10: health OK, страницы с `?v=r5.2`.
- Остаточные риск-пункты Р5 (бэклог продукта): EXIF-transpose на сервере (avatar.py), текст fallback-сценария спеки (center-crop → нормализация), сайдбар на 375px при открытом кропе (вне зоны), закрытие change-пакетов Р4/Р5 (архивация).

## Релиз 4 (add-r4-user-profile-ticket-view) — деплой-факты Р4

- Новый прод-путь: `location /avatars/` → `/var/lib/ekotov-wiki/avatars/` (вне rsync-корня, владелец wiki:wiki, `expires 7d; Cache-Control public`). Прод-конфиг требует ручного root-вставления блока ДО деплоя (deploy.sh шаг 5b гейтит: нет блока — FAIL с инструкцией). Шаблон — `deploy/nginx-ekotov-wiki*.conf` (блоки идентичны в обоих файлах).
- Миграция Р4: `python -m app.migrate_r4` — ALTER users (+display_name/role/bio/avatar_path/avatar_updated_at), ALTER tasks (+creator_id/assigned_to_id), бэкфилл creator=owner/assigned=owner, роли owner=PM/wife=PE, автосверка NFR-9 (exit 1 при расхождении). Требует SECRET_KEY в env. Идемпотентна.
- Порядок для СУЩЕСТВУЮЩЕЙ прод-БД: схема (базовая часть SCHEMA_SQL, без Р4-индексов — init_db определяет по отсутствию creator_id) → migrate_r4 (ALTER + бэкфилл + Р4-индексы) → повторная схема no-op. Свежая БД: полный SCHEMA_SQL сразу.
- Новый эндпоинт `GET /api/suggestions/users` — read-only (подсказки фильтров поиска; DISTINCT логины из tasks.creator_id ∪ assigned_to_id), вне exempt — 401 без сессии.
- static_v: r3.2 → **r4.0** (финальный релизный бамп, C-5).
- Регресс-эталон Р4: api 180 passed / 9 skipped / 2 xfailed; web 115 passed / 1 skipped (известные flakes: playwright route-disposal в test_navigation_search_ui, dnd-гонка в test_r3_dnd_ui — изолированные прогоны зеленые).
- Оба имени аватарной переменной обязательны на стенде: сервер читает `AVATARS_DIR`, тесты — `EKOTOV_WIKI_AVATARS_DIR` (в один tmp-каталог); без второй avatar-тесты падают `expected str… not NoneType` до запросов.
- Незакрытые риск-пункты Р4 (бэклог): J25 живой дизайн-макет — ЗАКРЫТ в Р5 (design/avatar-crop-v3.html — принятый артефакт Р5, правило «макет обновляется артефактом UI-задачи» действует), J26 deploy/прод-активности только через devops-сабагента.

## Релиз p15-wiki-1 (add-wiki) — деплой-факты

- Миграция: `python -m app.migrate_wiki` — таблицы pages/page_versions (FK pages.parent_id→pages RESTRICT, page_versions.page_id→pages CASCADE, author_id→users), 3 индекса; идемпотентна (повтор no-op, сверка «ОК»); монолит — владелец схемы. Репетиция на копии прода (consistency-copy контейнером от root: python sqlite3 .backup; sqlite3 CLI в python:slim нет) обязательна (NFR-32).
- Финальный RELEASE_TAG: `p15-wiki-1`; static_v: p14-responsive-1 → **p15-wiki-1**; 19 wiki-API (CRUD/дерево/версии/revert/LIKE-поиск по plain-тексту) + сайдбар «Wiki» (todo-бейдж — хвост 6.x).
- Регресс-эталон add-wiki: api-wiki 27 passed, sanitize 35, web p15 29 passed, регресс ядра 274 passed; perf p95 (1000 стр/10К версий): открытие 26–38ms, дерево 42–70ms, версии 20–87ms, поиск 32–110ms (цели NFR-30 300/500ms — запас 3–10×).
- Порядок обновления контурных файлов: contracts/openapi.json перегенерация scripts/export_openapi.py при каждом добавлении роута (рассинхрон ловится pr_validate/QA, не компиляцией).
- Открытые эскалации после релиза: (1) снять :ro с wiki-data маунта backup в compose (сейчас immutable-fallback: суточный бэкап может не включать WAL-хвост — WARNING в логах backup это норма); (2) хвосты 6.1: G2 (422 на лимиты загрузки — не проверено живьем), G5 (явный тест 302 аноним /wiki/{id}), снятие todo-бейджа Wiki, обновление wiki-stub теста, 3 неточности чеклиста CHK-wiki-1/20/27.

## Релиз p15-wiki-7 (финал живой приемки add-wiki) — деплой-факты

- Прод на образах p15-wiki-7, static_v = p15-wiki-7; пакет принят Заказчиком (протокол `test-model/reports/add-wiki/REPORT-4.5-acceptance.md`), заархивирован как `openspec/changes/archive/2026-10-11-add-wiki/`.
- Возвраты живой приемки, отлившие финальную функциональность: регистронезависимый поиск (casefold через wiki_nocase — SQLite lower() опускает только ASCII, кириллица), дерево без meta-счетчика (вытеснял названия), ellipsis+title-tooltip на названиях, state раскрытия дерева в cookie `wiki_tree_expanded` (24ч, дефолт свернуто, только фронт), «Создать страницу» на статье подставляет текущую родителем (?create=1&parent={id}), масштаб изображений как в Confluence (Оригинал/480/240/свой px, валидация 16..4096; sanitizer пропускает img width только целым).
- Против j41: PLAN-заглушки старых пакетов вымирают при архивации (add-wiki — закрыта; остались add-responsive-mobile и add-ui-polish-r8 — архивировать по мере готовности).
- Служебные артефакты отладки чистить после цикла: probe-юзер layoutprobe и probe-сессии удалены из прод-БД после приемки; playbook живой пробы раскладки (инъекция сессии в копию прод-БД через docker cp) — в SKILL.md, разделе «Жалоба на вёрстку».
