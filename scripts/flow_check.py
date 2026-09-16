#!/usr/bin/env python3
"""flow_check.py — детерминированная проверка порядка артефактов конвейера.

State machine по файлам репозитория: каждый артефакт этапа имеет предков,
без которых он запрещен. Проверка не зависит от дисциплины агента:
нарушение флоу = ненулевой exit code.

Usage: python3 scripts/flow_check.py <path-to-repo>
"""
import re
import sys
from pathlib import Path

CHANGE_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)+$")  # kebab-case, >= 2 слов
TC_REF = re.compile(r"TC-[a-z0-9]+-\d{3}")


def errs(*msg):
    for m in msg:
        print(f"FLOW-ERROR: {m}")
    return len(msg)


def check(repo: Path) -> int:
    errors = 0
    openspec = repo / "openspec"
    tm = repo / "test-model"

    # --- Этап 2: change-пакет требует requirements.md (контракт 1) ---
    req = repo / "requirements.md"
    active_changes = []
    ch_dir = openspec / "changes"
    if ch_dir.is_dir():
        for d in sorted(p for p in ch_dir.iterdir() if p.is_dir()):
            if d.name == "archive":
                continue
            active_changes.append(d)
            if not req.is_file():
                errors += errs(
                    f"openspec/changes/{d.name}/: change-пакет без requirements.md (контракт 1)"
                )
            if CHANGE_ID.match(d.name) is None:
                errors += errs(
                    f"openspec/changes/{d.name}: change-id не в kebab-case из >=2 слов"
                )
            for must in ("proposal.md", "design.md", "tasks.md"):
                if not (d / must).is_file():
                    errors += errs(
                        f"openspec/changes/{d.name}/: отсутствует {must} (контракт 2)"
                    )
            specs = d / "specs"
            if specs.is_dir() and not any(specs.rglob("spec.md")):
                errors += errs(
                    f"openspec/changes/{d.name}/: нет дельт specs/*/spec.md (контракт 2)"
                )

    # --- sdd.md: активный change требует SDD (контракт 2) ---
    sdd = repo / "sdd.md"
    if active_changes and not sdd.is_file():
        errors += errs("активный change-пакет без sdd.md (контракт 2)")

    # --- Спеки: каждый Requirement должен иметь сценарий ---
    specs_dir = openspec / "specs"
    if specs_dir.is_dir():
        for sf in sorted(specs_dir.rglob("spec.md")):
            text = sf.read_text(encoding="utf-8")
            n_req = len(re.findall(r"^### Requirement:", text, re.M))
            n_scn = len(re.findall(r"^#### Scenario:", text, re.M))
            if n_req and n_scn == 0:
                errors += errs(f"{sf.relative_to(repo)}: {n_req} Requirement без Scenario")

    # --- Этап QA: чеклист требует спеку/дельты (контракт 3/4) ---
    checklists = list((tm / "checklists").glob("*.md")) if (tm / "checklists").is_dir() else []
    has_spec_source = bool(active_changes) or (
        specs_dir.is_dir() and any(specs_dir.rglob("spec.md"))
    )
    for cl in checklists:
        if not has_spec_source:
            errors += errs(f"{cl.relative_to(repo)}: чеклист без спеки (контракт 3)")
            continue
        text = cl.read_text(encoding="utf-8")
        rows = [ln for ln in text.splitlines() if re.match(r"^\|\s*CHK-", ln)]
        if not rows:
            errors += errs(f"{cl.relative_to(repo)}: нет строк чеклиста CHK-*")
        bad_src = [ln for ln in rows if not re.search(r"FR-\d+|NFR-\d+|Requirement", ln)]
        if bad_src:
            errors += errs(
                f"{cl.relative_to(repo)}: {len(bad_src)} CHK-строк без источника FR/NFR (rule 6)"
            )
        if "Дефекты спеки" not in text:
            errors += errs(f"{cl.relative_to(repo)}: нет раздела «Дефекты спеки»")

    # --- Кейсы new/: требуют чеклист (контракт 4) и CHK-ссылки ---
    new_dir = tm / "new"
    case_files = list(new_dir.rglob("*.md")) if new_dir.is_dir() else []
    cl_ids = {cl.stem for cl in checklists}
    for cf in case_files:
        if cf.parent.name not in cl_ids:
            errors += errs(
                f"{cf.relative_to(repo)}: кейсы без чеклиста test-model/checklists/{cf.parent.name}.md (контракт 4)"
            )
        text = cf.read_text(encoding="utf-8")
        tcs = re.findall(r"^##\s+(TC-[a-z0-9]+-\d{3})", text, re.M)
        if not tcs:
            errors += errs(f"{cf.relative_to(repo)}: нет кейсов TC-***-NNN")
        orphan = [tc for tc in tcs if f"[{tc}]" not in text and "CHK-" not in text]
        if orphan:
            errors += errs(f"{cf.relative_to(repo)}: кейсы без CHK-трассировки (rule 6)")

    # --- approved/: требуют review с вердиктом «одобрить» (контракт 5/6) ---
    rev_dir = tm / "reviews"
    appr_dir = tm / "approved"
    reviews = list(rev_dir.rglob("review-*.md")) if rev_dir.is_dir() else []
    approved_by_change = {}
    if appr_dir.is_dir():
        for d in sorted(p for p in appr_dir.iterdir() if p.is_dir()):
            approved_by_change[d.name] = list(d.rglob("*.md"))
    for change, files in approved_by_change.items():
        if not files:
            errors += errs(f"test-model/approved/{change}/: пустая директория")
            continue
        it_reviews = sorted(rev_dir.rglob(f"review-*.md")) if rev_dir.is_dir() else []
        it_ok = any(
            change in r.read_text(encoding="utf-8")
            and re.search(r"одобрить", r.read_text(encoding="utf-8"), re.I)
            for r in it_reviews
        )
        if not it_ok:
            errors += errs(
                f"test-model/approved/{change}/: нет review с вердиктом «одобрить» (контракт 5)"
            )

    # --- Автотесты: только по approved + трассировка TC (контракт 6) ---
    tests_dir = repo / "tests"
    if tests_dir.is_dir():
        test_files = [p for p in tests_dir.rglob("test_*.py")]
        if test_files and not any(approved_by_change.values()):
            errors += errs("tests/: автотесты без approved-кейсов (контракт 6)")
        for tf in test_files:
            text = tf.read_text(encoding="utf-8", errors="replace")
            if re.search(r"\btime\.sleep\(", text):
                errors += errs(f"{tf.relative_to(repo)}: time.sleep запрещен (спека qa-pipeline)")
            doc_tests = re.findall(r'def (test_\w+)', text)
            if doc_tests and not TC_REF.search(text):
                errors += errs(f"{tf.relative_to(repo)}: тесты без TC-трассировки в docstring (rule 6)")

    # --- bugs/: append-only структура ---
    bugs = tm / "bugs"
    if bugs.is_dir():
        for bf in sorted(bugs.glob("*.md")):
            if not re.match(r"^BUG-\d{3}", bf.stem):
                errors += errs(f"{bf.relative_to(repo)}: баг-репорт не BUG-NNN")

    if errors == 0:
        print("flow_check: OK — порядок артефактов соответствует флоу")
    else:
        print(f"flow_check: {errors} ошибок(и)")
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    repo = Path(sys.argv[1]).resolve()
    if not repo.is_dir():
        print(f"FLOW-ERROR: репозиторий не найден: {repo}")
        sys.exit(2)
    sys.exit(check(repo))
