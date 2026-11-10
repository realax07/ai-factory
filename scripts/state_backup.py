#!/usr/bin/env python3
"""state_backup.py — бэкап и восстановление state движка фабрики (J64.6).

State движка (factory_paths.state_dir(): реестр сессий active_sessions.json,
flowctl_state.json, flow_mode.json, инциденты вотчдогов, gate-отчеты) лежит
вне git; при enforcing без него работа встает. Решение Заказчика 2026-11-10 —
«Бэкап + восстановление».

Usage:
  python3 scripts/state_backup.py backup  [--dest DIR] [--keep N] [--include-archive]
  python3 scripts/state_backup.py list    [--dest DIR]
  python3 scripts/state_backup.py restore ARCHIVE [--force]

backup  — архив state-<UTC>.tar.gz в --dest (по умолчанию
          factory_paths.backup_dir(), env AF_BACKUP_DIR); ротация — хранить
          N последних (--keep, по умолчанию 14). session-archive/
          (транскрипты, объемные) — только с --include-archive. Молчит при
          успехе (крон: чисто = пустой stdout), путь архива — с --verbose.
list    — архивы в --dest, новые первыми.
restore — распаковка архива в state_dir. Текущий state не удаляется:
          переименовывается в <state>.before-restore-<UTC>. Если в реестре
          есть активные сессии (reserved/running) — отказ без --force.
          Архив проверяется: только относительные пути внутри state, без
          ссылок и устройств.

Exit: 0 — ок; 1 — отказ (активные сессии, битый архив, нет state); 2 —
ошибка использования.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
import time
from pathlib import Path

import factory_paths as fp  # noqa: E402  (J64.5: пути машины — только оттуда)

PREFIX = "state-"
SUFFIX = ".tar.gz"
DEFAULT_KEEP = 14
ARCHIVE_SUBDIR = "session-archive"
ACTIVE_STATUSES = ("reserved", "running")


def _utc() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def archives(dest: Path) -> list[Path]:
    if not dest.is_dir():
        return []
    return sorted((p for p in dest.iterdir()
                   if p.name.startswith(PREFIX) and p.name.endswith(SUFFIX)),
                  key=lambda p: p.name, reverse=True)


def backup(state: Path, dest: Path, keep: int = DEFAULT_KEEP,
           include_archive: bool = False) -> Path:
    if not state.is_dir():
        raise RuntimeError(f"state не найден: {state}")
    dest = dest.resolve()
    if dest == state.resolve() or state.resolve() in dest.parents:
        raise RuntimeError(f"--dest внутри state ({dest}) — бэкап уйдет вместе с ним")
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{PREFIX}{_utc()}{SUFFIX}"
    n = 1
    while out.exists():          # два бэкапа в одну секунду
        out = dest / f"{PREFIX}{_utc()}-{n}{SUFFIX}"
        n += 1
    tmp = out.with_name(out.name + ".part")

    def _filter(info: tarfile.TarInfo):
        rel = Path(info.name)
        if not include_archive and rel.parts[1:2] == (ARCHIVE_SUBDIR,):
            return None
        if info.issym() or info.islnk() or info.isdev():
            return None
        return info

    with tarfile.open(tmp, "w:gz") as tar:
        tar.add(state, arcname="state", filter=_filter)
    tmp.rename(out)
    for old in archives(dest)[max(keep, 1):]:
        old.unlink()
    return out


def active_sessions(state: Path) -> list[str]:
    reg = state / fp.registry_path().name
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [s.get("delegation_id", "?") for s in data.get("sessions", [])
            if isinstance(s, dict) and s.get("status") in ACTIVE_STATUSES]


def _safe_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = tar.getmembers()
    for m in members:
        p = Path(m.name)
        if p.is_absolute() or ".." in p.parts or p.parts[:1] != ("state",):
            raise RuntimeError(f"недопустимый путь в архиве: {m.name}")
        if not (m.isfile() or m.isdir()):
            raise RuntimeError(f"недопустимый тип записи в архиве: {m.name}")
    return members


def restore(archive: Path, state: Path, force: bool = False) -> Path | None:
    """Распаковывает архив в state; возвращает путь отложенного прежнего state."""
    if not archive.is_file():
        raise RuntimeError(f"архив не найден: {archive}")
    if state.is_dir() and not force:
        active = active_sessions(state)
        if active:
            raise RuntimeError(
                "в текущем state активные сессии: " + ", ".join(active)
                + " — восстановление перезапишет их резервации (--force, если "
                  "это осознанно)")
    staging = state.with_name(state.name + f".restore-{_utc()}")
    try:
        with tarfile.open(archive, "r:gz") as tar:
            members = _safe_members(tar)
            staging.mkdir(parents=True)
            # filter="data" (3.12+): та же защита на уровне tarfile
            extra = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
            tar.extractall(staging, members=members, **extra)
    except (tarfile.TarError, OSError, EOFError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(f"архив не читается: {exc}") from exc
    except RuntimeError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    previous = None
    if state.exists():
        previous = state.with_name(state.name + f".before-restore-{_utc()}")
        state.rename(previous)
    (staging / "state").rename(state)
    staging.rmdir()
    return previous


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--dest", default=None)
    b.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    b.add_argument("--include-archive", action="store_true")
    b.add_argument("--verbose", action="store_true")
    li = sub.add_parser("list")
    li.add_argument("--dest", default=None)
    r = sub.add_parser("restore")
    r.add_argument("archive")
    r.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    state = fp.state_dir()
    dest = Path(args.dest).expanduser() if getattr(args, "dest", None) else fp.backup_dir()
    try:
        if args.cmd == "backup":
            out = backup(state, dest, args.keep, args.include_archive)
            if args.verbose:
                print(f"state_backup: {out}")
        elif args.cmd == "list":
            for p in archives(dest):
                print(f"{p}  {p.stat().st_size} байт")
        else:
            prev = restore(Path(args.archive).expanduser(), state, args.force)
            print(f"state_backup: state восстановлен из {args.archive} в {state}"
                  + (f"; прежний state — {prev}" if prev else ""))
    except RuntimeError as exc:
        print(f"state_backup: ОТКАЗ — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
