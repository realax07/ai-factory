# Рекомендации агенту-наследнику (саммари памяти и скиллов predecessor-сессии)

> Документ для агента, принимающего конвейер. Здесь сжато то, что копилось
> в памяти сессий: среда, процесс, инструментальные грабли, стиль. Прочитай
> целиком перед первым действием. Оперативное состояние — PLAN.md,
> backlog/MAP.md; это файл — «как работать», не «что делать».

## 1. Роль и стиль общения

- Заказчик — **Егор Игоревич Котов**. Стиль ответов задан явно: викторианский
  главный инженер — обращение «Сэр», лаконично, технически точно, без воды.
  Распространяется на все сессии.
- Доклад всегда содержит этапы ворот: `prepare/reserve/check/gates/
  provenance: PASS/DENY/UNKNOWN/SKIPPED` — если делал проверки, покажи их
  вердикты, а не «все ок».
- **Честность — абсолютная.** На вопрос «ты сделал или записал в бэклог?»
  отвечай честно. Не выдумывай привязки («автотеста нет — прогон REPORT-4.x
  скриптом»). Репортинг несуществующего результата = потеря доверия навсегда.
- Оборванные вводные не додумывай — переспроси. Вопросы Заказчику —
  нумерованным списком ОВ-N.

## 2. Среда

| Факт | Значение |
|---|---|
| Фабрика | `/home/openclaw/ai-factory` (etalон процессов, скиллов, скриптов) |
| Проект | `/home/openclaw/ekotov-wiki` (пилот; прод: проект `ekotov-wiki-par`, порт 10443, `https://127.0.0.1:10443`) |
| Venv проекта | `source /home/openclaw/venvs/wiki/bin/activate` (playwright 1.63 sync) |
| Тесты фабрики | системный python3 (venv нет) |
| SRC_DIR деплоя | `/home/openclaw/ekotov-wiki` — **НЕ /opt** |
| Деплой | `RELEASE_TAG=<tag> MIGRATE_MODULE=app.migrate_wiki PROJECT=ekotov-wiki-par SRC_DIR=... bash deploy/deploy.sh`; статика по `?v=<tag>` |
| Сессии/реестры | `~/.hermes/state/` (active_sessions.json, flow-bypass-decisions.json) |
| Плагин flow-enforcer | `~/.hermes/plugins/flow-enforcer/` — после изменений в фабрике **копируй вручную** (`cp plugins/flow-enforcer/*.py ~/.hermes/plugins/flow-enforcer/`), он не обновляется сам |
| Секреты | в логи/саммари НЕ сохранять; встречавшиеся токены — [REDACTED] |

## 3. Процесс: Флоу 1–5 и маркер делегации

- Пять флоу: 1 полный (БА→СА→…), 2 багфикс, 3 хотфикс (incident_ref),
  4 обслуживание (chore), 5 экспресс (slug, PLAN не нужен, ретроспективный
  артефакт express_close). Классификация флоу объявляется ДО запуска.
- **Каждая задача стартует с плана в .md** (PLAN-<change>.md или
  test-model/bugs/PLAN.md с «Флоу: N») — J41, проверяет flowctl.
- **Маркер делегации** (первой строкой goal, обязательный — его валидирует
  pre_tool_call-плагин):
  `flow: flow=<1-5> role=<роль> repo=<путь> scope=<id> task=<N>`
  + для продуктовых задач **обязательно `paths=<файл1,файл2>`** (иначе
  PATHS_MISSING — честный отказ, введено BUG-AF-RECHECK-001); `kind=docs`
  легален только для docs_task/chore_task.
- scope по флоу: change-id / `BUG-<КОМПЛЕКС>-NNN` (BUG-001,
  BUG-AF-RECHECK-001 — единая грамматика enforcer+flow_check) / incident-id /
  chore-slug / slug.
- Ролевая модель: **ПМ не пишет прод-код** — изменения через `delegate_task`
  (dev/devops/code_reviewer/design_validator/qa_automation/leaf); ПМ коммитит,
  пушит, мержит PR, деплоит. Исключение допускается явно и с оговоркой
  (прецедент: дозавершение PO-рефакторинга при мертвом пуле провайдера).
- Ревью-цикл: dev → code_reviewer (для значимых диффов — адверсариально:
  персоны Саботажник/Новичок/Security, skills/code-review §4b) → merge.
  Reviewer-Delegation в review-файле обязателен (self-review не засчитывается).
- Действует вердикт **актуальной итерации** ревью: поздний return отменяет
  старый approve (BUG-AF-RECHECK-003).
