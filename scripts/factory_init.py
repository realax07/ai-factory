#!/usr/bin/env python3
"""factory_init.py — развертывание конвейера AI Factory в произвольный проект (E15).

Копирует в целевой репозиторий обязательный минимум конвейера, параметризует
под проект и прогоняет post-init ворота (flow_check на пустом проекте = OK).

Usage:
  python3 ~/ai-factory/scripts/factory_init.py --target /path/to/repo --name "My Project" [--force]

Что устанавливается:
  scripts/flow_check.py, scripts/pr_validate.py, scripts/session_worktree.sh,
  scripts/codegraph.py, scripts/smoke_static.py, scripts/session_archive.py
  contracts/artifact_contract.md, templates/constitution.template.md,
  templates/task_delegation.md, .github/workflows/flow.yml,
  openspec/ (скелет specs/ + changes/archive/), test-model/ (checklists/new/reviews/approved/bugs),
  architecture/ (пустая, для map.md архитектора)

Промпты ролей копируются в <target>/agents/ — фабрика самодостаточна после установки.
Каждый промпт получает шапку-версию (yaml-комментарий с sha эталона); при наличии
~/ai-factory на машине flow_check предупреждает о рассинхроне (WARNING).

Post-init ворота: flow_check <target> должен завершиться exit 0.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent

COPY_FILES = [
    "scripts/flow_check.py",
    "scripts/pr_validate.py",
    "scripts/codegraph.py",
    "scripts/smoke_static.py",
    "scripts/session_archive.py",
    "scripts/session_worktree.sh",
    "contracts/artifact_contract.md",
    "templates/constitution.template.md",
    "templates/task_delegation.md",
    ".github/workflows/flow.yml",
]

MKDIRS = [
    "openspec/specs",
    "openspec/changes/archive",
    "test-model/checklists",
    "test-model/new",
    "test-model/reviews",
    "test-model/approved",
    "test-model/bugs",
    "architecture",
    "docs/ba",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="путь к целевому git-репозиторию")
    ap.add_argument("--name", required=True, help="имя проекта (для constitution)")
    ap.add_argument("--force", action="store_true", help="перезаписывать существующие файлы")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not (target / ".git").is_dir():
        print(f"FACTORY-INIT ERROR: {target} не git-репозиторий (init git вручную)")
        return 2

    # 1. Каталоги
    for d in MKDIRS:
        (target / d).mkdir(parents=True, exist_ok=True)
    print(f"  каталоги: {len(MKDIRS)} созданы/подтверждены")

    # 2. Файлы конвейера
    copied, skipped = 0, 0
    for rel in COPY_FILES:
        src = FACTORY / rel
        dst = target / rel
        if dst.exists() and not args.force:
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    print(f"  файлы: {copied} скопировано, {skipped} уже были (--force для перезаписи)")

    # 2b. Промпты ролей (в проект — самодостаточность установки) + README реестра
    import hashlib
    agents_copied = 0
    agents_dir = target / "agents"
    agents_dir.mkdir(exist_ok=True)
    for src in sorted((FACTORY / "agents").glob("*.md")):
        dst = agents_dir / src.name
        if dst.exists() and not args.force:
            continue
        text = src.read_text(encoding="utf-8")
        sha = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
        header = f"<!-- factory-version: {sha} -->\n\n"
        dst.write_text(header + text, encoding="utf-8")
        agents_copied += 1
    print(f"  промпты ролей: {agents_copied} в agents/ (версия = sha эталона в шапке)")

    # 3. Constitution из шаблона (если нет)
    constitution = target / "CONSTITUTION.md"
    if not constitution.exists() or args.force:
        tpl = (FACTORY / "templates/constitution.template.md").read_text(encoding="utf-8")
        constitution.write_text(tpl.replace("<ИМЯ ПРОЕКТА>", args.name), encoding="utf-8")
        print(f"  CONSTITUTION.md создан из шаблона (name={args.name})")
    else:
        print("  CONSTITUTION.md уже существует — не тронут")

    # 4. Проверка среды
    ok = True
    for cmd in ("python3 --version", "git --version"):
        r = subprocess.run(cmd.split(), capture_output=True, text=True)
        print(f"  {cmd}: {r.stdout.strip() or r.stderr.strip()}")
    r = subprocess.run(["openspec", "--version"], capture_output=True, text=True)
    if r.returncode != 0:
        print("  openspec CLI: НЕ найден (npm i -g @openspec/cli) — change-пакеты не валидируются")
        ok = False
    else:
        print(f"  openspec CLI: {r.stdout.strip()}")

    # 5. Post-init ворота: flow_check = OK на пустом проекте
    r = subprocess.run(["python3", str(FACTORY / "scripts/flow_check.py"), str(target)],
                       capture_output=True, text=True)
    print(f"  post-init flow_check: {r.stdout.strip()} (exit {r.returncode})")
    if r.returncode != 0:
        ok = False

    print(f"\nFACTORY-INIT {'OK' if ok else 'ЗАВЕРШЕН С ПРЕДУПРЕЖДЕНИЯМИ'}: {target}")
    print("Дальше: заполните CONSTITUTION.md принципами проекта; первый change-пакет — по контракту 2.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
