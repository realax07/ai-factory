# CI gates: где исполняется и что реально обязательно

Дополнение к `docs/README-flow-control.md`. Назначение (P0.5 по пересмотренному
плану): показать, какие проверки **реально обязательны в GitHub**, а какие —
только **договоренность команды** или **машинная проверка на нашей машине**
(enforcing внутри штатного маршрута `flowctl`, но невидимая для GitHub).

Граница гарантии: `enforcing`-проверки блокируют неверные действия только
внутри штатного маршрута `flowctl`. Общая ОС-учетка и общий токен не исключают
обход через GitHub или локальные файлы — поэтому только проверки из колонки
«GitHub-enforced» навязываются платформой, остальные держатся на дисциплине.

| Проверка | Где исполняется | Обязательность | Статус |
|---|---|---|---|
| `openspec validate --all --strict` | GitHub Actions (job `flow`, `.github/workflows/flow.yml`) | Обязательна | **GitHub-enforced** (job `flow` на PR и push в main) |
| `flow_check` (`scripts/flow_check.py .`) | GitHub Actions (job `flow`) | Обязательна | **GitHub-enforced** (job `flow` на PR и push в main; известен красный статус на main — гигиена P0.6, самоссылочные ошибки пакета add-deterministic-flow) |
| `pytest tests/` (полный набор, 405+ тестов, вкл. негативные сценарии P0.2–P0.4) | GitHub Actions (job `test-flow-control`, `.github/workflows/flow.yml`) | Обязательна для merge после включения Заказчиком в required checks ruleset | **GitHub-enforced** (после включения; до того — CI-сигнал без блокировки merge) |
| Branch protection ruleset на `main` (required checks, ветка + PR) | GitHub (ruleset репозитория) | Обязательна; bypass не предусмотрен и не должен выдаваться | **GitHub-enforced** |
| `session_check` zone-check (резервация зоны, diff ⊆ зона, OUT_OF_ZONE) | Машина (`scripts/session_check.py` на маршруте `flowctl finish`) | Обязательна на штатном маршруте `flowctl` | **машинная (enforcing)** — GitHub не видит и не блокирует обход вне маршрута |
| `gate_runner` (openspec/flow_check/pm_bounds/pr_validate с digest и STALE, SKIPPED ≠ PASS) | Машина (`scripts/gate_runner.py` на `flowctl finish`) | Обязательна на штатном маршруте; FAIL/ERROR/SKIPPED не дают `accepted` | **машинная (enforcing)** |
| Provenance (SHA, diff_digest, автор/ревьюер, независимость роли) | Машина (`scripts/gate_runner.py` record-review/check) | Обязательна на штатном маршруте; STALE_EVIDENCE / WRONG_ROLE блокируют | **машинная (enforcing)** |
| Review независимой ролью (approve-вердикты задач в `code-reviews/<change-id>/`) | Машина + GitHub (файлы в PR) | Договоренность + machine-факт: проверяется `gate_runner` при приемке, но содержательное качество ревью — не платформа | **договоренность** (с машинной проверкой формы) |
| Решение заказчика (`approval_ref` на конкретную запись решения) | Журнал в репозитории (`releases/<id>.md`) | Договоренность: файл в репо под общим пользователем не является независимым одобрением; фиксирует решение, но не подтверждает личность | **договоренность** |
| Самоотчет агента (статусы в отчете сабагента) | Чат / отчет агента | Не является проверкой; только сигнал для диспетчера | **НЕ проверка** |

## Итог

- Реально обязательны в GitHub: `openspec validate`, `flow_check`, (после
  включения в ruleset) `pytest tests/`, и сам branch protection ruleset.
- Обязательны, но только на машине: zone-check, gate_runner, provenance —
  гарантируют корректность штатного маршрута, но не защищены от обхода
  напрямую через GitHub или файловую систему (общая учетка, общий токен).
- Только договоренность: содержательное ревью независимой ролью и статус
  решения заказчика; самоотчет агента проверкой не является.

## Что проверяется когда (J37-5, 2026-10-09)

Две стадии — два набора ворот (норма поэтапного Флоу 1, не дефект):

- **Промежуточные PR** (поэтапный dev/qa, [chore]/[docs]/[ops]): job `flow` —
  openspec validate + flow_check (порядок артефактов, трассировка, зоны) +
  pytest tests/ (required). pr_validate здесь не выполняет QA-хвост: полный
  набор (impact/чеклист/approved/reviews) к промежуточной стадии не существует
  по дизайну — краснота на этом шаге означает срыв этапности (см. P14: ожидаемая
  процессная краснота до финального PR).
- **Финальный change-маркерный PR**: + pr_validate полный набор — impact (H5),
  чеклист (контракт 4), approved-кейсы (контракт 6), review-файлы с
  Reviewer-Delegation и вердиктами approve (J10, SELF_REVIEW-защита).

Правило: change-маркер ставится ТОЛЬКО на финальный PR пакета; промежуточные —
[chore]/[docs]/[ops].
