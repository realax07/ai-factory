# -*- coding: utf-8 -*-
"""J52: factory_init не перезаписывает проектный .github/workflows/flow.yml.

Живой инцидент ekotov-wiki (шов J53-раскатки): factory_init --force затер
проектный flow.yml с required-check «test-flow-control» → все PR проекта
блокируются. Idempotent-правило расширено на workflow:

  TC-J52-001  существующий проектный workflow переживает init без --force
              (контент не тронут, сообщение «не тронут»)
  TC-J52-002  существующий проектный workflow переживает init С --force
              (контент не тронут + WARNING о ручной сверке с эталоном:
              required-checks, триггеры)
  TC-J52-003  workflow отсутствует → копируется фабричный эталон
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
for p in (str(SCRIPTS),):
    if p not in sys.path:
        sys.path.insert(0, p)

import factory_init  # noqa: E402

PROJECT_YML = """\
name: project-ci
on: [push, pull_request]
jobs:
  test-flow-control:
    runs-on: ubuntu-latest
    steps:
      - run: echo "project required-check"
"""


def init(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "factory_init.py"),
         "--target", str(repo), "--name", "T", "--skip-plugin", *extra],
        capture_output=True, text=True,
    )


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "README.md").write_text("# r\n", encoding="utf-8")
    return repo


class TestProjectWorkflowGuard:
    def test_existing_workflow_survives_plain_init(self, tmp_path):
        """TC-J52-001: проектный workflow не тронут без --force."""
        repo = make_repo(tmp_path)
        wf = repo / factory_init.PROJECT_WORKFLOW_REL
        wf.parent.mkdir(parents=True)
        wf.write_text(PROJECT_YML, encoding="utf-8")
        r = init(repo)
        assert r.returncode == 0, r.stderr
        assert wf.read_text(encoding="utf-8") == PROJECT_YML
        assert "уже существует" in r.stdout
        assert "WARNING" not in r.stdout

    def test_existing_workflow_survives_force(self, tmp_path):
        """TC-J52-002: проектный workflow переживает --force; WARNING
        предписывает ручную сверку с фабричным эталоном."""
        repo = make_repo(tmp_path)
        wf = repo / factory_init.PROJECT_WORKFLOW_REL
        wf.parent.mkdir(parents=True)
        wf.write_text(PROJECT_YML, encoding="utf-8")
        r = init(repo, "--force")
        assert r.returncode == 0, r.stderr
        assert wf.read_text(encoding="utf-8") == PROJECT_YML
        assert "WARNING" in r.stdout
        assert "проектный workflow сохранен" in r.stdout
        assert "сверьте с фабричным эталоном вручную" in r.stdout
        assert "required-checks" in r.stdout
        # другие файлы при --force перезаписываются как раньше
        assert "test_smoke.py создан" in r.stdout or \
            (repo / "tests" / "test_smoke.py").is_file()

    def test_missing_workflow_copies_factory_reference(self, tmp_path):
        """TC-J52-003: файла нет → ставится фабричный эталон."""
        repo = make_repo(tmp_path)
        r = init(repo)
        wf = repo / factory_init.PROJECT_WORKFLOW_REL
        assert wf.is_file()
        assert wf.read_text(encoding="utf-8") == (
            FACTORY / factory_init.PROJECT_WORKFLOW_REL).read_text(
                encoding="utf-8")
        assert "создан (фабричный эталон)" in r.stdout

    def test_force_with_project_workflow_keeps_it_not_reference(self, tmp_path):
        """TC-J52-004 (инцидент ekotov-wiki): --force НЕ подменяет проектный
        workflow фабричным эталоном (required-check проекта остается)."""
        repo = make_repo(tmp_path)
        wf = repo / factory_init.PROJECT_WORKFLOW_REL
        wf.parent.mkdir(parents=True)
        wf.write_text(PROJECT_YML, encoding="utf-8")
        init(repo, "--force")
        text = wf.read_text(encoding="utf-8")
        assert text == PROJECT_YML
        assert "test-flow-control" in text
