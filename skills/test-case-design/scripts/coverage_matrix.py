#!/usr/bin/env python3
"""Матрица покрытия: сценарии спеки ↔ тест-кейсы (TC).

Скилл: test-case-design. Сопоставляет сценарии (заголовки «### Сценарий: …»
в спеках) с кейсами каталога test-model: кейс «покрывает» сценарий, если в
его файле встречается имя сценария или его идентификатор (SC/FR/NFR-N).
Вывод: сценарии без кейсов (пробелы) и кейсы-сироты (нет ссылок на спеку).

Usage:
    python coverage_matrix.py openspec/changes/add-wiki/ --cases test-model/new
    python coverage_matrix.py docs/ba/ --cases test-model/ --strict
"""
import argparse
import re
import sys
from pathlib import Path

SCEN_RE = re.compile(r"^#{2,4}\s*Сценарий[:\s]\s*(.+)$", re.MULTILINE)
TC_RE = re.compile(r"\bTC-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b")
REF_RE = re.compile(r"\b(?:SC|FR|NFR)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b")


def md_files(path: str) -> list[Path]:
    base = Path(path)
    if base.is_file():
        return [base]
    return sorted(base.rglob("*.md")) if base.is_dir() else []


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("specs", nargs="+", help="спеки (каталог или файлы)")
    ap.add_argument("--cases", default="test-model/new",
                    help="каталог кейсов (default: test-model/new)")
    ap.add_argument("--strict", action="store_true", help="пробелы = exit 2")
    args = ap.parse_args()

    # Сценарии: имя → источник
    scenarios: dict[str, str] = {}
    for spec in args.specs:
        for f in md_files(spec):
            for m in SCEN_RE.finditer(read(f)):
                scenarios.setdefault(m.group(1).strip(), str(f))

    # Кейсы: TC-ID → текст файла (поиск ссылки на сценарий ведем по тексту)
    tc_texts: dict[str, str] = {}
    tc_refs: dict[str, set[str]] = {}
    for f in md_files(args.cases):
        text = read(f)
        if not text:
            continue
        for tc in set(TC_RE.findall(text)):
            tc_texts.setdefault(tc, "")
            tc_texts[tc] += "\n" + text.lower()
            tc_refs.setdefault(tc, set()).update(REF_RE.findall(text))

    print(f"Сценариев в спеках: {len(scenarios)}; кейсов TC: {len(tc_texts)}")

    uncovered = []
    for name, src in sorted(scenarios.items()):
        key = name.lower()
        covered = any(key in body for body in tc_texts.values())
        if not covered:
            uncovered.append((name, src))

    orphans = sorted(tc for tc, refs in tc_refs.items() if not refs)

    if uncovered:
        print(f"\nБЕЗ КЕЙСОВ ({len(uncovered)}):")
        for name, src in uncovered:
            print(f"  - {name}  ({src})")
    else:
        print("\nВсе сценарии покрыты кейсами.")
    if orphans:
        tail = f" (+{len(orphans)-10})" if len(orphans) > 10 else ""
        print(f"\nКЕЙСЫ-СИРОТЫ (нет ссылки SC/FR/NFR): "
              f"{', '.join(orphans[:10])}{tail}")

    if uncovered and args.strict:
        return 2
    return 1 if uncovered else 0


if __name__ == "__main__":
    sys.exit(main())
