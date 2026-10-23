# -*- coding: utf-8 -*-
"""АУД-4: pre-flight чеки диспетчеризации (scripts/flow_preflight.py).

  static_v (Н24/R7): дифф трогает frontend static|templates / pages.py —
    static_v в рабочем дереве уже бампнут относительно main (иначе WARN),
    а не DENY на PR после полного dev-цикла.
  regress-staleness (Н24): regress-final старше последнего касания
    tests//backend/ ветки → WARN «не запускай, будет STALE» ДО прогона.
  check pr-body (Н20/Н25): механика pr_body-требований IR-05/IR-06.
  snapshot (Н17): ветка снапшота == текущий checkout.

Трассировка:
  TC-PF-001..004  static_v: WARN / OK / SKIP (не продуктовое дерево) /
                  SKIP (статика не тронута)
  TC-PF-005..007  regress-staleness: WARN (touch новее прогона) /
                  OK (прогон свежее) / SKIP (нет артефактов)
  TC-PF-008..010  pr-body: WARN (нет docker build / нет sha256) / OK /
                  SKIP (нет PR-контекста)
  TC-PF-011..013  pr-body content_when: IR-06 молчит без ассетов в патче /
                  WARN при ffmpeg-строке в Dockerfile / curl без sha256
  TC-PF-014..016  snapshot: OK / WARN ветка ≠ / WARN detached-HEAD
  TC-PF-017       CLI: JSON в stdout, exit-коды 0/1 (--strict)
  TC-PF-018       инертность pr_body-правил в существующих DENY-воротах
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
for p in (str(SCRIPTS),):
    if p not in sys.path:
        sys.path.insert(0, p)

import flow_preflight as fp  # noqa: E402


# --------------------------------------------------------------- helpers

def git(repo: Path, *args: str, date: str | None = None) -> str:
    env = dict(os.environ)
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def init_repo(tmp_path: Path, files: dict[str, str],
              name: str = "proj") -> Path:
    repo = tmp_path / name
    repo.mkdir(exist_ok=True)
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts" / "impact_rules.json").write_text(
        (SCRIPTS / "impact_rules.json").read_text(encoding="utf-8"),
        encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "init")
    git(repo, "branch", "origin/main")  # merge-base ищет main/origin/main
    git(repo, "checkout", "-q", "-b", "feature")
    return repo


PAGES = "static_v = 3\n"

PRODUCT = {
    "backend/app/pages.py": PAGES,
    "frontend/static/css/app.css": ".x{}\n",
    "tests/test_x.py": "def test_x(): pass\n",
}


def branch_commit(repo: Path, files: dict[str, str], msg: str,
                  date: str | None = None) -> None:
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    git(repo, "add", ".")
    if date:
        git(repo, "commit", "-qm", msg, date=date)
    else:
        git(repo, "commit", "-qm", msg)


def write_final(repo: Path, cid: str, commit: str) -> Path:
    art = repo / "test-model" / "regress" / cid / "regress-final.md"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(
        f"- date: 2026-10-23T00:00:00Z\n- commit: {commit}\n"
        f"- verdict: PASS\n", encoding="utf-8")
    return art


# ------------------------------------------------------- static_v (Н24)

def test_pf_static_v_warn_not_bumped(tmp_path):
    repo = init_repo(tmp_path, PRODUCT)
    branch_commit(repo, {"frontend/static/css/app.css": ".y{}\n"}, "css")
    res = fp.check_static_v(repo)
    assert res["status"] == "WARN"
    assert any("бампни ДО диспетчеризации" in w for w in res["warns"])
    assert res["base"] == 3 and res["worktree"] == 3


def test_pf_static_v_ok_bumped(tmp_path):
    repo = init_repo(tmp_path, PRODUCT)
    branch_commit(repo, {"frontend/static/css/app.css": ".y{}\n",
                         "backend/app/pages.py": "static_v = 4\n"}, "css+v")
    res = fp.check_static_v(repo)
    assert res["status"] == "OK" and res["worktree"] == 4


def test_pf_static_v_skip_no_pages(tmp_path):
    repo = init_repo(tmp_path, {"frontend/static/app.css": ".x{}\n"})
    branch_commit(repo, {"frontend/static/app.css": ".yy{}\n"}, "css")
    res = fp.check_static_v(repo)
    assert res["status"] == "SKIP"  # exists-guard: pages.py нет в HEAD


def test_pf_static_v_skip_no_static_diff(tmp_path):
    repo = init_repo(tmp_path, PRODUCT)
    branch_commit(repo, {"backend/app/api.py": "x = 1\n"}, "code")
    res = fp.check_static_v(repo)
    assert res["status"] == "OK"
    assert "не трогает" in res["note"]


# --------------------------------------------- regress-staleness (Н24)

def test_pf_regress_stale_warn(tmp_path):
    repo = init_repo(tmp_path, PRODUCT)
    old = "2026-10-20T10:00:00"
    branch_commit(repo, {"backend/app/api.py": "x = 1\n"}, "code",
                  date=f"{old} +0000")
    head_old = git(repo, "rev-parse", "HEAD").strip()
    write_final(repo, "add-widget", head_old)
    # касание tests/ ПОСЛЕ прогона
    branch_commit(repo, {"tests/test_y.py": "def test_y(): pass\n"},
                  "tests", date="2026-10-22T10:00:00 +0000")
    res = fp.check_regress_staleness(repo)
    assert res["status"] == "WARN"
    assert any("НЕ запускай диспетчеризацию" in w and "STALE" in w
               for w in res["warns"])


def test_pf_regress_fresh_ok(tmp_path):
    repo = init_repo(tmp_path, PRODUCT)
    branch_commit(repo, {"tests/test_y.py": "def test_y(): pass\n"},
                  "tests", date="2026-10-21T10:00:00 +0000")
    head = git(repo, "rev-parse", "HEAD").strip()
    write_final(repo, "add-widget", head)
    res = fp.check_regress_staleness(repo)
    assert res["status"] == "OK"


def test_pf_regress_skip_no_artifacts(tmp_path):
    repo = init_repo(tmp_path, PRODUCT)
    branch_commit(repo, {"tests/test_y.py": "def test_y(): pass\n"}, "tests")
    res = fp.check_regress_staleness(repo)
    assert res["status"] == "SKIP"


# ------------------------------------------------- pr-body (Н20/Н25)

DOCKER_FILES = {
    "services/api/Dockerfile": "FROM python:3.12\nCOPY app /app\n",
}


def test_pf_prbody_ir05_warn_no_docker_build(tmp_path):
    repo = init_repo(tmp_path, DOCKER_FILES)
    branch_commit(repo, {"services/api/Dockerfile":
                         "FROM python:3.12\nCOPY app2 /app\n"}, "docker")
    res = fp.check_pr_body(repo, None, None)
    # тела нет — единый WARN «не проверены», правило сработало
    assert res["status"] == "WARN"
    assert "IR-05" in res["rules_triggered"]
    assert any("недоступно" in w for w in res["warns"])
    body = tmp_path / "body.md"
    body.write_text("проверено маунтом на стенд, сборку не делали\n",
                    encoding="utf-8")
    res = fp.check_pr_body(repo, None, str(body))
    assert res["status"] == "WARN"
    assert any("docker build" in w and "IR-05" in w for w in res["warns"])


def test_pf_prbody_ir05_ok_with_build_line(tmp_path):
    repo = init_repo(tmp_path, DOCKER_FILES)
    branch_commit(repo, {"services/api/Dockerfile":
                         "FROM python:3.13\nCOPY app2 /app\n"}, "docker")
    body = tmp_path / "body.md"
    body.write_text("проверено:\n```\ndocker build -t api .\n```\n",
                    encoding="utf-8")
    res = fp.check_pr_body(repo, None, str(body))
    assert res["status"] == "OK" and res["rules_triggered"] == ["IR-05"]


def test_pf_prbody_ir06_sha_ok_and_missing(tmp_path):
    repo = init_repo(tmp_path, DOCKER_FILES)
    branch_commit(repo, {"services/api/Dockerfile":
                         "FROM python:3.12\n"
                         "RUN curl -L -o /usr/bin/ffmpeg https://johnvansickle.com/ffmpeg.tar.gz\n"},
                   "asset")
    body = tmp_path / "body.md"
    body.write_text("ассеты:\nhttps://johnvansickle.com/ffmpeg.tar.gz sha256:"
                    "ab" * 32 + "\n", encoding="utf-8")
    res = fp.check_pr_body(repo, None, str(body))
    assert "IR-06" in res["rules_triggered"]
    # sha256 упомянут — IR-06 молчит; IR-05 (тоже сработал на Dockerfile) WARN
    assert res["status"] == "WARN"
    assert all("IR-06" not in w for w in res["warns"])
    body.write_text("ассеты: johnvansickle tarball, без хешей\n", encoding="utf-8")
    res2 = fp.check_pr_body(repo, None, str(body))
    assert any("IR-06" in w and "sha256" in w for w in res2["warns"])


def test_pf_prbody_ir06_silent_without_assets(tmp_path):
    repo = init_repo(tmp_path, DOCKER_FILES)
    branch_commit(repo, {"services/api/Dockerfile":
                         "FROM python:3.13-slim\nCOPY x /x\n"}, "docker")
    body = tmp_path / "body.md"
    body.write_text("docker build -t api .\n", encoding="utf-8")
    res = fp.check_pr_body(repo, None, str(body))
    # content_when не сработал (в патче нет ассетов) — IR-06 не триггерится
    assert res["rules_triggered"] == ["IR-05"]
    assert res["status"] == "OK"


# ------------------------------------------------------ snapshot (Н17)

def test_pf_snapshot_ok(tmp_path):
    repo = init_repo(tmp_path, PRODUCT)
    res = fp.check_snapshot(repo, "feature")
    assert res["status"] == "OK" and res["branch"] == "feature"


def test_pf_snapshot_wrong_branch(tmp_path):
    repo = init_repo(tmp_path, PRODUCT)
    res = fp.check_snapshot(repo, "main")
    assert res["status"] == "WARN"
    assert any("пересними снапшот" in w for w in res["warns"])


def test_pf_snapshot_detached_head_warn(tmp_path):
    """Н17: checkout сменился (detached) — ворота прочитают не то дерево."""
    repo = init_repo(tmp_path, PRODUCT)
    branch_commit(repo, {"backend/app/api.py": "x = 2\n"}, "next")
    git(repo, "checkout", "-q", "--detach")
    res = fp.check_snapshot(repo, "feature")
    assert res["status"] == "WARN"
    assert any("пересними снапшот" in w for w in res["warns"])
    assert res["branch"] == "HEAD"


# ------------------------------------------------------------- CLI

def test_pf_cli_json_and_exit_codes(tmp_path):
    repo = init_repo(tmp_path, PRODUCT)
    branch_commit(repo, {"frontend/static/css/app.css": ".z{}\n"}, "css")
    # static_v: JSON в stdout, exit 0 без --strict
    p = subprocess.run(
        [sys.executable, str(SCRIPTS / "flow_preflight.py"),
         "static_v", "--repo", str(repo)],
        capture_output=True, text=True)
    assert p.returncode == 0
    assert json.loads(p.stdout)["check"] == "static_v"
    p2 = subprocess.run(
        [sys.executable, str(SCRIPTS / "flow_preflight.py"),
         "static_v", "--repo", str(repo), "--strict"],
        capture_output=True, text=True)
    assert p2.returncode == 1


def test_pf_prbody_rules_inert_in_existing_gates(tmp_path):
    """Н20/Н25-контракт: pr_body-правила не создают DENY в существующих
    воротах pr_validate.check_impact_rules (require без path пропускается)."""
    import pr_validate
    repo = init_repo(tmp_path, {**PRODUCT, "services/api/Dockerfile":
                                "FROM python:3.12\n"})
    branch_commit(repo, {"services/api/Dockerfile":
                         "RUN curl -L -o /f https://johnvansickle.com/x.tar.gz\n"},
                   "docker")
    os.environ.pop("PR_CHANGED_FILES", None)
    errs = pr_validate.check_impact_rules(
        repo, [("M", "services/api/Dockerfile")])
    assert errs == [], errs
