# PLAN-J46 — архитектор: актор ревью, вердикт-ворота, карта как обязательный артефакт

**Флоу: 2** (исполняемый контур). Решения Заказчика 2026-10-12: «Давай. Но ты
еще забыл про map. Она же основной была» — J44 (свежесть карты) вливается в
J46: карта — не «вспомнить при архивации», а проверяемый артефакт ревью.

## Проблемы

1. `architecture_review` в STAGE_TABLE — актор **pm**, не architect (легаси);
   реальных вызовов архитектора — 1 за историю (add-containerization).
2. **P15 не имел архитектурного ревью вообще** (новый домен, 2 таблицы,
   санитайзер) — ворота не требуют вердикт.
3. `architecture/map.md` — нигде не проверяется (ни существование, ни
   свежесть); замерла на 2026-10-05, 387 коммитов позади. ADR — ноль.
4. Энфорсер J43 не знает роль architect (ROLE_ACTIONS пусто для нее).

## Изменения

### Фабрика

1. **flow_transition.py**: STAGE_TABLE Флоу 1 — актор architecture_review →
   `("architect",)`; `check_dev_task` — для пакетов с продуктовыми дельтами
   (backend/services/frontend/design) требует
   `test-model/reviews/<change>/review-NNN-architecture.md` с вердиктом
   (в духе code_review: отсутствие/без вердикта = DENY,
   ARCH_REVIEW_MISSING).
2. **flow_check.py**: (а) `architecture/map.md` обязан существовать в проекте
   (отсутствие = FLOW-ERROR, карта — основной артефакт роли); (б) при
   архивации пакета с продуктовыми дельтами: в его architecture-review-файле
   должна быть строка-вердикт по карте — `Карта: обновлена` (и тогда
   architecture/** менялся в пакете) ИЛИ `Карта: без изменений` (с
   обоснованием); отсутствие строки = нарушение (контракт 7-дополнение, J46).
3. **plugins/flow-enforcer/enforcer.py**: ROLE_ACTIONS + SEQUENCE_PREREQS —
   `architect` → `architecture_review` (после create_change, перед dev_task).
4. **role_zone_policy.py**: проверить политику architect (уже есть — не менять
   без нужды).
5. **Тесты**: вердикт-ворота dev_task; map.md отсутствует/есть; строка
   «Карта:» в ревью; энфорсер role=architect; регресс 534+.

### Промпты (ПМ, отдельно)

- architect_agent.md: J43-маркер, чек-лист сверки карты при ревью пакета,
  строка «Карта: …» обязательна в review-файле.
- agents/README.md, skills/README (service-decomposition уже у СА).

### Проект ekotov-wiki (тонкий клиент)

- Синхронизация flow_check/flow_transition/role_zone_policy/enforcer +
  agents/architect (промпт ПМ). Разовая синхронизация карты —
  первая живая делегация архитектора после влития (J44-исполнение).

## Критерий закрытия

- dev_task продуктового пакета без architecture-вердикта = DENY.
- Архивация без строки «Карта: …» в ревью = FLOW-ERROR.
- role=architect проходит энфорсер; 534+ passed; flow_check OK оба репо.
