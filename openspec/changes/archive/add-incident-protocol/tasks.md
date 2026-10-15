# tasks.md — add-incident-protocol

Нарезка этапа 4 плана PLAN-J48 (dev) + QA/ревью/архивация. Зеркалирование в
ekotov-wiki — этап ПМ 7 ПОСЛЕ merge, задачей сюда НЕ входит.

## 1. Dev: severity в маркере (FR-4, D1)

- [ ] 1.1 [S] `scripts/flow_transition.py`: разбор severity-префикса `^S[123]-` в incident_ref (ctx-доставка последующим check-функциям) — ВЫПОЛНЕНО (закрытие после code review 4.1, J10)
- [ ] 1.2 [S] `check_emergency_stabilize`: incident_ref без префикса S1-/S2-/S3- → Finding MISSING_INPUT «инцидент неклассифицирован» (к неклассифицированному archival-семантика FR-3 не разрешает архивацию) — ВЫПОЛНЕНО
- [ ] 1.3 [S] `plugins/flow-enforcer/enforcer.py`: тест-фиксация, что scope=incident-id проходит в `--incident-ref` с severity-префиксом без искажений (маркер не переписывает код инцидента) — ВЫПОЛНЕНО
- [ ] 1.4 [M] Тесты: маркер `S1-prod-down` → severity S1 извлечен; `S2-…`; без префикса → MISSING_INPUT; Флоу 1/2/4/5 — поведение check-функций не изменилось — ВЫПОЛНЕНО (tests/test_j48_incident_protocol.py)

## 2. Dev: этапы и ворота архивации Флоу 3 (FR-1…FR-3, D2/D3)

- [ ] 2.1 [S] `STAGE_TABLE[3]`: этап `post_mortem` (роли dev/devops, check_post_mortem: файл в `test-model/incidents/` с секциями Таймлайн/Root cause/Action items) + этап `archive_change` (роли sa/dev_lead/integrator, check_archive_flow3) — ВЫПОЛНЕНО
- [ ] 2.2 [M] `check_archive_flow3` (ворота D2): Флоу 3 + incident_ref S1/S2 без post-mortem-файла → DENY (ненулевой exit); с post-mortem → ALLOW по воротам; неклассифицированный incident_ref → DENY MISSING_INPUT. Требование арх. I-2: severity перепарсивается из action.incident_ref в момент ворот (CLI-вызов архивации — отдельный процесс, ctx между вызовами не переносится) — ВЫПОЛНЕНО
- [ ] 2.3 [S] Хранилище: каркас `test-model/incidents/` (конвенция append-only в контракте каталога; именование `<YYYY-MM-DD>-<incident_ref>.md`) — ВЫПОЛНЕНО
- [ ] 2.4 [M] Тесты: архивация S1 без post-mortem блокируется; S2 с post-mortem (таймлайн/root cause/action items) проходит; append-only — существующие файлы тест-фиксацией не перезаписываются; неклассифицированный маркер архивацию не разрешает — ВЫПОЛНЕНО
- [ ] 2.5 [S] Регресс NFR-3: `pytest tests/` green; `flow_check.py` не изменялся (diff-пусто), его вывод на Флоу 1/2/4/5 не изменился — ВЫПОЛНЕНО (651 green)
- [ ] 2.6 [S] Обновить схему Флоу 3 в docs/README-flow-control.md §52-61 (M-3 ревью review-001) — ВЫПОЛНЕНО (одна схема)

> Примечание dev (2026-10-15): задачи 1.1–1.4/2.1–2.6 реализованы; чекбоксы не
> закрыты — J10 (flow_check) требует code-review файлов для закрытых dev-задач,
> независимое ревью — этап 4.1. Закрыть 1.x/2.x после ревью кода.

## 3. QA

- [ ] 3.1 [M] Тест-кейсы ← сценариев спеки `incident-protocol` (10), трассировка FR-1…FR-4 — `test-model/new` → approved
- [ ] 3.2 [M] Автоматизация кейсов ворот D2 (S1 без PM → DENY; S2 с PM → ALLOW; append-only) — тесты

## 4. Ревью и завершение

- [ ] 4.1 [S] Code review (независимый ревьюер): flow_transition + enforcer маркер
- [ ] 4.2 [S] QA review кейсов и автоматизации
- [ ] 4.3 [S] Финал: `openspec validate add-incident-protocol --strict` EXIT=0; полный регресс green; merge (dev_lead/ПМ)
- [ ] 4.4 [S] Архивация пакета (решение Заказчика) — дельты `incident-protocol` слить в `openspec/specs/`

## Порядок

1.1 → 1.2 → 1.3 → 1.4 ∥ 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 3.1 → 3.2 → 4.1 → 4.2 → 4.3 → 4.4.
Ворота: openspec validate --strict green на каждом шаге; NFR-3 регресс green после 2.x.
