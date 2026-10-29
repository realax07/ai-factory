#!/usr/bin/env python3
"""Вотчдог деградации моделей в чатах гейтвея (v2 — offset-модель).

Читает ТОЛЬКО новые байты errors.log (offset в state-файле) — старые
аномалии не всплывают повторно. Аномалия = runaway repetition / stream cut /
clean EOF без finish_reason. Алерт раз на кластер (не чаще раза в час на тип),
тишина = норма. Первый запуск: offset = размер файла (история не алертится).

stdlib-only. exit 0 всегда.
"""
import json
import re
import sys
import time
from pathlib import Path

LOG = Path("/home/openclaw/.hermes/logs/errors.log")
STATE = Path("/home/openclaw/.hermes/state/chat-degrade-watchdog.json")
# Clean EOF (сервер молча закрыл поток) — транзиторный само-ретраящийся сбой
# вызовов сабагентов, НЕ деградация чата: не алертим. Настоящий сигнал —
# runaway repetition (зацикливание модели на длинном контексте) и Stream cut.
PATTERNS = re.compile(r"(runaway repetition loop|Stream cut:)")
COOLDOWN = 3600
MAX_READ = 2_000_000  # предохранитель: не читать разом больше 2 MB


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
    size = LOG.stat().st_size
    state = load_state()
    offset = state.get("offset")
    if offset is None or offset > size:
        # первый запуск или ротация лога: начинаем «с сейчас»
        state["offset"] = size
        save_state(state)
        return 0
    if size == offset:
        return 0
    with LOG.open("rb") as f:
        f.seek(offset)
        chunk = f.read(min(size - offset, MAX_READ))
        new_offset = f.tell()
    text = chunk.decode("utf-8", errors="replace")
    state["offset"] = new_offset

    now = time.time()
    alerts = []
    seen = set()
    for line in text.splitlines():
        m = PATTERNS.search(line)
        if not m:
            continue
        kind = "repetition" if "repetition" in m.group(1) else "stream-cut"
        if kind in seen:
            continue
        seen.add(kind)
        if now - state.get(f"_last_{kind}", 0) < COOLDOWN:
            continue
        state[f"_last_{kind}"] = now
        ts = re.match(r"(\S+ \S+)", line)
        model = re.search(r"model=([\w.\-]+)", line)
        sess = re.search(r"\[(\d{8}_[0-9a-f]+)\]", line)
        alerts.append(
            f"деградация модели {model.group(1) if model else '?'}"
            f" (сессия {sess.group(1) if sess else '?'}, {ts.group(1)[-8:] if ts else ''})"
        )
    # гигиена state (храним не более 60 ключей)
    if len(state) > 60:
        keep = dict(sorted(state.items(), key=lambda kv: 0 if kv[0].startswith("_") else 1)[:60])
        state = keep
    save_state(state)
    if alerts:
        print(
            "АНОМАЛИЯ гейтвея: " + "; ".join(alerts)
            + ". Возможна деградация модели на длинном контексте — собеседнику может требоваться /new."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
