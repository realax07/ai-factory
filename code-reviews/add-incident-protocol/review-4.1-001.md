# Review-001 — task 4.1 (code review дифа J48)

- **Задача tasks.md:** 4.1 (независимое code review: flow_transition + enforcer маркер)
- **Ревьюируемая поставка:** ветка `pipeline/j48-incident-protocol`, диф `main...pipeline/j48-incident-protocol` (9 коммитов 2bb3266…80ba1d5)
- **Спека:** openspec/changes/add-incident-protocol/ (requirements FR-1…FR-4/NFR-1…3, design D1–D4, review-001-architecture)
- **Reviewer-Delegation: deleg_<id> — идентификатор платформенной делегации проставляет оркестратор при приемке (self-review защита flow_check J10)**
- **Метод:** три круга по skills/code-review (спека → best practices → integration); adversarial-ось — обратная совместимость Флоу 3-маркера (по постановке 4.1)

## Вердикт: approve

Задача может вливаться. Semantics ворот D2/I-2 реализованы корректно, breaking-изменение маркера — осознанное и задокументированное, изоляция Флоу 1/2/4/5 подтверждена тестами и полным регрессом (651 passed). Замечания ниже — major×1 + minor×4, ни одного blocker; major не нарушает спеку (ворота живут в flow_transition, как решено D2) и чинится [S]-правкой enforcer.

## Замечания

