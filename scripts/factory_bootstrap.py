#!/usr/bin/env python3
"""factory_bootstrap.py — установка AI Factory на новую машину.

Одна команда для чистой машины: проверяет окружение, развертывает state-каталоги,
ставит крон вотчдога и прогоняет приемочный тест переносимости. Секреты НЕ
переносит (кладутся вручную в ~/.hermes/.env).

Usage:
  python3 scripts/factory_bootstrap.py [--flow-mode shadow|enforcing] [--skip-cron]

Что делает:
  1. Проверка окружения: python >= 3.10, git, node/npx (для openspec CLI), pytest.
  2. State-каталоги: ~/.hermes/state/ (реестр, flow_mode.json с дефолтом),
     ~/.hermes/state/session-archive/.
  3. flow_mode.json — дефолт shadow (безопасно; enforcing — явное решение Заказчика).
  4. Крон вотчдога session_watchdog.py (*/2, no-agent) — если не --skip-cron.
  5. Приемочный тест переносимости: pytest tests/ фабрики (полный).
     Опционально --with-e2e: плюс smoke flowctl на fixture-репо.

Ничего НЕ делает: не трогает секреты, не пушит, не создает проектов
(проекты — factory_init.py --target).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
STATE = HERMES_HOME / "state"
MODE_FILE = STATE / "flow_mode.json"
ARCHIVE_DIR = STATE / "session-archive"
WATCHDOG = FACTORY / "scripts" / "session_watchdog.py"
DELEGATE_WATCHDOG = FACTORY / "scripts" / "delegate_watchdog.py"


def step(msg: str) -> None:
    print(f"[bootstrap] {msg}")


def check_env() -> bool:
    ok = True
    def _run(cmd: list[str]) -> str:
        nonlocal ok
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except FileNotFoundError:
            print(f"  MISSING: {cmd[0]}")
            ok = False
            return ""
        out = (r.stdout or r.stderr).strip().splitlines()
        line = out[0] if out else ""
        print(f"  {cmd[0]}: {line}")
        return line
    v = _run(["python3", "--version"])
    if v and v.startswith("Python 3."):
        try:
            minor = int(v.split()[1].split(".")[1])
            if minor < 10:
                print("  python < 3.10 — недостаточно")
                ok = False
        except (IndexError, ValueError):
            pass
    _run(["git", "--version"])
    if shutil.which("npx") is None:
        print("  npx: MISSING (нужен для openspec CLI: npm i -g @fission-ai/openspec)")
        ok = False
    else:
        _run(["npx", "--version"])
    if shutil.which("pytest") is None and not (FACTORY / "venv").exists():
        print("  pytest: MISSING (pip install pytest)")
        # не роняем: pytest может быть в venv
    return ok


def state_dirs() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if not MODE_FILE.exists():
        payload = {"mode": "shadow",
                   "since": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "by": "bootstrap-default"}
        tmp = MODE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, MODE_FILE)
        step(f"flow_mode.json создан (дефолт shadow): {MODE_FILE}")
    else:
        step(f"flow_mode.json уже есть: {json.loads(MODE_FILE.read_text())['mode']}")


def ensure_watchdog_cron() -> None:
    if not WATCHDOG.exists():
        step("session_watchdog.py не найден — крон пропущен")
        return
    job = f"*/2 * * * * cd {FACTORY} && python3 {WATCHDOG} >> {STATE / 'watchdog.log'} 2>&1"
    try:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = cur.stdout if cur.returncode == 0 else ""
    except FileNotFoundError:
        step("crontab недоступен — вотчдог пропущен (поставить вручную)")
        return
    changed = False
    if "session_watchdog.py" not in existing:
        existing = (existing.rstrip("\n") + "\n" + job + "\n") if existing.strip() else job + "\n"
        changed = True
    if DELEGATE_WATCHDOG.exists() and "delegate_watchdog.py" not in existing:
        job2 = f"*/5 * * * * cd {FACTORY} && python3 {DELEGATE_WATCHDOG} >> {STATE / 'delegate_watchdog.log'} 2>&1"
        existing = (existing.rstrip("\n") + "\n" + job2 + "\n") if existing.strip() else job2 + "\n"
        changed = True
    if not changed:
        step("крон вотчдогов уже стоят")
        return
    w = subprocess.run(["crontab", "-"], input=existing, capture_output=True, text=True)
    step("кроны вотчдогов установлены (*/2 + */5)" if w.returncode == 0
         else f"кроны НЕ установлены: {w.stderr.strip()}")


def acceptance_tests() -> bool:
    step("приемочный тест переносимости: pytest tests/ ...")
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       cwd=FACTORY, capture_output=True, text=True)
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "?"
    print(f"  {tail}")
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--flow-mode", choices=("shadow", "enforcing"), default="shadow",
                    help="начальный режим (дефолт shadow — безопасно)")
    ap.add_argument("--skip-cron", action="store_true", help="не ставить крон вотчдога")
    ap.add_argument("--skip-tests", action="store_true", help="не гонять приемочные тесты")
    args = ap.parse_args()

    step("1/4 окружение")
    env_ok = check_env()
    step("2/4 state-каталоги и режим")
    state_dirs()
    if args.flow_mode != "shadow":
        # перезаписываем дефолт, если явно попросили
        payload = json.loads(MODE_FILE.read_text(encoding="utf-8"))
        payload.update({"mode": args.flow_mode,
                        "since": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "by": "bootstrap-flag"})
        tmp = MODE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, MODE_FILE)
        step(f"режим установлен: {args.flow_mode}")
    step("3/4 вотчдог")
    if not args.skip_cron:
        ensure_watchdog_cron()
    step("4/4 приемочные тесты")
    tests_ok = True if args.skip_tests else acceptance_tests()

    print()
    if env_ok and tests_ok:
        print("FACTORY-BOOTSTRAP OK: фабрика готова.")
        print("Дальше: секреты в ~/.hermes/.env; проекты — scripts/factory_init.py --target <repo> --name <name>")
        return 0
    print("FACTORY-BOOTSTRAP ЗАВЕРШЕН С ПРЕДУПРЕЖДЕНИЯМИ — исправь MISSING выше и перезапусти.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
