# tests/ — индекс и трассировка

Автотесты фабрики. Базлайн: `python3 -m pytest tests/ -q` — все green.

## J48 — инцидент-протокол Флоу 3 (change add-incident-protocol)

Файл: `tests/test_j48_incident_protocol.py` (TC-J48-001…032).
Approved-кейсы: `test-model/approved/add-incident-protocol/`
(TC-SEV-001…004, TC-IRS-001…004, TC-PMG-001…007, TC-DEC-001…004 — 19 кейсов).

Матрица соответствия (этап qa_automation Флоу 1, прогон фактический — все
строки PASS на ветке `pipeline/j48-incident-protocol`):

| Approved TC | Автотест(ы) | Проверка / статус |
|---|---|---|
| TC-SEV-001 | **TC-J48-023** (+ TC-J48-001) | S1: rollback — первая устраняющая запись таймлайна, ts(rollback) < начала Root cause; deploy_rollback в STAGE_TABLE[3]; ворота принимают полный post-mortem. PASS |
| TC-SEV-002 | **TC-J48-024** (+ TC-J48-001) | S2: severity разобран, машина требует PR-цикл (review + pr_validate); первая устраняющая запись — «создан PR», rollback-записей нет; ворота проходят. PASS |
| TC-SEV-003 | TC-J48-007 (+ TC-J48-019) | S3: протокол не применяется — архивация без post-mortem проходит (этап и ворота). PASS |
| TC-SEV-004 | **TC-J48-025** (+ TC-J48-001, TC-J48-013/014) | S4 вне allowlist: трактуется неклассифицированным — DENY MISSING_INPUT «неклассифицирован»; в enforcer маркер S4 → FLOW_MARKER_INVALID. PASS |
| TC-IRS-001 | **TC-J48-026** | Порядок (1)→(2)→(3): 3 timestamps монотонны, last − start ≤ 15 мин, Root cause после стабилизации; ворота принимают артефакт. PASS |
| TC-IRS-002 | **TC-J48-027** | Ровно T+15:00 — порог включительный, превышения нет; ворота проходят. PASS |
| TC-IRS-003 | **TC-J48-028** | 16 мин > 15 мин — превышение выявляемо из артефакта парсингом timestamps. PASS |
| TC-IRS-004 | **TC-J48-029** | ts(Root cause) < ts(стабилизации) — нарушение порядка выявляемо из таймлайна. PASS |
| TC-PMG-001 | TC-J48-005 | S1 без post-mortem — DENY MISSING_INPUT, check_action DENY. PASS |
| TC-PMG-002 | TC-J48-006 | S2 с полным post-mortem — ворот нет, ALLOW. PASS |
| TC-PMG-003 | TC-J48-007 | S3 × файл отсутствует — ворота не применяются. PASS |
| TC-PMG-004 | TC-J48-008 (+ TC-J48-003) | Без префикса — DENY MISSING_INPUT (неклассифицированный архивацию не разрешает). PASS |
| TC-PMG-005 | **TC-J48-030** (+ TC-J48-009, TC-J48-022) | Не все 3 секции (только «## Root cause») — INVALID_GATE с перечнем недостающих («таймлайн, action items»), DENY. PASS |
| TC-PMG-006 | TC-J48-021 | Чужой post-mortem по границам имени не засчитывается — MISSING_INPUT. PASS |
| TC-PMG-007 | TC-J48-017 | Append-only: содержимое существующих файлов байт-в-байт, новых файлов проверки не создают (шаги кейса с `git status` — ручная часть инварианта). PASS |
| TC-DEC-001 | TC-J48-002 + TC-J48-005 | Маркер S1 распознан (ctx incident_severity=S1), затем archive_change → MISSING_INPUT DENY. PASS |
| TC-DEC-002 | TC-J48-003 + TC-J48-008 | Маркер без префикса: emergency_stabilize и archive_change — оба MISSING_INPUT «неклассифицирован». PASS |
| TC-DEC-003 | **TC-J48-031** (+ TC-J48-001, TC-J48-013) | Границы формата (s1-, S1prod-, hotfix-S1-): severity None, emergency_stabilize DENY MISSING_INPUT для каждого. PASS |
| TC-DEC-004 | **TC-J48-032** | Машинная часть: ворота детерминированы маркером (S3-маркер — находок нет, UNKNOWN нет; NFR-1); процессная часть (фиксация расхождения FR-4 в action items) — ревью, вне API. PASS |

Жирным — автотесты, добавленные этапом qa_automation (TC-J48-023…032,
докручены к существующим TC-J48-001…022 без дублирования). Замечание по
TC-IRS-001…004: 15-минутное окно и порядок реакции — процессные требования
без отдельных машинных ворот; проверяемость обеспечена парсингом таймлайна
(данные кейса → артефакт → проверка свойства), машинная часть (полнота
секций) — ворота `check_archive_flow3`.
