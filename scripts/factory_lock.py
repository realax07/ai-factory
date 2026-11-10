#!/usr/bin/env python3
"""factory_lock.py — версия фабрики, чьи ворота гоняет CI проекта (J65.7).

Проект хранит в корне `factory.lock`:

    # factory.lock — ворота фабрики для CI проекта (J65.7)
    repo=realax07/ai-factory
    sha=<40 hex коммита фабрики>

`.github/workflows/flow.yml` проекта делает checkout фабрики на этот SHA в
`.factory/` и запускает ее flow_check и pr_validate против проекта.
Обновление ворот в проекте = PR с одной строкой `sha=` (этой командой).
Без factory.lock CI берет копии `scripts/` проекта (как до J65.7).

Usage:
  python3 scripts/factory_lock.py show   --target <проект>
  python3 scripts/factory_lock.py update --target <проект> [--sha SHA] [--repo owner/name]

update без --sha берет HEAD фабрики — только если он опубликован (есть в
ветке origin): CI проекта не сможет сделать checkout неопубликованного
коммита. Exit: 0 — ок; 1 — отказ (битый lock, неопубликованный SHA); 2 —
ошибка использования.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
LOCK_NAME = "factory.lock"
DEFAULT_REPO = "realax07/ai-factory"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
HEADER = "# factory.lock — ворота фабрики для CI проекта (J65.7)\n"


class LockError(Exception):
    pass


def read_lock(target: Path) -> dict | None:
    """{'repo', 'sha'} или None, если файла нет; битый файл — LockError."""
    path = target / LOCK_NAME
    if not path.is_file():
        return None
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise LockError(f"{LOCK_NAME}: строка без '=': {line!r}")
        data[key.strip()] = value.strip()
    if not SHA_RE.match(data.get("sha", "")):
        raise LockError(f"{LOCK_NAME}: sha должен быть 40 hex, есть {data.get('sha')!r}")
    if not REPO_RE.match(data.get("repo", "")):
        raise LockError(f"{LOCK_NAME}: repo должен быть owner/name, есть {data.get('repo')!r}")
    return {"repo": data["repo"], "sha": data["sha"]}


def write_lock(target: Path, sha: str, repo: str = DEFAULT_REPO) -> Path:
    if not SHA_RE.match(sha):
        raise LockError(f"sha должен быть 40 hex: {sha!r}")
    if not REPO_RE.match(repo):
        raise LockError(f"repo должен быть owner/name: {repo!r}")
    path = target / LOCK_NAME
    path.write_text(f"{HEADER}repo={repo}\nsha={sha}\n", encoding="utf-8")
    return path


def _git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(FACTORY), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise LockError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def published_head() -> str:
    """HEAD фабрики, если он есть в какой-либо ветке origin; иначе LockError."""
    sha = _git("rev-parse", "HEAD")
    if not _git("branch", "-r", "--contains", sha):
        raise LockError(f"HEAD фабрики {sha[:12]} не опубликован в origin — CI "
                        "проекта не сможет его получить; запушь или передай --sha")
    return sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "update"):
        p = sub.add_parser(name)
        p.add_argument("--target", required=True)
        if name == "update":
            p.add_argument("--sha")
            p.add_argument("--repo", default=None)
    args = ap.parse_args(argv)
    target = Path(args.target).resolve()
    try:
        if args.cmd == "show":
            lock = read_lock(target)
            print(f"{LOCK_NAME}: нет — CI берет scripts/ проекта" if lock is None
                  else f"{LOCK_NAME}: {lock['repo']}@{lock['sha']}")
            return 0
        current = read_lock(target) if (target / LOCK_NAME).is_file() else None
        repo = args.repo or (current or {}).get("repo") or DEFAULT_REPO
        sha = args.sha or published_head()
        write_lock(target, sha, repo)
        print(f"{LOCK_NAME}: {repo}@{sha}"
              + (f" (было {current['sha'][:12]})" if current else ""))
        return 0
    except LockError as exc:
        print(f"factory_lock: ОТКАЗ — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
