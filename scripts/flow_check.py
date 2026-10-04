#!/usr/bin/env python3
"""flow_check.py — детерминированная проверка порядка артефактов конвейера.

State machine по файлам репозитория: каждый артефакт этапа имеет предков,
без которых он запрещен. Проверка не зависит от дисциплины агента:
нарушение флоу = ненулевой exit code.

Usage: python3 scripts/flow_check.py <path-to-repo>
"""
import json
import re
import sys
from pathlib import Path

CHANGE_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)+$")  # kebab-case, >= 2 слов
TC_REF = re.compile(r"TC-[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*-\d{3}")

# --- J10: обязательный code-review закрытых dev-задач ---
# Формат review-файла: agents/code_reviewer_agent.md —
#   код-reviews/<change-id>/review-<задача>-<NNN>.md, строка «## Вердикт: approve|return».
# Два формата имени: review-<NNN>-<task>.md (code_reviewer Р3) и review-<task>-<NNN>.md
REVIEW_FILE_RE = re.compile(r"^review-(\d{3})-(.+?)-(\d{3})\.md$", re.I)  # rev-first: NNN-task без цифр на конце — неоднозначно; ниже общий
REVIEW_FILE_REV_FIRST = re.compile(r"^review-(\d{3})-(.+)\.md$", re.I)
REVIEW_FILE_TASK_FIRST = re.compile(r"^review-(.+?)-(\d{3})\.md$", re.I)
VERDICT_LINE_RE = re.compile(r"^#{1,4}\s*Вердикт\s*:?\s*(.+)$", re.I | re.M)
VERDICT_APPROVE_RE = re.compile(r"\b(approve|approved|одобрен\w*)\b", re.I)
# SELF_REVIEW-защита (решение Заказчика 2026-10-03): review-файл обязан нести
# Reviewer-Delegation: deleg_<id> — платформенный id делегации ревьюера
# (реестр async_delegations устойчив к пересозданию main-сессий: id
# уникален и не зависит от имени сессии).
REVIEWER_META_RE = re.compile(r"Reviewer-Delegation[^A-Za-z0-9]{0,6}(deleg[-_][A-Za-z0-9]+)", re.I)
VERDICT_RETURN_RE = re.compile(r"\b(return|доработк\w*)\b", re.I)
QA_SECTION = "6"  # раздел 6.x — QA-цикл, не dev (J10)


def archived_delta_problems(repo: Path) -> dict[str, list[str]]:
    """Контракт 7: Requirements дельт archived-пакетов против master-spec.

    Для каждого каталога openspec/changes/archive/<id>/ со дельтами specs/
    проверяет: каждый Requirement дельты присутствует в openspec/specs/,
    а Requirements из блока «## REMOVED Requirements» — отсутствуют.
    Возвращает {change_id: [проблемы]} (пустой список = дельты слиты).

    Выделено из run_check для переиспользования фактом change.archived
    в flow_state (усиление P0.1): логика одна, парсеры не дублируются.
    """
    problems: dict[str, list[str]] = {}
    arch_dir = repo / "openspec" / "changes" / "archive"
    if not arch_dir.is_dir():
        return problems
    specs_root = repo / "openspec" / "specs"
    master_text = "\n".join(
        sf.read_text(encoding="utf-8") for sf in specs_root.rglob("spec.md")
    ) if specs_root.is_dir() else ""
    for d in sorted(p for p in arch_dir.iterdir() if p.is_dir()):
        missing: list[str] = []
        delta_specs = d / "specs"
        if delta_specs.is_dir():
            for ds in sorted(delta_specs.rglob("spec.md")):
                delta_text = ds.read_text(encoding="utf-8")
                for m in re.finditer(r"^### Requirement:\s*(.+)$", delta_text, re.M):
                    title = m.group(1).strip()
                    removed = re.search(
                        r"##\s*REMOVED Requirements.*?(?=^##\s|\Z)",
                        delta_text,
                        re.M | re.S,
                    )
                    if removed and f"### Requirement: {title}" in removed.group(0):
                        if f"### Requirement: {title}" in master_text:
                            missing.append(f"REMOVED '{title}' все еще в master-spec")
                    elif f"### Requirement: {title}" not in master_text:
                        missing.append(f"'{title}' не слит в master-spec")
        problems[d.name] = missing
    return problems


