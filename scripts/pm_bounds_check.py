#!/usr/bin/env python3
"""pm_bounds_check.py — детерминированные ворота границ ПМ-сабагента (J3, блок J).

Принцип Заказчика «где можно проверить скриптами — проверяем скриптами»:
декларативные границы в agents/pm_agent.md дублируются проверяемым слоем.
Проверяет два класса нарушений:

  1. Зона записи ПМ-сабагента: diff/содержимое указанных коммитов не должно
     трогать защищенные пути (спеки конвейера, контракты, промпты ролей, AGENTS.md)
     без пометки флоу в сообщении коммита (изменения конвейера легальны только
     через Флоу 1/4 с решением Заказчика, поэтому требуем явной пометки).
  2. Реестр active_sessions.json: записи ПМ-сабагента обязаны иметь project +
     owner_pm; пары project/owner_pm не должны смешиваться (у записи project
     владелец определяется однозначно).

Использование:
  pm_bounds_check.py --commits HASH[,HASH...] [--repo PATH]   # проверка дифов
  pm_bounds_check.py --sessions [PATH]                        # проверка реестра
  pm_bounds_check.py --all --commits ... --sessions ...       # всё сразу

Exit 0 = чисто; exit 1 = нарушения (список в stdout).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent

# Защищенные пути фабрики: ПМ-сабагент не меняет их без явной пометки
# "[pipeline]" / "[флоу 4]" в subject коммита (изменение конвейера — отдельная
# задача, запущенная Заказчиком, а не побочный эффект проектной фазы).
PROTECTED_PATHS = (
    "openspec/specs/",
    "contracts/",
    "AGENTS.md",
    "agents/README.md",
)
# Промпты ролей: менять можно, но каждый такой диф — событие конвейера.
ROLE_PROMPT_PREFIX = "agents/"

PIPELINE_MARKERS = ("[pipeline]", "[флоу 4]", "[flow 4]", "[конвейер]")
ALLOWED_EXTENSIONS_IN_ROLES = (".md", ".yaml", ".yml")

REQUIRED_SESSION_FIELDS = ("delegation_id", "role", "project", "owner_pm", "status")


def sh(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    return proc.stdout or ""


def check_commit(repo: Path, commit: str) -> list[str]:
    problems: list[str] = []
    files_raw = sh(repo, "show", "--name-only", "--format=", commit)
    files = [f for f in files_raw.splitlines() if f.strip()]
    if not files:
        return [f"{commit}: коммит не найден или пуст"]

    subject = sh(repo, "show", "-s", "--format=%s", commit).strip()
    has_marker = any(m in subject for m in PIPELINE_MARKERS)
    protected_touched = [
        f for f in files
        if f.startswith(PROTECTED_PATHS) or f == "AGENTS.md"
    ]
    role_touched = [
        f for f in files
        if f.startswith(ROLE_PROMPT_PREFIX) and f != "agents/README.md"
        and f.endswith(ALLOWED_EXTENSIONS_IN_ROLES)
    ]

    if (protected_touched or role_touched) and not has_marker:
        what = ", ".join(protected_touched[:3] or role_touched[:3])
        problems.append(
            f"{commit}: затронуты защищенные пути конвейера ({what}) без пометки "
            f"[pipeline] в subject — изменения конвейера только через Флоу 1/4 "
            f"с решением Заказчика (граница J3)"
        )

    for f in files:
        if f.startswith(ROLE_PROMPT_PREFIX) and not f.endswith(ALLOWED_EXTENSIONS_IN_ROLES):
            problems.append(
                f"{commit}: {f} — не-документный файл в agents/ вне зоны ПМ (J3)"
            )
    return problems


def check_sessions(path: Path) -> list[str]:
    problems: list[str] = []
    if not path.exists():
        return [f"{path}: файл реестра не найден"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"{path}: не читается как JSON: {exc}"]

    seen: dict[tuple[str, str], str] = {}
    for i, s in enumerate(data.get("sessions", [])):
        label = f"sessions[{i}] ({s.get('delegation_id', '?')})"
        for field in REQUIRED_SESSION_FIELDS:
            if not s.get(field):
                problems.append(f"{label}: отсутствует обязательное поле '{field}' (J2)")
        project, owner = s.get("project", ""), s.get("owner_pm", "")
        if project and owner:
            key = (project, owner)
            if key in seen and seen[key] != s.get("delegation_id"):
                problems.append(
                    f"{label}: пара project/owner_pm {key} повторяется — "
                    f"один ПМ = один проект (J2)"
                )
            seen.setdefault(key, s.get("delegation_id", ""))
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=str(FACTORY), help="git-репозиторий для --commits")
    ap.add_argument("--commits", help="коммит(ы) через запятую")
    ap.add_argument("--sessions", nargs="?", const=str(
        Path.home() / ".hermes/state/active_sessions.json"),
        help="путь к active_sessions.json")
    args = ap.parse_args()

    problems: list[str] = []
    if args.commits:
        repo = Path(args.repo).resolve()
        for c in [c.strip() for c in args.commits.split(",") if c.strip()]:
            problems += check_commit(repo, c)
    if args.sessions:
        problems += check_sessions(Path(args.sessions).expanduser())

    if problems:
        print("pm_bounds_check: FAIL — нарушения границ ПМ:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("pm_bounds_check: OK — границы ПМ-сабагента соблюдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
