# PLAN-readme-refresh: актуализация всех README репозитория

**Флоу: 4** — обслуживание: документация и генератор документации, поведение
ворот не меняется.

## Задача

Заказчик (2026-11-07): «обнови все README которые есть в репозитории».
Сверка всех README (кроме `archive/`, `code-reviews/`, исторического ТЗ
`docs/chatgpt-deterministic-flow/`) с фактом после J65.1 (реестр ролей),
J65.4 (вердикт ревью) и J66 (тестовые зоны).

## Что сделано

- `README.md`: роли dev/qa_automation по раскладке тестов, этап
  `[qa_automation]` во Флоу 2–5, factory_init (smoke в `tests/unit/`,
  режим раскладки), раздел «Раскладка тестов» в «Как связаны части».
- `docs/README-flow-control.md`: раздел «Раскладка автотестов (J66)»,
  реестр скриптов (flow_check, gen_role_docs, factory_init), путь
  `tests/unit/test_gate_harness.py`.
- README роль-паков: блок «Зона записи» и пример `PI_ZONE_WRITE` теперь
  генерирует `gen_role_docs.py` из `agents/roles.json` (было руками и
  расходилось с политикой: code-reviewer писал в `test-model/reviews`
  вместо `code-reviews/`, devops — `docs/ops` вместо `ops/` и
  `.github/workflows`, architect — лишний `docs/`, regress-runner — без
  блока); проза рядом приведена к политике. Закрывает остаток J64.11 по
  README паков (debug/auditor — без политики, развилка J64.11 остается).
- `skills/pm-factory/pi/role-packs/README.md`, `skills/README.md`
  (без чеклистов J23, автотесты по раскладке J66).
- Тест TC-J65-PZ-001…003.

## Вне объема

- Промпты паков `role-agents.md` (code-reviewer — `test-model/reviews`,
  architect — `docs/**`, devops — `docs/ops`) расходятся с политикой так
  же — это промпты, не README; правка — отдельно по согласию Заказчика.
- `agents/README.md`, `plugins/README.md`, `tests/README.md`,
  `agents/archive/README.md` — сверены, актуальны.

## Возврат ревью review-001 (1 major, 10 minor) — исправлено

Пример запуска code-reviewer писал review вне зоны (`test-model/reviews`) —
теперь `code-reviews/C123/…`; брифы с вердиктом-заголовком вместо «маркера»;
оговорка о масках внутри пути (префикс guard'а шире, точная граница —
session_check); sa — подстановка `<id>` только в зоны политики; TC-ID — везде,
кроме `tests/unit/`; генератор — однократный импорт раннера, ошибка с именем
файла при отсутствии маркеров/README, плейсхолдер = `role_zone_policy.CHANGE_ID`;
тесты против `policy_zones` раннера, двойные кавычки, отсутствие маркеров;
остаток J64.11 (промпты паков) — в бэклоге J64.

## Критерий закрытия

Полный сьют зеленый, `gen_role_docs --check` OK, flow_check OK, ревью
approve, CI зеленый.