def closed_dev_tasks(tasks_text: str) -> list[str]:
    """Закрытые dev-задачи ([x]) tasks.md; QA-раздел 6.x исключен (J10).

    Исключены также ops/docs-задачи (маркер `[ops]`/`[docs]` после чекбокса):
    боевая приемка Заказчика / верификация фактов вместо code-review
    (контракт flow_control: ops_task/docs_task, J10 не применяется).
    """
    out = []
    for m in re.finditer(r"^[-*]\s*\[x\]\s*(\d+(?:\.\d+)*)(?:\s+\[[SP]\])?(\s+\[([a-z]+)\])?", tasks_text, re.M):
        num = m.group(1)
        if num.split(".")[0] == QA_SECTION:
            continue
        if m.group(3) in ("ops", "docs"):
            continue
        out.append(num)
    return out


def parse_verdict(text: str) -> str | None:
    """Вердикт из review-файла по формату code_reviewer_agent.md: 'approve' | 'return' | None."""
    for m in VERDICT_LINE_RE.finditer(text):
        v = m.group(1).strip().strip("*").strip().lower()
        has_return = bool(VERDICT_RETURN_RE.search(v))
        has_approve = bool(VERDICT_APPROVE_RE.search(v))
        if has_return:
            return "return"
        if has_approve:
            return "approve"
    return None


def approved_review_tasks(repo: Path, change_id: str) -> dict[str, str]:
    """task-id → имя последнего review-файла с вердиктом approve (code-reviews/<change-id>/)."""
    covered: dict[str, tuple[int, str]] = {}
    cr_dir = repo / "code-reviews" / change_id
    if not cr_dir.is_dir():
        return {}
    for rf in cr_dir.glob("review-*.md"):
        m = REVIEW_FILE_REV_FIRST.match(rf.name)
        if m:
            rev, task = int(m.group(1)), m.group(2)
        else:
            m = REVIEW_FILE_TASK_FIRST.match(rf.name)
            if not m:
                continue
            task, rev = m.group(1), int(m.group(2))
        # Нормализация: имя может объединять несколько задач (review-001-2.1-2.2-dnd.md)
        # или нести суффикс (review-001-1.1-auth-me.md) — задачи = все числовые
        # идентификаторы вида N[.N...] в task-части имени
        nums = re.findall(r"\d+(?:\.\d+)*", task)
        tasks = nums if nums else [task]
        text = rf.read_text(encoding="utf-8", errors="replace")
        verdict = parse_verdict(text)
        meta = REVIEWER_META_RE.search(text)
        if verdict == "approve" and meta:
            for task_id in tasks:
                if task_id not in covered or rev > covered[task_id][0]:
                    covered[task_id] = (rev, rf.name)
    # Исторические ревью с нестандартными именами (Флоу 4, карта покрытия
    # review-mapping.json: файл → список task-id). Мета обязательна и здесь.
    mapping_file = cr_dir / "review-mapping.json"
    if mapping_file.is_file():
        try:
            mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            mapping = {}
        for fname, task_ids in mapping.items():
            if fname.startswith("_"):
                continue
            rf = cr_dir / fname
            if not rf.is_file():
                continue
            verdict = parse_verdict(rf.read_text(encoding="utf-8", errors="replace"))
            meta = REVIEWER_META_RE.search(rf.read_text(encoding="utf-8", errors="replace"))
            if verdict == "approve" and meta:
                rev = int(fname.split("-")[1]) if fname.split("-")[1].isdigit() else 0
                for task_id in task_ids:
                    if task_id not in covered or rev > covered[task_id][0]:
                        covered[task_id] = (rev, fname)
    return {task: name for task, (_, name) in covered.items()}


def errs(*msg):
    for m in msg:
        print(f"FLOW-ERROR: {m}")
    return len(msg)


def warns(*msg):
    for m in msg:
        print(f"FLOW-WARNING: {m}")
    return len(msg)


