# -*- coding: utf-8 -*-
"""Фиксы по return code-review PR #126 (code-reviews/j51/review-003.md).

Покрывает (нумерация TC-R3-NNN — по замечаниям ревью):
  - major #1: MAP J51 возвращен в [ ] с пометкой про живой параллельный
    пилот (критерий закрытия — после merge);
  - minor #2: роль regress_runner в ROLE_ZONE_POLICY + digest/дата
    POLICY_TABLE_DIGEST под текущую редакцию таблицы agents/README.md
    (дайджест воспроизводим: sha256 таблицы в запиненном коммите);
  - minor #3: check_regress_final валидирует change-id той же функцией,
    что и cmd_regress (session_check.change_id_problem — единая точка);
  - minor #4: свежестная сверка «артефакт ↔ дерево»: если в артефакте
    указан worktree, его HEAD обязан совпадать с commit прогона
    (flowctl regress пишет `- worktree:` в артефакт).
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
for p in (str(SCRIPTS),):
    if p not in sys.path:
        sys.path.insert(0, p)

import pr_validate  # noqa: E402
import role_zone_policy as rzp  # noqa: E402
import session_check as sc  # noqa: E402

CHANGE = "add-widget"


# --------------------------------------------------------------- helpers

def git(repo: Path, *args: str) -> str:
    env = {**__import__("os").environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True, env=env)
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path: Path) -> Path:
    """Git-репо с каркасом change-пакета (ветка main, чистое дерево)."""
    repo = tmp_path / "proj"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    write(repo, "openspec/changes/add-widget/proposal.md", "# p\n")
    write(repo, "src/widget.py", "X = 1\n")
    commit_all(repo, "init")
    return repo


def write_final(repo: Path, *, verdict: str = "PASS",
                commit: str | None = None, worktree: str | None = None,
                change: str = CHANGE) -> Path:
    """Артефакт regress-final.md в формате flowctl regress (с worktree-полем)."""
    commit = commit or git(repo, "rev-parse", "HEAD")
    p = repo / "test-model" / "regress" / change / "regress-final.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Regress {change} — regress-final.md", "",
        f"- change: {change}",
        "- date: 2026-10-17T12:00:00+00:00",
        f"- commit: {commit}",
    ]
    if worktree is not None:
        lines.append(f"- worktree: {worktree}")
    lines += [
        f"- verdict: {verdict}",
        "- diff source: git diff main...HEAD",
        "- changed files: 1",
        "- suites: tests",
        "- pytest exit code: 0",
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------- major #1: MAP J51

class TestMapJ51Open:
    def test_j51_is_open_with_pilot_note(self):
        """TC-R3-001 (major #1): J51 в MAP — [ ], критерий закрытия —
        живой параллельный пилот, реализация помечена как замерженная."""
        line = next(l for l in (FACTORY / "backlog" / "MAP.md")
                    .read_text(encoding="utf-8").splitlines()
                    if l.startswith("- [") and "**J51**" in l)
        assert line.startswith("- [ ] **J51**")
        assert "живой параллельный пилот" in line
        assert "два агента" in line and "два worktree" in line
        assert "после merge" in line


# ------------------------------------------------- minor #2: политика ролей

class TestRegressRunnerPolicy:
    def test_regress_runner_in_policy(self):
        """TC-R3-002 (minor #2): regress_runner в ROLE_ZONE_POLICY — зона
        test-model/regress/<change-id>/ (таблица agents/README, дословно)."""
        assert rzp.allowed_zones_for("regress_runner") == \
            ("test-model/regress/*/**",)

    def test_narrow_zones_accepts_regress_dir(self):
        """Зона своей роли резервируется: test-model/regress/<id>/**;
        чужой путь — violation (не расширяется)."""
        ok = rzp.narrow_zones("regress_runner",
                              ["test-model/regress/add-widget/**"])
        assert ok["zones"] == ["test-model/regress/add-widget/**"]
        assert ok["violations"] == []
        bad = rzp.narrow_zones("regress_runner", ["code-reviews/x/review-1.md"])
        assert bad["zones"] == [] and bad["violations"]

    @staticmethod
    def _table_digest(txt: str) -> tuple[str, int, int]:
        """Документированный алгоритм: таблица «Зона записи» (заголовок
        «| Агент | Режим | …» до последней строки-ряда), join "\\n",
        sha256 по UTF-8."""
        lines = txt.splitlines()
        start = next(i for i, l in enumerate(lines)
                     if l.startswith("| Агент | Режим | Зона записи"))
        end = start
        while end + 1 < len(lines) and lines[end + 1].startswith("|"):
            end += 1
        return hashlib.sha256(
            "\n".join(lines[start:end + 1]).encode("utf-8")).hexdigest(), \
            start, end

    def test_policy_digest_matches_pinned_commit(self):
        """TC-R3-003 (minor #2): digest воспроизводим. Если запиненный
        коммит доступен (не shallow) — полная проверка с пином. В
        shallow-клоне CI `git show` пина падает (128) — проверяем
        самосогласованность: digest, задокументированным алгоритмом по
        ТЕКУЩЕМУ agents/README.md, совпадает с POLICY_TABLE_DIGEST
        (дайджест-в-коде обязан соответствовать текущему файлу)."""
        m = re.search(r"agents/README\.md@([0-9a-f]+):.*?sha256 ([0-9a-f]{64})",
                      rzp.POLICY_TABLE_DIGEST)
        assert m, f"не парсится: {rzp.POLICY_TABLE_DIGEST!r}"
        rev, digest = m.group(1), m.group(2)
        pinned = subprocess.run(
            ["git", "-C", str(FACTORY), "show", f"{rev}:agents/README.md"],
            capture_output=True, text=True, check=False)
        if pinned.returncode == 0:
            # полный путь: таблица в запиненном коммите
            calc, start, end = self._table_digest(pinned.stdout)
            lines = pinned.stdout.splitlines()
            assert calc == digest
            assert any("regress_runner" in l for l in lines[start:end + 1])
        else:
            # shallow / коммит недоступен: самосогласованность кода и файла
            assert pinned.returncode == 128, pinned.stderr
            txt = (FACTORY / "agents" / "README.md").read_text(
                encoding="utf-8")
            calc, start, end = self._table_digest(txt)
            assert calc == digest
            lines = txt.splitlines()
            assert any("regress_runner" in l for l in lines[start:end + 1])


# ------------------------------------------------- minor #3: change-id

class TestChangeIdValidation:
    @pytest.mark.parametrize("bad", ["../../evil", "a/b", "..", "", ".x",
                                     "x" * 65, "bad id"])
    def test_gate_rejects_bad_change_id(self, tmp_path, bad):
        """TC-R3-004 (minor #3): ворота не читают путь до валидации
        change-id (traversal закрыт), проблема — текст единой функции."""
        repo = make_repo(tmp_path)
        problems = pr_validate.check_regress_final(repo, bad)
        assert len(problems) == 1
        assert "недопустимый change-id" in problems[0]
        assert "J51.3" in problems[0]

    def test_same_validator_as_writer(self):
        """TC-R3-005 (minor #3): оба конца используют одну функцию —
        pr_validate делегирует session_check.change_id_problem."""
        assert pr_validate._sc is sc
        assert sc.change_id_problem(CHANGE) is None
        assert sc.change_id_problem("../../evil") is not None

    def test_flowctl_regress_rejects_bad_change_id(self, tmp_path):
        """Пишущий конец: flowctl regress с невалидным change-id — rc 2,
        тот же текст, артефакт не создан."""
        repo = make_repo(tmp_path)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "flowctl.py"), "regress",
             "--repo", str(repo), "--change", "../../evil", "--final"],
            capture_output=True, text=True)
        assert r.returncode == 2
        assert "недопустимый change-id" in r.stderr
        assert not (repo / "test-model" / "regress").exists()


# ------------------------------------------------- minor #4: worktree-сверка

class TestWorktreeFreshness:
    def test_worktree_matching_commit_passes(self, tmp_path):
        """TC-R3-006 (minor #4): worktree в артефакте, HEAD дерева == commit
        прогона → ворота пропускают."""
        repo = make_repo(tmp_path)
        write_final(repo, worktree=str(repo))
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_worktree_ahead_stales_artifact(self, tmp_path):
        """TC-R3-007 (minor #4): дерево уехало вперед после прогона →
        REGRESS_FINAL_STALE, даже если commit — валидный предок."""
        repo = make_repo(tmp_path)
        wt = tmp_path / "proj-wt"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q",
                        str(wt), "-b", "wtbranch"], check=True)
        art_commit = git(wt, "rev-parse", "HEAD")
        write_final(repo, commit=art_commit, worktree=str(wt))
        write(wt, "src/other.py", "Y = 2\n")
        commit_all(wt, "advance after run")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "не совпадает с commit прогона" in problems[0]

    def test_worktree_not_git_stales(self, tmp_path):
        """TC-R3-008 (minor #4): путь в артефакте не git-дерево → STALE,
        молчаливого пропуска нет."""
        repo = make_repo(tmp_path)
        not_git = tmp_path / "plain"
        not_git.mkdir()
        write_final(repo, worktree=str(not_git))
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "не читается как git-дерево" in problems[0]

    def test_no_worktree_field_unchanged_behavior(self, tmp_path):
        """Артефакт без worktree-поля (старый формат) — прежняя семантика."""
        repo = make_repo(tmp_path)
        write_final(repo, worktree=None)
        assert pr_validate.check_regress_final(repo, CHANGE) == []


# ------------------------------------------------- e2e: flowctl → ворота

class TestE2e:
    def test_flowctl_writes_worktree_gates_pass(self, tmp_path):
        """TC-R3-009: `flowctl regress --final` пишет `- worktree:` в
        артефакт; ворота (включая новую сверку) пропускают."""
        repo = make_repo(tmp_path)
        write(repo, "tests/test_widget.py", "def test_x():\n    assert 1\n")
        commit_all(repo, "tests")
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "flowctl.py"), "regress",
             "--repo", str(repo), "--change", CHANGE, "--final"],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        art = (repo / "test-model" / "regress" / CHANGE
               / "regress-final.md").read_text(encoding="utf-8")
        assert f"- worktree: {repo}" in art
        assert pr_validate.check_regress_final(repo, CHANGE) == []
