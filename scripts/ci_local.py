#!/usr/bin/env python3
"""ci_local.py — прогон сьюта так, как его видит CI (J65.12).

Повод: «локально зеленое, в CI красное» по двум устойчивым причинам —
полная история git (тест digest J64.18 сверял старый пин и проходил, в
shallow-клоне CI падал) и реальный HOME/env машины (J64.2, BUG-025). Скрипт
воспроизводит условия CI для `pytest tests/` (job `test-flow-control`) и
`flow_check` (шаг job `flow`):

1. клон глубины 1 ЗАКОММИЧЕННОГО HEAD во временный каталог (`git init` +
   `fetch --depth 1 <sha>`) — незакоммиченные правки в прогон не попадают;
2. окружение с нуля: пустой HOME, без GITHUB_*/GIT_*/HERMES_HOME/AF_*/
   AI_FACTORY_HOME; git-шаги — без глобального и системного git-конфига;
   PATH и PYTHONUSERBASE сохраняются (иначе pytest из user-site не
   найдется — класс BUG-025);
3. `python -m pytest tests/ -q` и `python scripts/flow_check.py .` в клоне.

Чем отличается от CI (сознательно): интерпретатор — текущий (CI — 3.12);
пакеты user-site разработчика видны (PYTHONUSERBASE); на PR CI гоняет
merge-коммит с base, ci_local — HEAD ветки; HOME пустой (строже раннера
CI); в клоне нет remote `origin`; `openspec validate` не запускается.

Usage:
  python3 scripts/ci_local.py [--repo PATH] [--keep] [-- <аргументы pytest>]

Exit: 0 — оба шага зеленые; 1 — красный шаг; 2 — ошибка подготовки.
"""
from __future__ import annotations

import argparse
import os
import shutil
import site
import subprocess
import sys
import tempfile
from pathlib import Path

# Переменные, которые не должны протекать из машины в прогон: CI их не
# задает (GITHUB_EVENT_PATH снимается и в flow.yml — env -u).
_KEEP_ENV = ("PATH", "LANG", "LC_ALL", "TMPDIR", "PYTHONUSERBASE")


def ci_env(home: Path) -> dict[str, str]:
    """Окружение прогона: только _KEEP_ENV + пустой HOME."""
    env = {k: os.environ[k] for k in _KEEP_ENV if os.environ.get(k)}
    # Реальный user base — до подмены HOME (BUG-025): pytest из pip --user.
    env.setdefault("PYTHONUSERBASE", site.getuserbase())
    env["HOME"] = str(home)
    return env


def git_env() -> dict[str, str]:
    """Окружение git-шагов: без GIT_* (из git-хука экспортируются GIT_DIR/
    GIT_WORK_TREE/GIT_INDEX_FILE — fetch писал бы в ИСХОДНЫЙ .git и делал
    его shallow) и без глобального/системного конфига (как раннер CI)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    # safe.directory из глобального конфига сохраняется: без него git
    # откажет в репо другого владельца (VPS), а это не условие CI.
    for i, value in enumerate(_global_safe_directories()):
        env[f"GIT_CONFIG_KEY_{i}"] = "safe.directory"
        env[f"GIT_CONFIG_VALUE_{i}"] = value
        env["GIT_CONFIG_COUNT"] = str(i + 1)
    return env


def _global_safe_directories() -> list[str]:
    # GIT_CONFIG_GLOBAL — указатель на сам глобальный конфиг, его сохраняем.
    clean = {k: v for k, v in os.environ.items()
             if not k.startswith("GIT_") or k == "GIT_CONFIG_GLOBAL"}
    got = subprocess.run(["git", "config", "--global", "--get-all",
                          "safe.directory"], capture_output=True, text=True,
                         env=clean)
    return [line for line in got.stdout.splitlines() if line.strip()]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, env=git_env())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--keep", action="store_true",
                    help="не удалять временный каталог (разбор падения)")
    ap.add_argument("pytest_args", nargs="*", help="после --: аргументы pytest")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    head = _git(repo, "rev-parse", "HEAD")
    if head.returncode != 0:
        print(f"ci_local: {repo} — не git-репозиторий или git отказал: "
              f"{head.stderr.strip()}", file=sys.stderr)
        return 2
    sha = head.stdout.strip()
    dirty = _git(repo, "status", "--porcelain").stdout.strip()
    if dirty:
        print("ci_local: ВНИМАНИЕ — есть незакоммиченные изменения, в прогон "
              "они не попадут (CI видит только коммит)", file=sys.stderr)

    work = Path(tempfile.mkdtemp(prefix="af-ci-local-"))
    clone, home = work / "repo", work / "home"
    home.mkdir()
    try:
        # Ровно коммит HEAD, глубина 1 — и для worktree, и для detached HEAD
        # (clone --depth взял бы HEAD основного клона): fetch по SHA через
        # upload-pack с allowAnySHA1InWant (только на время этого fetch).
        prep = [
            ("init", lambda: _git(work, "init", "-q", str(clone))),
            ("fetch", lambda: _git(
                clone, "fetch", "-q", "--depth", "1", "--upload-pack",
                "git -c uploadpack.allowAnySHA1InWant=true upload-pack",
                repo.as_uri(), sha)),
            ("checkout", lambda: _git(clone, "checkout", "-q", "FETCH_HEAD")),
        ]
        for name, step in prep:
            done = step()
            if done.returncode != 0:
                print(f"ci_local: {name} {sha[:12]} не удался: "
                      f"{done.stderr.strip()}", file=sys.stderr)
                return 2
        env = ci_env(home)
        print(f"ci_local: {sha[:12]} клон глубины 1 {clone}, HOME={home}")

        steps = [
            ("pytest", [sys.executable, "-m", "pytest", "tests/", "-q",
                        *args.pytest_args]),
            ("flow_check", [sys.executable, "scripts/flow_check.py", "."]),
        ]
        failed = []
        for name, cmd in steps:
            print(f"\n== {name}: {' '.join(cmd[1:])}", flush=True)
            rc = subprocess.run(cmd, cwd=clone, env=env).returncode
            if rc != 0:
                failed.append(f"{name} (rc={rc})")
        print("\nci_local: " + ("FAIL — " + ", ".join(failed) if failed
                                else "PASS — pytest и flow_check зеленые"))
        return 1 if failed else 0
    finally:
        if args.keep:
            print(f"ci_local: каталог сохранен: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
