#!/usr/bin/env python3
"""session_watchdog.py — вотчдог роутинга Telegram-чата Заказчика (J19).

Проблема: ключ роутинга agent:main:telegram:dm:<chat> может указывать на
ended-сессию в state.db (после /stop + session_reset делегации или фейловера) —
Заказчик «проваливается» в зомби-сабагента, heal срабатывает только на inbound.

Вотчдог (cron, --no-agent): каждую минуту читает state.db:
  - для каждого routing_key вида agent:main:telegram:dm:* сверяет entry.session_id
    с sessions.ended_at;
  - если сессия ended и это НЕ осознанный сброс — удаляет залипшую запись роутинга
    (и из gateway_routing, и из sessions.json): следующее сообщение Заказчика
    создаст свежую сессию, ответ придет от главной сессии (ассистента);
  - доставка отчетов делегаций при этом не страдает: результат delegation
    остается в записях делегации, ворота no_zombie_holds при живом ключе не срабатывают.

Exit 1 = было лечение (для крона с failure-deliver). Тихий выход 0 = чисто.

Запуск: hermes cron create '*/2 * * * *' --no-agent --script session_watchdog.py
"""

import json
import sqlite3
import sys
import time
from pathlib import Path

STATE_DB = Path.home() / ".hermes/state.db"
SESSIONS_JSON = Path.home() / ".hermes/sessions/sessions.json"
DM_PREFIX = "agent:main:telegram:dm:"
DRY_RUN = "--dry-run" in sys.argv


def heal() -> list[str]:
    con = sqlite3.connect(
        f"file:{STATE_DB}?mode=rw", timeout=10, uri=True
    )
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    actions: list[str] = []

    # 1) залипшие ключи роутинга: routing entry -> ended-сессия
    stale_keys: list[tuple[str, str, str]] = []  # (routing_key, session_id, ended_at)
    for row in cur.execute(
        "SELECT session_key, entry_json FROM gateway_routing WHERE session_key LIKE ?",
        (DM_PREFIX + "%",),
    ):
        try:
            entry = json.loads(row["entry_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        sid = entry.get("session_id", "")
        if not sid:
            continue
        ended = cur.execute(
            "SELECT ended_at FROM sessions WHERE id = ?", (sid,)
        ).fetchone()
        if ended and ended["ended_at"]:
            stale_keys.append((row["session_key"], sid, str(ended["ended_at"])))

    for key, sid, ended_at in stale_keys:
        actions.append(
            f"heal: routing '{key}' указывал на ended-сессию {sid} "
            f"(ended_at={ended_at}) — запись удалена, следующий inbound создаст свежую сессию"
        )
        if not DRY_RUN:
            cur.execute(
                "DELETE FROM gateway_routing WHERE session_key = ?", (key,)
            )

    if not DRY_RUN and actions:
        con.commit()

    # 2) живые, но незавершенные holds делегаций (информативно, не лечим)
    try:
        rows = list(
            cur.execute(
                "SELECT delegation_id, routing_key, state, updated_at "
                "FROM async_delegations WHERE state NOT IN ('delivered','failed','cancelled')"
            )
        )
        for r in rows:
            age_min = (time.time() - float(r["updated_at"] or 0)) / 60
            if age_min > 120:
                actions.append(
                    f"warn: hold {r['delegation_id']} ({r['routing_key']}, state={r['state']}) "
                    f"висит {age_min:.0f} мин"
                )
    except sqlite3.OperationalError:
        pass  # таблица/колонка отсутствует в этой версии — не критично

    # 3) sessions.json: сессии telegram, отсутствующие в state.db
    try:
        data = json.loads(SESSIONS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    ghost = [
        k
        for k, v in data.items()
        if k.startswith(DM_PREFIX)
        and not cur.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (v.get("session_id", ""),)
        ).fetchone()
    ]
    if ghost:
        actions.append(f"heal: ghost-записи sessions.json (нет в state.db): {ghost}")
        if not DRY_RUN:
            for k in ghost:
                data.pop(k, None)
            SESSIONS_JSON.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    con.close()
    return actions


def main() -> int:
    if not STATE_DB.exists():
        print(f"no state.db at {STATE_DB}")
        return 0
    actions = heal()
    if actions:
        print("\n".join(actions))
        return 1 if not DRY_RUN else 0
    print("ok: роутинг чист, зомби-holds нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
