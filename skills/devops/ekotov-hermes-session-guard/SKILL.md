---
name: ekotov-hermes-session-guard
potential: always
description: "Use when Telegram DM delegation drops results."
tags: [hermes, sessions, delegation, telegram, watchdog]
metadata:
  hermes:
    tags: [hermes, sessions, delegation, telegram]
---

# Telegram DM session guard (ekotov Hermes)

## Известный баг (апстрим #92859)

delegate_task-батч, отправленный из Telegram-DM **ровно на границе ротации сессии**
(в ту же секунду, когда создается новый session id на ключе
`agent:main:telegram:dm:144324141`), не создает изолированную subagent-сессию:
текст ТЗ становится первым user-сообщением НОВОЙ chat-сессии, чат сам принимает
роль сабагента, а результат в конце получает `delivery_state='dropped'`
(родитель закрыт по user-boundary → fail-closed #55578).

Симптомы от Заказчика: «я провалился в сабагента», «отчет сабагента не пришел».

## Превентивные правила

1. **Не диспатчить delegate_task в ходу чужого входящего сообщения**
   (steer/OUT-OF-BAND) на границе хода — сначала завершить ход, затем
   диспатч обычным инструментом. Здоровые диспатчи (21:01–22:52 2026-10-01)
   давали 4/4 изолированных subagent-сессий и `delivered`.
2. **Главная сессия всегда называется `main`** — Заказчик возвращается через
   `/resume main`. Вотчдог `~/.hermes/scripts/session_watchdog.py` (крон */2,
   no_agent) автоматически возвращает тайтл `main` активной DM-сессии.
3. Вотчдог также **однократно** предупреждает о `delivery_state='dropped'`
   делегациях за последние 24ч (дедуп в `~/.hermes/state/watchdog_dropped_seen.json`).

## Диагностика (проверено 2026-10-02)

```bash
# Куда сейчас смотрит чат:
sqlite3 ~/.hermes/state.db "SELECT entry_json FROM gateway_routing WHERE session_key LIKE 'agent:main:telegram:dm:%';"
# Проваленные доставки за 24ч:
sqlite3 ~/.hermes/state.db "SELECT delegation_id, parent_session_id FROM async_delegations WHERE delivery_state='dropped' AND state='completed' AND completed_at > strftime('%s','now')-86400;"
# Читать результат dropped-делегации:
sqlite3 ~/.hermes/state.db "SELECT result_json FROM async_delegations WHERE delegation_id='...';"
```

Тест health: `python3 ~/.hermes/scripts/session_watchdog.py`
→ exit 0 = чисто, exit 1 = было лечение/warn.

## Урок 2026-10-03: вотчдог сам падал (UNIQUE sessions.title)

`UPDATE sessions SET title='main'` падает с IntegrityError, если «main» застрял
у мёртвой старой сессии (title UNIQUE, частичный индекс) — вотчдог умирал каждый
прогон (failure_streak 8+), сессия оставалась без тайтла. Фикс в heal(): перед
переименованием освобождать тайтл у держателей != active (title=NULL). Всегда
прогонять вотчдог руками дважды после правки: 1-й лечит, 2-й должен дать exit 0.

Апстрим-репорт: NousResearch/hermes-agent#92859 + наш комментарий (telegram repro,
2026-10-02).

## Урок 2026-10-03 (вечер): stall → session_reset → dropped-делегация

Вторая разновидность того же класса: рабочая сессия упёрлась в max iterations
(16), упал background-процесс, gateway залип (stall idle>300s при pending
inbound), затем session_reset — родительская сессия «перманентно ушла», и
делегация получила `targets permanently-gone session; terminally dropping
delivery`. РЕЗУЛЬТАТ САБАГЕНТА НЕ ТЕРЯЕТСЯ: он лежит в
`async_delegations.result_json` даже при dropped — читать оттуда и
восстанавливать ход в новой сессии руками. Признаки в errors.log:
`Session stall detected ... last_activity=initializing`, `Hermes Relay drained
orphaned scope`, `turn finalization failed: session is closing`. При потере
контекста Заказчиком: сначала читать async_delegations за 24ч, потом доклад.