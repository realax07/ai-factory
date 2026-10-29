#!/usr/bin/env python3
"""Вотчдог деградации моделей в чатах гейтвея.

Сканирует хвост gateway.log на признаки деградации модели (runaway
repetition, stream cut) и шлет ОДНО оповещение на аномалию (дедуп через
state-файл). Тишина = норма (политика вотчдогов 2026-10-23).

stdlib-only. exit 0 всегда (кроме фатальной ошибки окружения).
"""
import json
import re
import sys
import time
from pathlib import Path

LOG = Path("/home/openclaw/.hermes/logs/errors.log")
STATE = Path("/home/openclaw/.hermes/state/chat-degrade-watchdog.json")
PATTERNS = re.compile(
    r"(runaway repetition loop|Stream cut:|Clean EOF, no finish_reason)"
)
# алерт, если аномалия встречалась в последних N строках лога
TAIL = 400
COOLDOWN = 3600  # не чаще раза в час на один тип


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(s):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False))
    tmp.replace(STATE)


def main():
    if not LOG.exists():
        return 0
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-TAIL:]
    lines += [l.replace("agent.chat_completion_helpers: ", " ") for l in lines if False]
    state = load_state()
    now = time.time()
    alerts = []
    for line in reversed(lines):
        if not PATTERNS.search(line):
            continue
        m = re.match(r"(\S+)\s", line)
        ts = m.group(1) if m else ""
        kind = "repetition" if "repetition" in line else "stream-cut"
        key = f"{kind}:{ts[:13]}"  # час + тип
        if key in state:
            continue
        if now - state.get(f"_last_{kind}", 0) < COOLDOWN:
            continue
        # вытащить модель/чата из строки
        chat = re.search(r"\[(\d{8}_[0-9a-f]+)\]", line)
        model = re.search(r"model=([\w.\-]+)", line)
        alerts.append(
            f"деградация модели: {model.group(1) if model else '?'}"
            f" (сессия {chat.group(1) if chat else '?'}, {ts[11:19]} UTC)"
        )
        state[f"_last_{kind}"] = now
    # мусор-сборка старых key
    for k in [k for k in state if not k.startswith("_")]:
        pass
    if alerts:
        save_state(state)
        print(
            "АНОМАЛИЯ гейтвея: " + "; ".join(alerts)
            + ". Чат-собеседнику может требоваться /new или пауза — модель деградирует на длинном контексте."
        )
        return 0
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
