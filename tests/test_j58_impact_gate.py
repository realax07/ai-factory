# -*- coding: utf-8 -*-
"""J58: impact-карта — обязательный артефакт СА + механическая сверка diff↔карта.

Правила (scripts/impact_rules.json, pr_validate.check_impact_gate):
  - [change-id] PR: обязателен impact-артефакт — openspec/changes/<id>/impact.md
    ИЛИ секция «## Impact» в design.md/proposal.md;
  - механическая сверка диффа с правилами — для ЛЮБОГО маркера; расхождение
    = DENY с id правила и подсказкой;
  - [chore]/[docs]/[ops] — только правила, карта не требуется (не душить chore).

Трассировка:
  TC-J58-001..008  четыре стартовых правила IR-01..IR-04 (позитив + негатив)
  TC-J58-009..011  карта: impact.md / секция «## Impact» / отсутствует
  TC-J58-012       [chore]: механика работает, карта НЕ требуется
  TC-J58-013       [docs]/[ops]: карта не требуется; правило срабатывает
  TC-J58-014       расширяемость: стороннее правило из user-rules срабатывает
  TC-J58-015       битый/отсутствующий rules.json — сверка молчит (WARN)
  TC-J58-016       парсер диффа: PR_CHANGED_FILES со статусами и без
  TC-J58-017       статус-фильтр правила: IR-02 не срабатывает на 'M'
  TC-J58-018       фабричный impact_rules.json валиден и содержит 4 правила
  TC-J58-019       factory_init ставит шаблон openspec/changes/_template/impact.md
  TC-J58-020       change-PR без пакета: карта не дублируется (пакет ловит check_change)
  TC-J58-021       exists-guard: фабричный PR (contracts/ без openapi.json в
                   HEAD, services/, frontend/, migrate_) — правила молчат
  TC-J58-022       exists-guard: продуктовый репо (артефакты в HEAD) — DENY прежний
  TC-J58-023       вне git (HEAD не определён) — guard не применяется, DENY прежний
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import pr_validate  # noqa: E402


def F(st: str | None, path: str) -> tuple[str | None, str]:
    return (st, path)


@pytest.fixture()
def rules_repo(tmp_path) -> Path:
    """Репо с фабричным impact_rules.json (копия эталона)."""
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # conftest J41 может уже создать proj/ (PLAN-fixture)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "impact_rules.json").write_text(
        (FACTORY / "scripts" / "impact_rules.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return repo


@pytest.fixture()
def no_env(monkeypatch):
    monkeypatch.delenv("PR_CHANGED_FILES", raising=False)


# --- TC-J58-001..002: IR-01 контракт → contracts/openapi.json ---

def test_j58_ir01_positive(rules_repo, no_env):
    files = [F("M", "services/weather/openapi.yaml"),
             F("M", "contracts/openapi.json")]
    assert pr_validate.check_impact_rules(rules_repo, files) == []


def test_j58_ir01_negative(rules_repo, no_env):
    files = [F("M", "services/weather/openapi.yaml")]
    errs = pr_validate.check_impact_rules(rules_repo, files)
    assert len(errs) == 1
    assert "IR-01" in errs[0] and "contracts/openapi.json" in errs[0]
    assert "перегенерируй" in errs[0]  # подсказка: что ожидалось


# --- TC-J58-003..004: IR-02 новый сервис → deploy.sh + RUNBOOK ---

def test_j58_ir02_positive(rules_repo, no_env):
    files = [F("A", "services/catalog/app.py"),
             F("M", "deploy/deploy.sh"),
             F("M", "deploy/RUNBOOK.md")]
    assert pr_validate.check_impact_rules(rules_repo, files) == []


def test_j58_ir02_negative(rules_repo, no_env):
    errs = pr_validate.check_impact_rules(rules_repo, [F("A", "services/catalog/app.py")])
    assert len(errs) == 2
    assert "IR-02" in errs[0] and "deploy/deploy.sh" in errs[0]
    assert "IR-02" in errs[1] and "deploy/RUNBOOK.md" in errs[1]
    assert "weather-1" in errs[0]  # урок релиза в подсказке


# --- TC-J58-005..006: IR-03 статика → static_v в backend/app/pages.py ---

@pytest.mark.parametrize("static_path", [
    "frontend/static/css/app.css",
    "frontend/templates/index.html",
    "services/wiki/frontend/static/main.css",
])
def test_j58_ir03_positive(rules_repo, no_env, static_path):
    files = [F("M", static_path), F("M", "backend/app/pages.py")]
    assert pr_validate.check_impact_rules(rules_repo, files) == []


def test_j58_ir03_negative(rules_repo, no_env):
    errs = pr_validate.check_impact_rules(rules_repo, [F("M", "frontend/static/app.css")])
    assert len(errs) == 1
    assert "IR-03" in errs[0] and "pages.py" in errs[0]


# --- TC-J58-007..008: IR-04 миграция → RUNBOOK ---

def test_j58_ir04_positive(rules_repo, no_env):
    files = [F("A", "backend/migrations/migrate_0042_add_avatars.py"),
             F("M", "deploy/RUNBOOK.md")]
    assert pr_validate.check_impact_rules(rules_repo, files) == []


def test_j58_ir04_negative(rules_repo, no_env):
    errs = pr_validate.check_impact_rules(
        rules_repo, [F("A", "backend/migrations/migrate_0042_add_avatars.py")])
    assert len(errs) == 1
    assert "IR-04" in errs[0] and "RUNBOOK" in errs[0]


# --- TC-J58-009..011: карта есть/нет ---

def _make_pkg(repo: Path, cid: str = "add-widget") -> Path:
    pkg = repo / "openspec" / "changes" / cid
    pkg.mkdir(parents=True)
    return pkg


def test_j58_map_impact_md_ok(rules_repo, no_env):
    pkg = _make_pkg(rules_repo)
    (pkg / "impact.md").write_text("# Impact\n\n## Затронутые сервисы\n", encoding="utf-8")
    assert pr_validate.impact_map_problem(rules_repo, "add-widget") is None


def test_j58_map_impact_section_in_design_ok(rules_repo, no_env):
    pkg = _make_pkg(rules_repo)
    (pkg / "design.md").write_text("# Design\n\n## Impact\n\nсервисы: weather\n",
                                   encoding="utf-8")
    assert pr_validate.impact_map_problem(rules_repo, "add-widget") is None


@pytest.mark.parametrize("flow_type", ["change"])
def test_j58_map_missing_denies(rules_repo, no_env, flow_type):
    _make_pkg(rules_repo)
    errs = pr_validate.check_impact_gate(rules_repo, flow_type, "add-widget")
    assert len(errs) == 1
    assert "impact.md" in errs[0] and "J58" in errs[0]
    assert "## Impact" in errs[0]  # подсказка: где еще может жить карта


def test_j58_map_in_proposal_ok(rules_repo, no_env):
    pkg = _make_pkg(rules_repo)
    (pkg / "proposal.md").write_text("# Proposal\n\n## Impact\n\n—\n", encoding="utf-8")
    assert pr_validate.impact_map_problem(rules_repo, "add-widget") is None


# --- TC-J58-012: [chore] не душится: механика без карты ---

def test_j58_chore_no_map_no_rules_silent(rules_repo, no_env):
    """[chore]: карта не требуется; дифф правил не триггерит — DENY нет."""
    errs = pr_validate.check_impact_gate(rules_repo, "chore", "chore")
    assert errs == []


def test_j58_chore_with_rule_violation_denies_but_no_map(rules_repo, no_env):
    """[chore]: расхождение с правилом = DENY (механика), но требования карты НЕТ."""
    errs = pr_validate.check_impact_gate(rules_repo, "chore", "chore")
    assert not any("impact-карта" in e for e in errs)
    errs = pr_validate.check_impact_rules(rules_repo, [F("M", "contracts/api.yaml")])
    assert errs and "IR-01" in errs[0]


# --- TC-J58-013: [docs]/[ops] — карта не требуется, механика работает ---

def test_j58_docs_ops_no_map(rules_repo, no_env):
    assert pr_validate.check_impact_gate(rules_repo, "docs", "docs") == []
    assert pr_validate.check_impact_gate(rules_repo, "ops", "ops") == []


# --- TC-J58-014: расширяемость — стороннее правило срабатывает ---

def test_j58_rules_extensible(rules_repo, no_env):
    (rules_repo / "scripts" / "impact_rules.json").write_text(json.dumps({
        "version": 1,
        "rules": [{
            "id": "IR-99",
            "title": "тестовое правило проекта",
            "when": [{"path": "^infra/"}],
            "require": [{"path": "^docs/infra\\.md$", "label": "docs/infra.md",
                         "hint": "опиши инфраструктуру"}],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    errs = pr_validate.check_impact_rules(rules_repo, [F("M", "infra/x.tf")])
    assert errs and "IR-99" in errs[0] and "docs/infra.md" in errs[0]
    # позитив: требование покрыто диффом — молчит
    assert pr_validate.check_impact_rules(rules_repo, [F("M", "infra/x.tf"),
                                                       F("M", "docs/infra.md")]) == []


# --- TC-J58-015: нет/битый rules.json — сверка молчит (WARN) ---

def test_j58_no_rules_file_silent(tmp_path, no_env, capsys):
    repo = tmp_path / "bare"
    repo.mkdir()
    assert pr_validate.check_impact_gate(repo, "chore", "chore") == []
    assert "J58" not in capsys.readouterr().err


def test_j58_broken_rules_json_warns(tmp_path, no_env, capsys):
    repo = tmp_path / "broken"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "impact_rules.json").write_text("{не json", encoding="utf-8")
    assert pr_validate.check_impact_rules(repo, [F("M", "contracts/openapi.json")]) == []
    assert "не читается как JSON" in capsys.readouterr().err


# --- TC-J58-016: парсер диффа (env-конвенция CI) ---

def test_j58_changed_files_env_with_status(monkeypatch):
    monkeypatch.setenv("PR_CHANGED_FILES", "A\tservices/x.py\nM\tcontracts/openapi.json\n")
    assert pr_validate.pr_changed_files(Path("/nonexistent")) == [
        ("A", "services/x.py"), ("M", "contracts/openapi.json")]


def test_j58_changed_files_env_bare_paths(monkeypatch):
    monkeypatch.setenv("PR_CHANGED_FILES", "services/x.py\nbackend/y.py")
    files = pr_validate.pr_changed_files(Path("/nonexistent"))
    assert files == [(None, "services/x.py"), (None, "backend/y.py")]


def test_j58_changed_files_git_fallback(tmp_path, monkeypatch, no_env):
    """Fallback: name-status из git (real-репо с одним коммитом + правка)."""
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True,
                       capture_output=True, text=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (repo / "a.txt").write_text("1", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "init")
    (repo / "a.txt").write_text("2", encoding="utf-8")
    files = pr_validate.pr_changed_files(repo)
    assert files == [("M", "a.txt")]


# --- TC-J58-017: статус-фильтр: IR-02 ('A') молчит на 'M' ---

def test_j58_status_filter_ir02_modify_silent(rules_repo, no_env):
    files = [F("M", "services/weather/api.py")]
    assert pr_validate.check_impact_rules(rules_repo, files) == []


def test_j58_status_filter_unknown_status_conservative(rules_repo, no_env):
    """Неизвестный статус (bare-path env) — правило считается сработавшим
    (консервативный DENY лучше молчаливого пропуска)."""
    errs = pr_validate.check_impact_rules(rules_repo, [(None, "services/newsvc/app.py")])
    assert errs and "IR-02" in errs[0]


# --- TC-J58-018: фабричный rules.json валиден, 4 стартовых правила ---

def test_j58_factory_rules_valid():
    data = json.loads((FACTORY / "scripts" / "impact_rules.json").read_text(encoding="utf-8"))
    rules = data["rules"]
    assert [r["id"] for r in rules] == ["IR-01", "IR-02", "IR-03", "IR-04"]
    for r in rules:
        assert r.get("title") and r.get("when") and r.get("require")
        for w in r["when"]:
            assert w.get("path")
        for req in r["require"]:
            assert req.get("path") and req.get("label") and req.get("hint")


# --- TC-J58-019: factory_init ставит шаблон impact-карты ---

def test_j58_factory_init_impact_template(tmp_path):
    from factory_init import install_impact_template, IMPACT_TEMPLATE_REL
    target = tmp_path / "proj"
    target.mkdir(exist_ok=True)  # conftest J41 может уже создать proj/
    install_impact_template(target)
    dst = target / IMPACT_TEMPLATE_REL
    assert dst.is_file()
    text = dst.read_text(encoding="utf-8")
    for section in ("Затронутые сервисы", "Контракты", "Статика",
                    "Deploy-матрица", "Миграции", "Тесты"):
        assert section in text
    # идемпотентность: контент проекта не перезаписывается
    dst.write_text("проектный контент", encoding="utf-8")
    install_impact_template(target)
    assert dst.read_text(encoding="utf-8") == "проектный контент"


def test_j58_factory_init_copies_rules_json(tmp_path):
    from factory_init import COPY_FILES
    assert "scripts/impact_rules.json" in COPY_FILES


# --- TC-J58-020: change-PR без пакета — карта не дублируется ---

def test_j58_no_package_no_map_error(rules_repo, no_env):
    """Пакета нет → check_change сам вернет 'пакет отсутствует';
    impact-гейт карту не требует (не дублирует отказ)."""
    errs = pr_validate.check_impact_gate(rules_repo, "change", "absent-pkg")
    assert errs == []


# --- TC-J58-021..023: exists-guard require (J58-fix, ревью-001 замечание 1) ---

def _init_git_repo(tmp_path: Path, name: str,
                   files: dict[str, str]) -> Path:
    """Real git-репо с одним коммитом (HEAD-дерево для exists-guard)."""
    repo = tmp_path / name
    repo.mkdir(exist_ok=True)  # conftest J41 может уже создать proj/
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "impact_rules.json").write_text(
        (FACTORY / "scripts" / "impact_rules.json").read_text(encoding="utf-8"),
        encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True,
                       capture_output=True, text=True)
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", ".")
    git("commit", "-qm", "init")
    return repo


FACTORY_LIKE = {
    "contracts/artifact_contract.md": "контракт фабрики\n",
    "contracts/flow_control_contract.md": "контракт флоу\n",
}

PRODUCT_LIKE = {
    **FACTORY_LIKE,
    "contracts/openapi.json": "{}\n",
    "services/weather/openapi.yaml": "openapi: 3.0\n",
    "deploy/deploy.sh": "#!/bin/sh\n",
    "deploy/RUNBOOK.md": "# RUNBOOK\n",
    "backend/app/pages.py": "static_v = 1\n",
}


def test_j58_exists_guard_factory_pr_silent(tmp_path, no_env):
    """Фабричный PR: артефактов (contracts/openapi.json, deploy/,
    backend/app/pages.py) в HEAD нет — все 4 правила молчат, despite триггеры."""
    repo = _init_git_repo(tmp_path, "factory", FACTORY_LIKE)
    assert pr_validate.check_impact_rules(
        repo, [F("M", "contracts/artifact_contract.md")]) == []          # IR-01
    assert pr_validate.check_impact_rules(
        repo, [F("A", "services/newsvc/app.py")]) == []                  # IR-02
    assert pr_validate.check_impact_rules(
        repo, [F("M", "frontend/static/app.css")]) == []                 # IR-03
    assert pr_validate.check_impact_rules(
        repo, [F("A", "ops/migrate_0001_init.py")]) == []                # IR-04


def test_j58_exists_guard_product_repo_denies(tmp_path, no_env):
    """Продуктовый репо: артефакты есть в HEAD — DENY прежний (не ослаблен)."""
    repo = _init_git_repo(tmp_path, "product", PRODUCT_LIKE)
    errs = pr_validate.check_impact_rules(
        repo, [F("M", "services/weather/openapi.yaml")])
    assert len(errs) == 1 and "IR-01" in errs[0]
    errs = pr_validate.check_impact_rules(repo, [F("A", "services/catalog/app.py")])
    assert len(errs) == 2 and all("IR-02" in e for e in errs)
    errs = pr_validate.check_impact_rules(repo, [F("M", "frontend/static/app.css")])
    assert len(errs) == 1 and "IR-03" in errs[0]
    errs = pr_validate.check_impact_rules(
        repo, [F("A", "backend/migrations/migrate_0042_x.py")])
    assert len(errs) == 1 and "IR-04" in errs[0]


def test_j58_exists_guard_product_positive_still_ok(tmp_path, no_env):
    """Продуктовый позитив не сломан: требование покрыто диффом — молчит."""
    repo = _init_git_repo(tmp_path, "product", PRODUCT_LIKE)
    assert pr_validate.check_impact_rules(
        repo, [F("M", "services/weather/openapi.yaml"),
               F("M", "contracts/openapi.json")]) == []


def test_j58_exists_guard_no_git_enforces(tmp_path, no_env):
    """Вне git HEAD не определён — guard не применяется (консервативно):
    требование работает как раньше, DENY не потерян."""
    repo = tmp_path / "nogit"
    repo.mkdir(exist_ok=True)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "impact_rules.json").write_text(
        (FACTORY / "scripts" / "impact_rules.json").read_text(encoding="utf-8"),
        encoding="utf-8")
    errs = pr_validate.check_impact_rules(repo, [F("M", "contracts/api.yaml")])
    assert len(errs) == 1 and "IR-01" in errs[0]
    assert pr_validate._head_files(repo) is None