- bypass-flow — только по записи в
  `~/.hermes/state/flow-bypass-decisions.json` (repo/scope/action/expires,
  пишет человек по подтверждению Заказчика); подстрока в goal сама ничего
  не решает (BUG-AF-RECHECK-002).

## 4. Инструментальные грабли (проверено болью)

1. **CI re-run переигрывает старый payload** — правка title/body PR не
   перезапускает проверки с новыми данными; нужен новый push.
   Title/body правь через `gh api repos/.../pulls/N -X PATCH --input file.json`
   (обычный `gh pr edit` падает на GraphQL Projects-classic deprecation).
2. **pr_validate**: в title/body PR обязателен маркер `[BUG-NNN]` /
   `[change-id]` / `[chore]` / `[docs]` / `[ops]`; для бага репорт должен
   матчиться glob'ом `BUG-<NNN>-*.md` и содержать раздел «Статус».
   Не выдумывай имена репортов вне этой грамматики (см. BUG-AF-RECHECK
   переименование).
3. **Лимиты провайдера**: сабагенты умирают HTTP 429 (Weekly/Monthly Limit
   Exhausted) — пул встает до reset-даты. Частичная работа остается в
   worktree закоммиченной/незакоммиченной — осмотри `git log`/`git status`
   ветки перед перезапуском делегации и передай наследнику контекст
   «сделано/осталось».
4. **terminal timeout cap 600s**: длинные прогоны (полный e2e ~10 мин)
   — сразу background + уведомление; foreground timeout >600s уходит в
   background автоматически.
5. **Базлайны через worktree**: `git worktree add /tmp/wt-main main` → прогон
   того же файла на main → честная дельта. Обязательно при «рефакторинг не
   должен ничего сломать». Убирай worktree после.
6. Пред-существующие провалы тестов проекта (задокументированы, не твой
   регресс): gallery/crop-фикстуры (guard BUG-008, connection errors ~5),
   sanitize 35 errors (стенд), test_search*.py 9 failed, teardown-шум
   playwright (conftest.py:277). Прогон web-набора: ориентир 218 passed /
   12 failed / 15 errors (после волны 1 PO-рефакторинга).
7. **Флаки-тесты** не чини на месте: таксономия в skills/playwright-pro
   (timing/isolation/environment), локально 3 прогона перед выводами.

## 5. Скиллы: как устроены и как дополнять

- Фабрика `skills/` — 12 скиллов; формат как в alirezarezvani/claude-skills:
  SKILL.md (инструкции) + scripts/ (исполняемые инструменты скипта) +
  references/ (справочники). Скрипты вызываются из инструкций SKILL.md
  (пример: skills/code-review/scripts/code_quality_checker.py).
- Новые скиллы/скрипты обязательно: (1) в SKILL_DIRS в
  `scripts/factory_init.py` (иначе не уедут в новые проекты), (2) в таблицу
  скиллов агента в `agents/<role>_agent.md`, (3) в skills/README.md,
  (4) зеркалирование в проект (ekotov-wiki/skills/) — там тонкий клиент.
- Источник практик: github alirezarezvani/claude-skills (MIT) — mined
  многократно; перед переносом прогоняй их скрипты на нашем коде и фиксируй
  false positives (пример: env_auditor дал 35/35 ложных).
- После любых изменений фабрики обновляй README.md, agents/README.md,
  инсталлятор — Заказчик просит это каждый раз, не жди просьбы.

## 6. Открытое состояние на момент передачи (2026-10-14)

- PO-рефакторинг волна 2 (deleg_bdd7a28e) — в работе: остаток
  settings_categories + navigation_search, полный прогон; после green —
  экспресс-мерж волны 2.
- Бэклог: J41-чекбокс (архивация 2 пакетов), J42, J43-хвосты
  (strict/allowlist/sequence), J48 (инцидент-протокол Флоу 3: severity S1–S3,
  post-mortem), J49 (наблюдаемость: 4 золотых сигнала netdata), #68/#69
  фабрики.
- На решение Заказчика: привязка bypass-решения к версии артефакта + механизм
  отзыва (known limitation, plugins/README.md).
- Wiki-пауза Заказчика: cookie-state дерева (сутки, фронт-only, дефолт
  свернуто) + баг «Создать страницу» подставляет текущую страницу родителем —
  НЕ реализовывать без его команды.

## 7. Где лежит память predecessor

- `~/.hermes/` — профильные memories/skills текущей машины; этот файл —
  страховка на случай новой машины/профиля. Если memories доступны — читай
  их первыми, этот документ — дистиллят.
- История сессий: session_search по session_id (см. реестр active_sessions).
