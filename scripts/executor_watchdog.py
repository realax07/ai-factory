#!/usr/bin/env python3
"""executor_watchdog.py — обход любого исполнителя агентов (J65.5 + J64.7).

Вотчдог делегаций Hermes (delegate_watchdog) видит только delegate_task.
Здесь — исполнители-процессы (pi, stub, …, `scripts/executors/`): активный
запуск исполнителя, чей рабочий каталог не совпадает с worktree живой
резервации реестра сессий (reserved/running/finished/needs_attention), —
обход ворот (раннер всегда резервирует worktree пакета до запуска). Ручные
исполнители (hermes) пропускаются: их сверяет delegate_watchdog.

Журнал запусков раннера (`<state>/executor_runs.jsonl`) дополняет инцидент:
есть незакрытый start раннера на этот каталог — запуск раннера, чья
резервация уже не живая (сбой раннера), а не ручной.

Зовется из delegate_watchdog (крон */5): находки идут в тот же канал
инцидентов с id `proc:<исполнитель>:<pid>`. Отдельно:
  python3 scripts/executor_watchdog.py [--registry PATH] [--json]
Exit: 0 — чисто; 1 — есть обход.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factory_paths as fp  # noqa: E402
import executors  # noqa: E402

LIVE = ("reserved", "running", "finished", "needs_attention")
RUNS_JOURNAL = "executor_runs.jsonl"


def _real(path: str) -> str:
    try:
        return os.path.realpath(path)
    except OSError:
        return path


def live_worktrees(registry: Path) -> set[str]:
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {_real(s["worktree"]) for s in data.get("sessions", [])
            if isinstance(s, dict) and s.get("worktree")
            and s.get("status", "reserved") in LIVE}


def open_runner_starts(journal: Path) -> dict[str, dict]:
    """Незакрытые start раннера по рабочему каталогу."""
    opened: dict[str, dict] = {}
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
    except OSError:
        return opened
    for line in lines:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        wd = _real(str(ev.get("workdir") or ""))
        if ev.get("event") == "start":
            opened[wd] = ev
        elif ev.get("event") == "end":
            opened.pop(wd, None)
    return opened


def scan(registry: Path, journal: Path | None = None,
         names: list[str] | None = None) -> list[dict]:
    """Обходы: активные запуски исполнителей-процессов вне живых резерваций."""
    live = live_worktrees(registry)
    starts = open_runner_starts(journal) if journal else {}
    found = []
    for name in names if names is not None else executors.names():
        ex = executors.get(name, required=False)
        if ex is None or ex.manual:
            continue
        for run in ex.list_active():
            cwd = _real(run.cwd)
            if any(cwd == w or cwd.startswith(w + os.sep) for w in live):
                continue
            start = starts.get(cwd)
            found.append({
                "delegation_id": f"proc:{name}:{run.pid}",
                "kind": "executor_bypass",
                "executor": name, "pid": run.pid, "cwd": cwd,
                "command": run.command[:300],
                "runner_start": start,   # не None — сбой раннера, не ручной запуск
                "detail": (f"процесс {name} (pid {run.pid}) в {cwd} без живой "
                           "резервации реестра сессий — запуск мимо ворот"
                           + (" (start раннера без end: резервация уже не живая)"
                              if start else "")),
            })
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--registry", default=None)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)
    registry = Path(args.registry) if args.registry else fp.registry_path()
    found = scan(registry, registry.parent / RUNS_JOURNAL)
    if args.as_json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    elif found:
        for f in found:
            print(f"BYPASS {f['delegation_id']}: {f['detail']}")
    else:
        print("clean: активных запусков исполнителей мимо ворот нет")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
