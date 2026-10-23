#!/usr/bin/env python3
"""check_mirrors.py — sha256-сверка копий фабричных скриптов в проектах с
эталоном фабрики (аудит Н22).

Инцидент-класс: копии скриптов расставляет factory_init (15 файлов/проект);
фикс в фабрике может тихо не доехать до копий (осознано в J34, механизма
не было). Скрипт сравнивает sha256 указанных файлов в каждом проекте с
эталоном и печатает JSON-отчет; расхождение/отсутствие копии — статус
mismatch/missing (exit 1), совпадение — match (exit 0).

Модуль автономен (stdlib only), существующие скрипты не трогает.
Вызывается отдельно (CI-джоба/крон/ручной запуск).

Usage:
    python3 scripts/check_mirrors.py --project /path/proj1 \
        --project /path/proj2 [--factory /path/factory] \
        [--file flow_check.py --file pr_validate.py --file impact_rules.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_FILES = ("flow_check.py", "pr_validate.py", "impact_rules.json")
FACTORY_REL_SCRIPTS = "scripts"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def default_factory() -> Path:
    """Эталон фабрики = репо, в котором лежит сам скрипт (scripts/..)."""
    return Path(__file__).resolve().parent.parent


def check_project(project: Path, factory: Path,
                  files: list[str]) -> dict:
    """Отчет по одному проекту: sha256 копии vs эталон.

    Ранжирование статуса проекта: error (mismatch/нет эталона) >
    missing (копии нет) > match — мисматч хуже отсутствия: расхождение
    означает, что проект едет на протухшей версии скрипта.
    """
    rank = {"match": 0, "missing": 1, "mismatch": 2, "no_reference": 2}
    entries = []
    worst = "match"
    for name in files:
        ref = factory / FACTORY_REL_SCRIPTS / name
        copy = project / FACTORY_REL_SCRIPTS / name
        entry: dict = {"file": name,
                       "reference": str(ref),
                       "copy": str(copy)}
        if not ref.is_file():
            entry["status"] = "no_reference"
        elif not copy.is_file():
            entry["status"] = "missing"
            entry["reference_sha256"] = sha256_file(ref)
        else:
            ref_sha = sha256_file(ref)
            copy_sha = sha256_file(copy)
            entry["reference_sha256"] = ref_sha
            entry["copy_sha256"] = copy_sha
            entry["status"] = "match" if ref_sha == copy_sha else "mismatch"
        if rank[entry["status"]] > rank[worst]:
            worst = entry["status"]
        entries.append(entry)
    return {"project": str(project), "files": entries, "status": worst}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_mirrors",
        description="sha256 копий скриптов проектов vs эталон фабрики (Н22)")
    parser.add_argument("--project", action="append", required=True,
                        help="путь к проекту (опция многократная)")
    parser.add_argument("--factory", default=None,
                        help="эталон фабрики (default: репо скрипта)")
    parser.add_argument("--file", action="append", default=None,
                        help="имя файла для сверки (default: "
                             + ", ".join(DEFAULT_FILES) + ")")
    args = parser.parse_args(argv)

    factory = Path(args.factory) if args.factory else default_factory()
    files = args.file if args.file else list(DEFAULT_FILES)
    reports = [check_project(Path(p), factory, files)
               for p in args.project]
    rank = {"match": 0, "missing": 1, "mismatch": 2, "no_reference": 2}
    overall = max((r["status"] for r in reports),
                  key=lambda s: rank[s]) if reports else "match"
    print(json.dumps({"check": "mirrors", "factory": str(factory),
                      "status": overall, "projects": reports},
                     ensure_ascii=False, indent=2))
    return 0 if overall == "match" else 1


if __name__ == "__main__":
    sys.exit(main())
