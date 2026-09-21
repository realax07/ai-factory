#!/usr/bin/env python3
"""pr_validate.py — валидатор артефактов по трассировочному ID (I3+I4, блок I).

Запускается:
  1. Локально: python3 scripts/pr_validate.py <repo> --id BUG-001 [--type bug|change|chore]
  2. GitHub Action на PR: парсит ID из title/body PR, валидирует наличие
     обязательных артефактов по контрактам artifact_contract.md.

Маркер ID обязателен в title/body PR: [BUG-NNN] | [change-id] | [chore]
Каждый тип влечет свой набор обязательных артефактов (см. FLOWS ниже).

Exit 0 — все артефакты на месте; exit 1 — список отсутствующих.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

# --- Наборы обязательных артефактов по типам (контракты) ---

def check_bug(repo: Path, num: str) -> list[str]:
    """Флоу 2: баг-репорт обязателен; после мержа — статус CLOSED."""
    missing = []
    digits = re.sub(r"^BUG-", "", num)  # принимаем и "BUG-001", и "001"
    bugs = list((repo / "test-model" / "bugs").glob(f"BUG-{digits}-*.md")) if (repo / "test-model" / "bugs").is_dir() else []
    if not bugs:
        return [f"test-model/bugs/BUG-{digits}-*.md: баг-репорт отсутствует (контракт 6/правило 7)"]
    text = bugs[0].read_text(encoding="utf-8", errors="replace")
    # На момент PR статус может быть открыт; CLOSED требуется после мержа (проверяет отдельно post-merge job)
    if "Статус" not in text and "CLOSED" not in text:
        missing.append(f"{bugs[0].name}: нет раздела «Статус»")
    return missing


def check_change(repo: Path, change_id: str) -> list[str]:
    """Флоу 1: change-пакет + QA-артефакты (контракты 2, 4, 5, 6, 7)."""
    missing = []
    pkg = repo / "openspec" / "changes" / change_id
    if not pkg.is_dir():
        return [f"openspec/changes/{change_id}/: change-пакет отсутствует (контракт 2)"]
    for req_file in ("proposal.md", "design.md", "tasks.md"):
        if not (pkg / req_file).is_file():
            missing.append(f"openspec/changes/{change_id}/{req_file}: отсутствует (контракт 2)")
    if not (pkg / "specs").is_dir() or not any((pkg / "specs").rglob("spec.md")):
        missing.append(f"openspec/changes/{change_id}/specs/: нет дельт (контракт 2)")

    # Impact-анализ (H5) — при MODIFIED/REMOVED дельтах обязателен
    has_modified = False
    for sf in (pkg / "specs").rglob("spec.md") if (pkg / "specs").is_dir() else []:
        if re.search(r"^##\s*(MODIFIED|REMOVED)", sf.read_text(encoding="utf-8", errors="replace"), re.M):
            has_modified = True
            break
    impact = repo / "test-model" / "impact" / f"{change_id}.md"
    if has_modified and not impact.is_file():
        missing.append(f"test-model/impact/{change_id}.md: нет impact-анализа при MODIFIED/REMOVED дельтах (H5)")

    # Чеклист (контракт 4)
    cl = repo / "test-model" / "checklists" / f"{change_id}.md"
    if not cl.is_file():
        missing.append(f"test-model/checklists/{change_id}.md: чеклист отсутствует (контракт 4)")

    # Кейсы: approved обязательны (контракт 6); new допустим только если PR не финальный
    appr = repo / "test-model" / "approved" / change_id
    if not appr.is_dir() or not any(appr.glob("*.md")):
        new = repo / "test-model" / "new" / change_id
        if new.is_dir() and any(new.glob("*.md")):
            missing.append(
                f"test-model/approved/{change_id}/: кейсы не перенесены из new/ — ревью не завершено (контракт 5/6)"
            )
        else:
            missing.append(f"test-model/approved/{change_id}/: approved-кейсы отсутствуют (контракт 6)")

    # Ревью-файл с вердиктом (контракт 5)
    rev_dir = repo / "test-model" / "reviews" / change_id
    if not rev_dir.is_dir() or not any(rev_dir.glob("review-*.md")):
        missing.append(f"test-model/reviews/{change_id}/: нет review-файла (контракт 5)")

    # Тесты: хотя бы один TC-ID change в tests/ (контракт 6, трассировка)
    tests_root = repo / "tests"
    tc_prefix = "TC-" + change_id.split("-")[0].upper()
    found_test = False
    if tests_root.is_dir():
        for tf in tests_root.rglob("test_*.py"):
            if re.search(rf"{re.escape(change_id)}|{tc_prefix}", tf.read_text(encoding="utf-8", errors="replace")):
                found_test = True
                break
    if not found_test:
        missing.append(
            f"tests/: не найдено тестов с трассировкой {change_id} / {tc_prefix}-NNN (контракт 6)"
        )
    return missing


def check_chore(repo: Path, marker: str) -> list[str]:
    """Флоу 4: обслуживание — минимальный набор, спека не меняется."""
    # Запрет: chore не имеет права менять спеки (изменение as is только через change)
    changed_specs = os.environ.get("PR_CHANGED_SPECS", "")
    if changed_specs.strip() in ("1", "true"):
        return [
            "PR помечен [chore], но содержит изменения openspec/ — изменение as is только через change-пакет (контракт 7)"
        ]
    return []


FLOWS = {
    "bug": check_bug,
    "change": check_change,
    "chore": check_chore,
}

MARKER_RE = re.compile(r"\[(BUG-\d+|[a-z0-9]+(?:-[a-z0-9]+)+|\bchore)\]")


def parse_id(text: str) -> tuple[str, str] | None:
    """Возвращает (тип, id) из маркера в тексте PR."""
    m = re.search(r"\[(BUG-\d+)\]", text)
    if m:
        return "bug", m.group(1)
    m = re.search(r"\[chore\]", text, re.I)
    if m:
        return "chore", "chore"
    m = re.search(r"\[([a-z0-9]+(?:-[a-z0-9]+)+)\]", text)
    if m and "-" in m.group(1):
        return "change", m.group(1)
    return None


def fetch_pr_info() -> tuple[str, str] | None:
    """В CI (GitHub Action): событие pull_request — читает body/title из GITHUB_EVENT_PATH."""
    ev = os.environ.get("GITHUB_EVENT_PATH")
    if not ev or not Path(ev).is_file():
        return None
    d = json.loads(Path(ev).read_text(encoding="utf-8"))
    pr = d.get("pull_request") or {}
    title = pr.get("title", "")
    body = pr.get("body") or ""
    return title + "\n" + body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".", help="корень репозитория проекта")
    ap.add_argument("--id", help="трассировочный ID (BUG-001 / change-id / chore)")
    ap.add_argument("--type", choices=list(FLOWS), help="тип флоу (иначе выводится из ID)")
    args = ap.parse_args()

    marker_text = f"[{args.id}]" if args.id else ""
    if not marker_text:
        pr_text = fetch_pr_info()
        if pr_text:
            marker_text = pr_text
        else:
            print("pr_validate: не указан --id и нет GITHUB_EVENT_PATH")
            return 1

    parsed = parse_id(marker_text)
    if not parsed:
        print(
            "pr_validate: маркер ID не найден. Обязателен в title/body PR: "
            "[BUG-NNN] (баг-фикс) / [change-id] (функционал) / [chore] (обслуживание). Блок I."
        )
        return 1

    flow_type, ident = parsed
    if args.type:
        flow_type = args.type

    repo = Path(args.repo).resolve()
    missing = FLOWS[flow_type](repo, ident)

    if missing:
        print(f"PR-VALIDATE FAIL ({flow_type}:{ident}): отсутствуют артефакты по контрактам:")
        for m in missing:
            print(f"  - {m}")
        return 1
    print(f"PR-VALIDATE OK ({flow_type}:{ident}): обязательные артефакты на месте")
    return 0


if __name__ == "__main__":
    sys.exit(main())