| # | Файл:строка | Серьезность | Замечание | Рекомендация |
|---|---|---|---|---|
| 1 | plugins/flow-enforcer/enforcer.py:193 (`ROLE_ACTIONS_FLOW[3]`) | **major** | Новые этапы D3 (`post_mortem`, `archive_change`) не выражаемы через enforcer-маркер: `action_for_role()` выводит действие только из role+flow; для Флоу 3 `dev/devops`→`emergency_stabilize` всегда, `sa`→фолбэк `create_change` (этап Флоу 1!) из ROLE_ACTIONS. SEQUENCE_PREREQS[3] при этом уже знает post_mortem/archive_change — таблица знает действия, которые маппинг не может породить (внутренняя рассинхронизация). Пока sequence-gate OFF и/или этапы проводятся flowctl напрямую — спит; при `FLOW_ENFORCER_SEQUENCE=1` или будущей валидации action — реальный разрыв интеграции (делегация sa на архивацию Флоу 3 уйдет в prepare с action=create_change). | Добавить в `ROLE_ACTIONS_FLOW[3]` маппинги `devops/dev`→`post_mortem` невозможно одним ключом (роль→одно действие) — значит: либо явный маркер `action=`, либо отдельные роли этапов. Минимальный [S]-вариант: расширить ROLE_ACTIONS_FLOW[3] до полной карты ролей этапов Флоу 3 (dev/devops → по контексту задачи) или задокументировать в plugins/README + D3, что этапы post_mortem/archive_change проводятся ТОЛЬКО flowctl-CLI вне enforcer-маркеров, и убрать их из SEQUENCE_PREREQS-ожиданий маркера. |
| 2 | openspec/changes/.../design.md (D1) + enforcer.py:435 | minor | Ломающее изменение ОСОЗНАННОЕ, но трассировка неполная: design D1 описывает только уровень flow_transition («нет префикса → Finding MISSING_INPUT»); enforcer-уровень (bare incident_ref → FlowMarkerError/FLOW_MARKER_INVALID ДО старта реакции) в design не записан — он меняет семантику отказа (код FLOW_MARKER_INVALID вместо MISSING_INPUT из сценария FR-4 «WHEN flow_transition разбирает маркер»). Итог для потребителя тот же (проход запрещен), defense-in-depth в flow_transition сохранен. | Одна строка в D1: «enforcer дополнительно отсекает bare-маркер на входе (FLOW_MARKER_INVALID); сценарий FR-4 покрывается обоими слоями». Миграционная запись: риск ≈ 0 (в логах enforcer живых Флоу 3-делегаций с bare incident_ref нет; единственный прецедент J25 — вне маркеров, ОВ-1/Won't фиксируют «старые маркеры не переписываются»), но добавить в proposal/tasks фразу «существующие bare-маркеры Флоу 3 после J48 невалидны — осознанное следствие FR-4». |
| 3 | flow_transition.py `_post_mortem_findings` (корреляция `ref in p.name`) | minor | Корреляция по «сырой» подстроке: ref `S1-prod` удовлетворяется файлом другого инцидента `2026-10-15-S1-prod-down.md` — архивация без собственного post-mortem проходит. Детерминизм NFR-1 не нарушен, но матч свободнее контракта именования D4. | Матчить по границам: `re.search(rf"(?:^|-){re.escape(ref)}(?:\.|$)", p.name)` — или требовать точный суффикс `-{ref}.md`. |
| 4 | flow_transition.py `_post_mortem_findings` (секции) | minor | Секции проверяются как подстрока `.lower()` по всему тексту, а не по заголовкам `##` — design D4 («проверка по заголовкам») и README хранилища обещают заголовки; файл, где «root cause» упомянут в прозе, проходит без реальной секции. | Искать по строкам: `any(re.match(rf"^#+\s*{s}", line) for line in text.splitlines())` — либо поправить формулировку D4 на «по вхождению». |
| 5 | flow_transition.py `check_emergency_stabilize` | minor | `severity` вычисляется до проверки `if not action.incident_ref` — для пустого ref оба Finding сливаются корректно, но elif-ветка зависит от порядка; читаемость: вычисление используется в двух ветках — ок, просто зафиксировать инвариант комментарием (пустой ref → MISSING_INPUT «причина не зафиксирована», без «неклассифицирован»). Тест TC-J48-008 покрывает None — поведение верное. | Опционально; можно не чинить. |

## Проверенные Scenario

- **FR-1/S1-S2-S3**: классификация реагированием — откат/PR/перевод в Ф2 — протокольно зафиксированы воротами (S3: протокол не применяется, TC-J48-007); матрица как процесс — вне кода (промпты — Won't-граница, честно: не проверяемо в этом дифе).
- **FR-3**: S1/S2 без post-mortem → DENY MISSING_INPUT (TC-J48-005); S2 с полным post-mortem → ALLOW (TC-J48-006); секции неполные → INVALID_GATE на этапе и в воротах (TC-J48-009); append-only — ворота не пишут в хранилище (TC-J48-017); S3 → без пост-мортема проходит (TC-J48-007).
- **FR-4**: S1-/S2-/S3- извлечены; S4-/s1-/S1-без-суффикса → None/отказ (TC-J48-001, TC-J48-013); bare incident_ref → DENY в flow_transition (TC-J48-003/008) и FLOW_MARKER_INVALID в enforcer (TC-J48-013); `--incident-ref` без искажений (TC-J48-015).
- **арх. I-1**: allowlist единый — enforcer импортирует `flow_transition.SEVERITY_PREFIXES`, fallback синхронизирован тестом (TC-J48-014).
- **арх. I-2**: ворота перепарсивают severity из `action.incident_ref` сами; poisoned-ctx тест (TC-J48-011) — чужой ctx-`incident_severity` не влияет на вердикт.
- **NFR-3 (изоляция)**: STAGE_TABLE[3]-дополнения только под ключом 3; состав действий Флоу 1/2/4/5 закреплен тестом (TC-J48-018); check-функции на 1/2/4/5 → [] (TC-J48-019); SEQUENCE_PREREQS[3] согласован с STAGE_TABLE[3] (TC-J48-016); `git diff main... -- scripts/flow_check.py` пуст; `pytest tests/` — **651 passed**.

## Что НЕ проверено (честно)

- Живой прогон `flowctl prepare` Флоу 3 с новым этапом (замечание #1 — статический анализ enforcer, не live-проба).
- Файл с несколькими post-mortem одного ref (поведение `matches[-1]` — по коду: лексикографически последний, для append-only коррекций приемлемо).
- Промпты devops/dev и wiki-зеркало — вне среза (этапы ПМ 7 / Won't).
- Ретроактивность J25 — открытое ОВ-1, не в этом дифе.
