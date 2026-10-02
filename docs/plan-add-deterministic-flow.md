# План change-пакета add-deterministic-flow (срез 1, поставки 01–03)

> Флоу: 4 (обслуживание фабрики). Ветка: `deterministic-flow` (от main 8048c0e).
> Ветка основная на время работ; в main не вливать до явного решения Заказчика.
> Источник ТЗ: docs/chatgpt-deterministic-flow/ (00–03). Бэклог: J28.
> Заказчик: старт 2026-10-02 («Погнали, но в ветке отдельной»).

## Состав среза 1

1. **Поставка 01** — спека OpenSpec `deterministic-flow` (Flow State, Transition
   Validator, human gate, восстановление) + контракт интерфейсов:
   `inspect(repo, scope) -> FlowSnapshot`; `check_action(snapshot, action) -> Decision`;
   коды причин (MISSING_INPUT, INVALID_GATE, HUMAN_APPROVAL_REQUIRED, WRONG_ROLE,
   ZONE_CONFLICT, STALE_EVIDENCE, AMBIGUOUS_STATE, STALE_SNAPSHOT,
   EXTERNAL_ENFORCEMENT_UNKNOWN). Матрица «действие → роль → входы → evidence →
   gates → результат».
2. **Поставка 02** — `scripts/flow_state.py`: read-only снимок фактов
   (requirements.md, openspec/, tasks.md, code-reviews/, test-model/, Git,
   active_sessions.json), модель факта (key/value/source/observed_at/fingerprint/
   confidence), snapshot_digest, CLI `inspect --json`. Без записей, чистый.
3. **Поставка 03** — `scripts/flow_transition.py`: чистая `check_action(snapshot,
   action) -> Decision`, CLI `check`/`next` (exit 0 ALLOW / 1 DENY / 2 UNKNOWN),
   правила Флоу 1–5, этапные ворота AGENTS.md → HUMAN_APPROVAL_REQUIRED.
   Shadow mode: ничего не блокирует, решения против решений ПМ.

## Порядок работ

- [ ] 0. План (этот файл) + каркас change-пакета openspec (`proposal.md`,
      `specs/deterministic-flow/spec.md`) — ПМ.
- [ ] 1. Поставка 01: спека + контракт (СА-сабагент) → ревью.
- [ ] 2. Поставка 02: flow_state.py + тесты (dev-сабагент) → ревью → прогон на
      ekotov-wiki (shadow, сверка с фактом).
- [ ] 3. Поставка 03: flow_transition.py + табличные тесты всех флоу (dev) →
      ревью → shadow-прогон на истории Р6.
- [ ] 4. Доклад Заказчику: результаты shadow, расхождения машина/ПМ, решение о
      срезе 2 (поставка 04).

## Ворота

- openspec validate --all --strict green на каждом шаге.
- flow_check.py и pm_bounds_check.py не меняются (только совместимость).
- CI flow.yml зеленый на ветке.
- Никакого enforcement: срез 1 = inspect/check/next, read-only.

## Критерии приемки (по ТЗ 00/03)

- CLI показывает состояние и допустимые следующие действия на тестовом репо и на
  ekotov-wiki.
- Отвергает обход порядка, чужую роль, неизвестный Flow — кодами причин.
- Дважды вызванный inspect на неизменном вводе — эквивалентный JSON.
- Негативные тесты: пропущенный этап, неподходящая роль, нет решения Заказчика,
  устаревшее evidence, битый реестр.
