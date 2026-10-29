# Change: Детерминированный Flow Control (срез 1, поставки 01–03)

## Why

Правила конвейера (Флоу 1–5, этапные ворота Заказчика, роли, зоны записи) существуют
текстом в AGENTS.md/контрактах; исполняемый слой (`flow_check.py`) проверяет
артефакты постфактум, но не отвечает на вопрос «какое действие разрешено сейчас и
почему нет». Переходы и распределение задач остаются решениями ПМ (бэклог J28,
дыры J14: часть гарантий «на честном слове»).

Источник требований: `docs/chatgpt-deterministic-flow/` (ТЗ ChatGPT, поставки 01–03).

## What Changes

- Новая спека `deterministic-flow`: Flow State (снимок фактов), Transition Validator
  (разрешение действий ALLOW/DENY/UNKNOWN со стабильными кодами причин), human gate
  (этапные ворота Заказчика), восстановление после сбоев.
- `scripts/flow_state.py` — read-only снимок состояния по scope
  (repo+project+flow+change+task): факты из requirements/openspec/tasks/reviews/
  test-model/Git/реестра сессий, snapshot_digest.
- `scripts/flow_transition.py` — чистая функция `check_action(snapshot, action) -> Decision`
  + CLI `check`/`next` (exit 0/1/2). Правила Флоу 1–5, параллельность по `[P]`,
  независимый ревьюер, provenance-заглушка → UNKNOWN до поставки 05.
- Режим: **shadow** — ничего не блокирует; результаты сверяются с решениями ПМ.

## Impact

- Affected specs: новая `deterministic-flow` (не трогает pipeline/artifacts/qa-pipeline).
- Affected code: +`scripts/flow_state.py`, +`scripts/flow_transition.py` (новые файлы,
  stdlib); `flow_check.py`/`pm_bounds_check.py` не изменяются.
- Риски: минимальные — read-only, без enforcement, без запуска агентов.
