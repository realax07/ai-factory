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
| `flow_check` (`scripts/flow_check.py .`) | GitHub Actions (job `flow`) | Обязательна | **GitHub-enforced** (job `flow` на PR и push в main; main зелен — самоссылочные ошибки пакета add-deterministic-flow вычищены, гигиена P0.6 закрыта) |
| `pytest tests/` (полный набор, 1400+ тестов на 2026-11-14, вкл. негативные сценарии P0.2–P0.4 и эталонный прогон Флоу 1 без QA-контура через раннер, J65.10) | GitHub Actions (job `test-flow-control`, `.github/workflows/flow.yml`) | Обязательна для merge: required check ruleset | **GitHub-enforced** (проверка ruleset — `scripts/ruleset_check.py`) |
| Branch protection ruleset на `main` (required checks, ветка + PR) | GitHub (ruleset репозитория) | Обязательна; bypass не предусмотрен и не должен выдаваться | **GitHub-enforced** |
| `session_check` zone-check (резервация зоны, diff ⊆ зона, OUT_OF_ZONE) | Машина (`scripts/session_check.py` на маршруте `flowctl finish`) | Обязательна на штатном маршруте `flowctl` | **машинная (enforcing)** — GitHub не видит и не блокирует обход вне маршрута |
| `gate_runner` (openspec/flow_check/pm_bounds/pr_validate с digest и STALE, SKIPPED ≠ PASS) | Машина (`scripts/gate_runner.py` на `flowctl finish`) | Обязательна на штатном маршруте; FAIL/ERROR/SKIPPED не дают `accepted` | **машинная (enforcing)** |
| Provenance (SHA, diff_digest, автор/ревьюер, независимость роли) | Машина (`scripts/gate_runner.py` record-review/check) | Обязательна на штатном маршруте; STALE_EVIDENCE / WRONG_ROLE блокируют | **машинная (enforcing)** |
| Review независимой ролью (approve-вердикты задач в `code-reviews/<change-id>/`) | Машина + GitHub (файлы в PR) | Договоренность + machine-факт: проверяется `gate_runner` при приемке, но содержательное качество ревью — не платформа | **договоренность** (с машинной проверкой формы) |
| Решение заказчика (`approval_ref` на конкретную запись решения) | Журнал в репозитории (`releases/<id>.md`) | Договоренность: файл в репо под общим пользователем не является независимым одобрением; фиксирует решение, но не подтверждает личность | **договоренность** |
| Ворота агентной стадии `<исполнитель>:<роль>` (prepare/run/finish, сверка git diff с зоной, коммит стадии) | Машина (`scripts/package_runner.py`, J63, J65.5) | Обязательна для пакетов, идущих через раннер | **машинная (enforcing)** — GitHub не видит; ручной запуск исполнителя мимо раннера — BYPASS вотчдога (`executor_watchdog`), не блок |
| Ворота CI проекта по закрепленной версии фабрики | GitHub Actions проекта: checkout фабрики на SHA из `factory.lock` в `.factory/` (J65.7) | Для проектов с `factory.lock` | **GitHub-enforced** в проекте (если `flow` — required check проекта) |
| Самоотчет агента (статусы в отчете сабагента) | Чат / отчет агента | Не является проверкой; только сигнал для диспетчера | **НЕ проверка** |

## Итог

- Реально обязательны в GitHub: `openspec validate`, `flow_check`,
  `pytest tests/` (required checks `flow` и `test-flow-control`), и сам
  branch protection ruleset.
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
  approved-кейсы (контракт 6), review-файлы с
  Reviewer-Delegation и вердиктами approve (J10, SELF_REVIEW-защита).
  (remove-qa-checklist: чеклист (бывший контракт 4) больше не требуется.)

Правило стадий маркеров (документированное, волна 4 Н27; машина различает
стадии по маркеру в title/body PR):

- **Промежуточные** — `[chore]` / `[docs]` / `[ops]`: работа по ходу пакета
  (обслуживание, документация, эксплуатация) и этапы Флоу 1 до финала;
  полный QA-хвост к ним не существует по дизайну, pr_validate проверяет
  маркер + механические правила J58.
- **Финальные** — `[change-id]` / `[BUG-NNN]`: change-маркер ставится
  ТОЛЬКО на финальный PR пакета (полный набор: impact, approved-кейсы,
  review-файлы); `[BUG-NNN]` — завершенный багфикс.
- Красный промежуточный PR = срыв этапности (P14), красный main = дефект
  конвейера (сейчас main зелен).

## Воспроизведение CI локально (J65.12)

`python3 scripts/ci_local.py` гоняет `pytest tests/` и `flow_check` в условиях
CI: клон глубины 1 закоммиченного HEAD, пустой HOME, без `GITHUB_*`/`GIT_*`.
Ловит класс «локально зеленое, в CI красное» (полная история git, реальный
HOME) до push. `openspec validate` не входит.