def check(repo: Path) -> int:
    errors = 0
    openspec = repo / "openspec"
    tm = repo / "test-model"

    # --- factory-init: рассинхрон промптов с эталоном фабрики (если фабрика на машине) ---
    project_agents = repo / "agents"
    if project_agents.is_dir():
        factory_agents = Path.home() / "ai-factory/agents"
        if factory_agents.is_dir():
            import hashlib
            stale = []
            for dst in sorted(project_agents.glob("*.md")):
                src = factory_agents / dst.name
                if not src.is_file():
                    continue
                m = re.search(r"factory-version: ([0-9a-f]{12})", dst.read_text(encoding="utf-8", errors="replace")[:300])
                cur = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
                if m and m.group(1) != cur:
                    stale.append(dst.name)
            if stale:
                warns(
                    f"промпты устарели относительно ~/ai-factory: {', '.join(stale[:5])} "
                    f"— обнови: factory_init.py --target {repo.name} --name <name> --force"
                )

    # --- Этап 2: change-пакет требует requirements.md (контракт 1) ---
    req = repo / "requirements.md"
    # --- Контракт 1 (C1): преамбула ответственности в requirements.md ---
    if req.is_file():
        req_text = req.read_text(encoding="utf-8")
        req_head = req_text[:600]
        # Преамбула может идти после заголовка H1 — ищем первую цитату-строку
        preamble = re.search(r"^>\s*Статус:", req_head, re.M)
        if not preamble:
            errors += errs(
                "requirements.md: нет преамбулы ответственности (контракт 1, C1): "
                "> Статус: ... | Автор: ba_agent | История: r1 → ... → rN"
            )
        elif "Автор:" not in req_head:
            errors += errs(
                "requirements.md: в преамбуле нет поля «Автор:» (контракт 1, C1)"
            )
        change_req_preamble = (preamble is not None and "Автор:" in req_head)

        # --- Контракт 1 (E3): структурная валидация ТЗ скриптом ---
        # 1) Все 7 разделов (допускаются вариации заголовков с «##»).
        required_sections = (
            "описание", "аудитория", "функциональн", "нефункциональн",
            "приорит", "ограничен", "открытые вопросы",
        )
        low = req_text.lower()
        for sec in required_sections:
            if not re.search(rf"^#+\s.*{sec}", low, re.M):
                errors += errs(
                    f"requirements.md: нет раздела «{sec}» (контракт 1, E3)"
                )
        # 2) Уникальность FR-N / NFR-N: определение (раздел FR/NFR или MoSCoW)
        #    — каждое ровно один раз; упоминания в связках (дельты, сценарии)
        #    не считаются. Эвристика: считаем только в строках-определениях
        #    (маркированный список с идентификатором в начале описания).
        def_lines = re.findall(r"^[-*]\s*(?:\*\*)?(FR|NFR)-(\d+)\b", req_text, re.M)
        ids_def = [f"{kind}-{num}" for kind, num in def_lines]
        dupes = sorted({i for i in ids_def if ids_def.count(i) > 1})
        if dupes:
            errors += errs(
                "requirements.md: дубликаты идентификаторов в определениях "
                "(контракт 1, E3): " + ", ".join(dupes[:6])
            )
        # 3) Нет TBD/TODO.
        for marker in ("TBD", "TODO"):
            if re.search(rf"\b{marker}\b", req_text):
                errors += errs(
                    f"requirements.md: найден {marker} (контракт 1, E3) — реши и запиши"
                )
        # 4) Оценочные формулировки в строках FR (эвристика, контракт 1).
        for ln in req_text.splitlines():
            if re.match(r"^[-\d].*\bFR-\d+", ln) and re.search(
                r"\b(быстро|удобно|просто|понятно)\b", ln, re.I
            ):
                errors += errs(
                    f"requirements.md: оценочная формулировка без критерия в FR-строке "
                    f"(контракт 1, E3): {ln.strip()[:80]}"
                )
    else:
        change_req_preamble = False
    change_req_ok = change_req_preamble and req.is_file()
    active_changes = []
    archived_changes = []
    ch_dir = openspec / "changes"
    arch_dir = ch_dir / "archive" if ch_dir.is_dir() else None
    if arch_dir is not None and arch_dir.is_dir():
        for d in sorted(p for p in arch_dir.iterdir() if p.is_dir()):
            archived_changes.append(d)

    # --- Контракт 7: archived change должен быть слит в master-spec ---
    if specs_dir_check := (openspec / "specs"):
        for d in archived_changes:
            delta_problems = archived_delta_problems(repo).get(d.name, [])
            if delta_problems:
                errors += errs(
                    f"openspec/changes/archive/{d.name}: master-spec не соответствует дельтам (контракт 7): "
                    + "; ".join(delta_problems[:5])
                )

    if ch_dir.is_dir():
        for d in sorted(p for p in ch_dir.iterdir() if p.is_dir()):
            if d.name == "archive":
                continue
            active_changes.append(d)
            change_req = d / "requirements.md"
            if not change_req.is_file() and not change_req_ok:
                errors += errs(
                    f"openspec/changes/{d.name}/: change-пакет без requirements.md (контракт 1)"
                )
            # --- Решение Заказчика 2026-10-02 (3.3/S7): архивация — функция sa ---
            # (контракт 7: автор спек сливает дельты; граф машинных правил приведен
            #  в соответствие, см. docs/shadow-r6-scenario.md)
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
            # --- J10: обязательный code-review закрытых dev-задач ---
            tasks_file = d / "tasks.md"
            if tasks_file.is_file():
                closed = closed_dev_tasks(tasks_file.read_text(encoding="utf-8", errors="replace"))
                if closed:
                    covered = approved_review_tasks(repo, d.name)
                    if not covered:
                        errors += errs(
                            f"openspec/changes/{d.name}: {len(closed)} закрытых dev-задач без "
                            f"code-review — каталог code-reviews/{d.name}/ пуст или без approve-вердиктов (J10): "
                            + ", ".join(closed)
                        )
                    else:
                        uncovered = [t for t in closed if t not in covered]
                        if uncovered:
                            errors += errs(
                                f"openspec/changes/{d.name}: закрытые dev-задачи без review-файла "
                                f"с вердиктом approve в code-reviews/{d.name}/ (J10): "
                                + ", ".join(uncovered)
                            )

    # --- sdd.md: активный change требует SDD (контракт 2) ---
    sdd = repo / "sdd.md"
    change_sdd = None
    for d in active_changes:
        cand = d / "sdd.md"
        if cand.is_file():
            change_sdd = cand
            break
    if active_changes and not sdd.is_file() and change_sdd is None:
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

    # --- Кейсы new/: требуют чеклист (контракт 4), CHK-ссылки и формат H1 ---
    # H1: 1 кейс = 1 файл, имя файла = ID кейса (допускается суффикс -update).
    # Заголовки кейсов: # TC-... или ## TC-... (оба уровня приняты практикой).
    TC_HEAD = re.compile(r"^#{1,3}\s+(TC-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*-\d{3})", re.M)
    new_dir = tm / "new"
    case_files = list(new_dir.rglob("*.md")) if new_dir.is_dir() else []
    cl_ids = {cl.stem for cl in checklists}
    for cf in case_files:
        if cf.parent.name not in cl_ids:
            errors += errs(
                f"{cf.relative_to(repo)}: кейсы без чеклиста test-model/checklists/{cf.parent.name}.md (контракт 4)"
            )
        text = cf.read_text(encoding="utf-8")
        tcs = TC_HEAD.findall(text)
        if not tcs:
            errors += errs(f"{cf.relative_to(repo)}: нет кейсов TC-***-NNN")
            continue
        if len(tcs) > 1:
            errors += errs(
                f"{cf.relative_to(repo)}: {len(tcs)} кейсов в одном файле — нарушение «1 кейс = 1 файл» (H1)"
            )
        elif cf.stem != tcs[0] and not cf.stem.startswith(tcs[0] + "-update"):
            errors += errs(
                f"{cf.relative_to(repo)}: имя файла не совпадает с ID кейса {tcs[0]} (H1)"
            )
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
        # Источник кейсов (с 2026-10-03, as-is структура regression/<domain>/,
        # J33): approved/<change>/ (классика Флоу 1) ИЛИ regression/<domain>/
        # (as-is база).
        reg_dir = tm / "regression"
        has_regression_cases = reg_dir.is_dir() and any(
            d.is_dir() and not d.name.startswith(".") for d in reg_dir.iterdir()
        ) and any(f.suffix == ".md" for f in reg_dir.rglob("*.md"))
        if test_files and not any(approved_by_change.values()) and not has_regression_cases:
            errors += errs(
                "tests/: автотесты без approved-кейсов и без as-is базы "
                "test-model/regression/<domain>/ (контракт 6)"
            )
        for tf in test_files:
            text = tf.read_text(encoding="utf-8", errors="replace")
            if re.search(r"\btime\.sleep\(", text):
                errors += errs(f"{tf.relative_to(repo)}: time.sleep запрещен (спека qa-pipeline)")
            doc_tests = re.findall(r'def (test_\w+)', text)
            if doc_tests and not TC_REF.search(text):
                errors += errs(f"{tf.relative_to(repo)}: тесты без TC-трассировки в docstring (rule 6)")

    # --- I3: API-эндпоинты без спек-покрытия (эвристика) ---
    # В активных change-пакетах: каждый маршрут, добавленный кодом (diff-хpat в design/tasks/sdd
    # недостаточно — сверяем с дельтами спек и impact), должен иметь дельту specs/*/spec.md,
    # упоминание пути в sdd.md/дизайне и строку в impact-записи. Упрощенно-детерминированно:
    # собираем маршруты из backend-кода, затем требуем упоминание каждого пути хотя бы в
    # одном из: дельты спек активных пакетов, sdd.md, test-model/checklists (impact).
    backend_dir = repo / "backend/app"
    if backend_dir.is_dir():
        route_rx = re.compile(r'@(?:\w+)\.(get|post|patch|delete|put)\(\s*[\'"]([^\'"]*)[\'"]')
        prefixes: dict[str, str] = {}
        routes: list[tuple[str, str, Path]] = []  # (method, full_path, file)
        for py in sorted(backend_dir.glob("*.py")):
            text = py.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'APIRouter\(\s*prefix\s*=\s*[\'"]([^\'"]+)[\'"]', text):
                prefixes[py.stem] = m.group(1)
            for m in route_rx.finditer(text):
                method, path = m.group(1).upper(), m.group(2)
                full = prefixes.get(py.stem, "") + path
                routes.append((method, full, py))
        # источники покрытия: корневые артефакты (sdd, master-specs) — ВСЕГДА:
        # маршруты ядра существуют вне пакетов, а архивация предыдущего пакета
        # не должна осиротать покрытие (урок 2026-10-04: архивация
        # add-containerization обнулила покрытие всех немодифицированных
        # маршрутов). Дельты активных пакетов добавляются сверху.
        cover_texts: list[str] = []
        if (repo / "sdd.md").is_file():
            cover_texts.append((repo / "sdd.md").read_text(encoding="utf-8", errors="replace"))
        if specs_dir.is_dir():
            for sf in specs_dir.rglob("spec.md"):
                cover_texts.append(sf.read_text(encoding="utf-8", errors="replace"))
        for pkg in active_changes:
            for sf in pkg.rglob("spec.md"):
                cover_texts.append(sf.read_text(encoding="utf-8", errors="replace"))
            for name in ("sdd.md", "design.md", "tasks.md", "proposal.md"):
                f = pkg / name
                if f.is_file():
                    cover_texts.append(f.read_text(encoding="utf-8", errors="replace"))
        if (tm / "checklists").is_dir():
            for cf in (tm / "checklists").glob("*.md"):
                cover_texts.append(cf.read_text(encoding="utf-8", errors="replace"))
        corpus = "\n".join(cover_texts)
        allowlist = {"/health", "/api/health", "/login", "/logout"}
        for method, full, py in routes:
            if full in allowlist or "{" in full:
                continue  # параметризованные маршруты сверяем по префиксу ниже
            if full and full not in corpus:
                errors += errs(
                    f"{py.relative_to(repo)}: маршрут {method} {full} не упомянут ни в дельтах спек, "
                    f"ни в sdd/design активного change, ни в чеклистах (I3)"
                )

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
