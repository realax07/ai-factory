"""remove-qa-checklist: контракты 3/4/5 flow_check после упразднения чеклистов.

- кейсы без чеклиста — ALLOW (не нарушение);
- кейс с трассировкой к Requirement/Scenario спеки — ALLOW;
- кейс без трассировки — дефект (контракт 4);
- существующие чеклисты не валидируются и не удаляются (append-only история).
"""
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_check  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


def make_repo(tmp_path: Path, name: str = "proj") -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)  # exist_ok: conftest J41-фикстура уже создает proj/
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "openspec" / "changes").mkdir(parents=True)
    (repo / "test-model").mkdir()
    spec = ("### Requirement: Виджет список\n"
            "#### Scenario: Пустой список\n"
            "- GIVEN нет данных\n- WHEN открыт экран\n- THEN пусто\n")
    (repo / "openspec" / "specs" / "widget" / "spec.md").parent.mkdir(parents=True)
    (repo / "openspec" / "specs" / "widget" / "spec.md").write_text(spec,
                                                                   encoding="utf-8")
    pkg = repo / "openspec" / "changes" / "add-widget"
    (pkg / "specs" / "widget").mkdir(parents=True)
    (pkg / "proposal.md").write_text("# p\n", encoding="utf-8")
    (pkg / "design.md").write_text("# d\n", encoding="utf-8")
    (pkg / "tasks.md").write_text("# t\n", encoding="utf-8")
    (pkg / "requirements.md").write_text("# r\n", encoding="utf-8")
    (pkg / "specs" / "widget" / "spec.md").write_text(spec, encoding="utf-8")
    (repo / "sdd.md").write_text("# SDD\n", encoding="utf-8")
    return repo


def write_case(repo: Path, body: str) -> None:
    d = repo / "test-model" / "new" / "add-widget"
    d.mkdir(parents=True, exist_ok=True)
    (d / "TC-WID-001.md").write_text(body, encoding="utf-8")


def run_flow_check(repo: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "flow_check.py"), str(repo)],
        capture_output=True, text=True)
    return proc.returncode, proc.stdout


def test_cases_without_checklist_ok(tmp_path):
    """Кейсы без чеклиста — ALLOW (remove-qa-checklist)."""
    repo = make_repo(tmp_path)
    write_case(
        repo,
        "# TC-WID-001 — пустой список\n\n"
        "Источник: Requirement: Виджет список\n"
        "Источник: Scenario: Пустой список (FR-1)\n"
        "\n## Шаги\n- открыть экран\n")
    code, out = run_flow_check(repo)
    assert code == 0, out
    assert "чеклист" not in out


def test_case_with_req_trace_ok_without_checklist(tmp_path):
    """Кейс с трассировкой к Req — ALLOW; исторический чеклист не мешает."""
    repo = make_repo(tmp_path)
    cl = repo / "test-model" / "checklists"
    cl.mkdir(parents=True)
    (cl / "add-widget.md").write_text(
        "| CHK-1 | старый пункт без раздела Дефекты |\n", encoding="utf-8")
    write_case(
        repo,
        "# TC-WID-001 — пустой список\n\n"
        "Requirement: Виджет список\nScenario: Пустой список\n")
    code, out = run_flow_check(repo)
    assert code == 0, out


def test_case_without_trace_is_defect(tmp_path):
    """Кейс без трассировки к спеке — дефект (контракт 4)."""
    repo = make_repo(tmp_path)
    write_case(
        repo,
        "# TC-WID-001 — пустой список\n\n[CHK-1]\n")
    code, out = run_flow_check(repo)
    assert code == 1
    assert "без трассировки к спеке" in out


def test_trace_to_unknown_title_is_defect(tmp_path):
    """Ссылка на несуществующий заголовок спеки — дефект трассировки."""
    repo = make_repo(tmp_path)
    write_case(
        repo,
        "# TC-WID-001 — пустой список\n\nRequirement: Несуществующий сценарий\n")
    code, out = run_flow_check(repo)
    assert code == 1
    assert "без трассировки к спеке" in out


def test_checklist_not_required_and_not_validated(tmp_path):
    """Чеклист без спеки-источника и без раздела «Дефекты спеки» больше не
    ошибка: append-only история не валидируется."""
    repo = make_repo(tmp_path)
    cl = repo / "test-model" / "checklists"
    cl.mkdir(parents=True)
    (cl / "legacy.md").write_text("| CHK-9 | без источника |\n", encoding="utf-8")
    write_case(
        repo,
        "# TC-WID-001 — пустой список\n\nRequirement: Виджет список\n")
    code, out = run_flow_check(repo)
    assert code == 0, out
