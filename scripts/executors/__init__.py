"""Исполнители агентных стадий пакетного раннера (J65.5 + J64.7).

Исполнитель — модуль `scripts/executors/<имя>.py` с объектом `EXECUTOR`
(подкласс `Executor`). Манифест выбирает его префиксом стадии
`run: <имя>:<роль>` (решение Заказчика 2026-11-12 «Префикс run»); реестр
находит модуль по имени — регистрации в раннере нет. Новый исполнитель —
один файл здесь, без правок flowctl/gate_runner/session_check: ворота стадии
(prepare, резервация, сверка диффа, гейты, provenance) делает раннер вокруг
вызова, одинаково для любого исполнителя.

Интерфейс (соответствие ТЗ J65.5: start/wait/list_active/transcript):
  manual            — ручная стоп-точка ПМ (раннер не исполняет, ждет ПМ);
  preflight()       — готовность до ворот входа; провал — ExecutorUnavailable;
                      возвращает provenance (например, sha256 guard'а);
  prepare_workdir() — ролевая инструкция в рабочий каталог (start);
  command(launch)   — argv + env процесса (start); запуск с таймаутом и
                      ожидание (wait) — общий spawn раннера;
  list_active()     — активные запуски исполнителя для вотчдога обхода;
  transcript(ref)   — транскрипт запуска, если исполнитель его хранит.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ExecutorUnavailable(Exception):
    """Исполнитель не готов (нет guard'а, команды, бинаря) — STOP стадии до
    ворот входа. code — машиночитаемый код отказа."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class StageLaunch:
    """Что исполнитель получает от раннера на одну агентную стадию."""
    role: str              # роль-пак (dev, code-reviewer, …)
    flow_role: str         # роль политики (dev, code_reviewer, …)
    workdir: Path          # worktree пакета
    brief: str             # бриф стадии (собирает раннер)
    zones: list[str]       # зоны записи — префикс-форма (normalize_zone)
    provider: str
    model: str
    package: str
    env: dict = field(default_factory=dict)   # env процесса (раннер: os.environ + стенд)


@dataclass
class ActiveRun:
    """Активный запуск исполнителя (для вотчдога обхода)."""
    executor: str
    pid: int | None
    cwd: str
    command: str
    ref: str = ""          # id запуска у исполнителя (делегация Hermes и т.п.)


class Executor:
    name = ""
    manual = False         # True — стоп-точка ПМ, раннер не запускает процесс
    agents_note = ("этот файл — ролевая инструкция исполнителя, проектные "
                   "правила — в AGENTS.md.")

    def preflight(self) -> dict:
        return {}

    def prepare_workdir(self, workdir: Path, role_text: str) -> tuple[str, list[Path]]:
        """Роль → AGENTS.md в корень рабочего каталога; если там уже есть
        AGENTS.md проекта — рядом AGENTS.<имя>.md (проектные правила не
        затираются, BUG-026). Возвращает (имя файла для брифа, файлы на
        уборку после запуска — в дифф стадии они не попадают)."""
        target = workdir / "AGENTS.md"
        if target.exists():
            path = workdir / f"AGENTS.{self.name}.md"
            path.write_text(role_text + "\n---\n> Читай вместе с AGENTS.md "
                            "проекта: " + self.agents_note + "\n", encoding="utf-8")
        else:
            path = target
            path.write_text(role_text, encoding="utf-8")
        return path.name, [path]

    def command(self, launch: StageLaunch) -> tuple[list[str], dict]:
        raise NotImplementedError

    def list_active(self) -> list[ActiveRun]:
        return []

    def transcript(self, ref: str) -> str | None:
        return None


def names() -> list[str]:
    """Имена всех исполнителей (модули пакета с EXECUTOR)."""
    out = []
    for info in pkgutil.iter_modules(__path__):
        if NAME_RE.match(info.name) and get(info.name, required=False) is not None:
            out.append(info.name)
    return sorted(out)


def get(name: str, required: bool = True) -> Executor | None:
    if not NAME_RE.match(name or ""):
        if required:
            raise KeyError(f"недопустимое имя исполнителя: {name!r}")
        return None
    try:
        mod = importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as exc:
        if exc.name != f"{__name__}.{name}":
            raise                          # сломан сам модуль — не маскируем
        if required:
            raise KeyError(f"исполнитель {name!r} не найден "
                           f"(scripts/executors/{name}.py)") from None
        return None
    ex = getattr(mod, "EXECUTOR", None)
    if not isinstance(ex, Executor):
        if required:
            raise KeyError(f"scripts/executors/{name}.py без EXECUTOR")
        return None
    return ex


# ------------------------------------------------- процессы (для list_active)

def processes() -> list[tuple[int, str]]:
    """(pid, командная строка) процессов машины; недоступно — []."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,args="], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if pid.isdigit():
            rows.append((int(pid), cmd.strip()))
    return rows


def process_cwd(pid: int) -> str | None:
    """Рабочий каталог процесса: /proc (Linux) или lsof (macOS)."""
    proc = Path(f"/proc/{pid}/cwd")
    if proc.exists():
        try:
            return os.path.realpath(proc)
        except OSError:
            return None
    try:
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        if line.startswith("n"):
            return os.path.realpath(line[1:])
    return None


def active_by_binary(executor: str, binary: str) -> list[ActiveRun]:
    """Активные процессы, чей argv[0] — указанный бинарь (по имени файла)."""
    own = os.getpid()
    runs = []
    for pid, cmd in processes():
        argv0 = cmd.split(" ", 1)[0]
        if pid == own or os.path.basename(argv0) != binary:
            continue
        cwd = process_cwd(pid)
        if cwd:
            runs.append(ActiveRun(executor, pid, cwd, cmd))
    return runs

