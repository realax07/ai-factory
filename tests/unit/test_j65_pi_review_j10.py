# -*- coding: utf-8 -*-
"""J65.4b: ревью стадии Pi пакетного раннера засчитывается в J10 (pr_validate).

До J65.4b pr_validate требовал Reviewer-Delegation, найденную в реестре
делегаций Hermes (state.db → async_delegations); у стадии pi:code-reviewer
раннера такой записи нет, и ее approve в финальном PR пакета не засчитывался.
Теперь раннер ставит в review-файл штамп со своей делегацией стадии, а
pr_validate при отсутствии делегации в реестре Hermes проверяет запись цикла
flowctl раннера.

Трассировка:
  TC-J65-PRV-001  штамп раннера: добавляется после заголовка; повтор с той же
                  делегацией — без изменений; чужая делегация — RunnerStop
  TC-J65-PRV-002  runner_review_ok: роль code_reviewer, тот же change, статус
                  accepted|provisional, пометка package_runner, ≠ dev — True;
                  любое отклонение — False
  TC-J65-PRV-003  check_change: делегации нет в Hermes, есть запись раннера —
                  ревью засчитано; нет записи раннера — «не найдена в реестре»
  TC-J65-PRV-004  раннер: штамп в закоммиченном review-файле стадии
                  (test_j65_review_verdict::test_runner_approve_writes_provenance)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import package_runner as pr  # noqa: E402
import pr_validate as pv  # noqa: E402

DELEG = "deleg-0123456789abcdef"


def _review(tmp_path, text="# Ревью\n\n## Вердикт: approve\n"):
    f = tmp_path / "review-001.md"
    f.write_text(text, encoding="utf-8")
    return f


class TestStamp:
    def test_added_after_heading(self, tmp_path):
        """TC-J65-PRV-001."""
        f = _review(tmp_path)
        assert pr.stamp_reviewer_delegation(f, DELEG) is True
        lines = f.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "# Ревью"
        assert pr.REVIEWER_DELEGATION_RE.search(lines[1]).group(1) == DELEG
        assert pr.stamp_reviewer_delegation(f, DELEG) is False   # идемпотентно
        assert f.read_text(encoding="utf-8").count("Reviewer-Delegation") == 1

    def test_foreign_delegation_stops(self, tmp_path):
        """TC-J65-PRV-001: подмена штампа — стоп."""
        f = _review(tmp_path, "# Ревью\nReviewer-Delegation: deleg-ffff\n")
        with pytest.raises(pr.RunnerStop, match="подмена"):
            pr.stamp_reviewer_delegation(f, DELEG)

    def test_resume_replaces_own_stamp(self, tmp_path):
        """TC-J65-PRV-001: return → resume — новая делегация попытки заменяет
        штамп прошлой (без ложного STOP), штамп в файле ровно один."""
        f = _review(tmp_path, "# Ревью\n\n## Вердикт: Вернуть\n")
        pr.stamp_reviewer_delegation(f, "deleg-attempt1aaaaaaaa")
        f.write_text(f.read_text(encoding="utf-8")
                     + "\n## Итерация 2\n\n## Вердикт: approve\n", encoding="utf-8")
        assert pr.stamp_reviewer_delegation(f, DELEG) is True
        text = f.read_text(encoding="utf-8")
        assert text.count("Reviewer-Delegation") == 1
        assert pr.REVIEWER_DELEGATION_RE.search(text).group(1) == DELEG

    def test_reviewer_line_same_id_kept(self, tmp_path):
        """Ревьюер вписал верную делегацию сам — штамп не дублируется."""
        f = _review(tmp_path, f"# Ревью\nReviewer-Delegation: {DELEG}\n")
        assert pr.stamp_reviewer_delegation(f, DELEG) is False
        assert f.read_text(encoding="utf-8").count("Reviewer-Delegation") == 1

    def test_missing_file_noop(self, tmp_path):
        assert pr.stamp_reviewer_delegation(tmp_path / "none.md", DELEG) is False


def _run(**over):
    rec = {"delegation_id": DELEG, "actor_role": "code_reviewer",
           "scope": {"change": "add-widget"}, "status": "provisional",
           "package_runner": {"commit": "abc"}}
    rec.update(over)
    return {"runs": {"c1": rec}}


@pytest.mark.parametrize("over,dev,ok", [
    ({}, set(), True),
    ({"status": "accepted"}, set(), True),
    ({"actor_role": "dev"}, set(), False),
    ({"scope": {"change": "other"}}, set(), False),
    ({"status": "returned"}, set(), False),
    ({"package_runner": None}, set(), False),
    ({}, {DELEG.replace("-", "_")}, False),
])
def test_runner_review_ok(over, dev, ok):
    """TC-J65-PRV-002."""
    assert pv.runner_review_ok(DELEG, "add-widget", _run(**over), dev) is ok


def _hermes_db(home: Path):
    home.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(home / "state.db")
    c.execute("CREATE TABLE async_delegations (delegation_id TEXT, state TEXT)")
    c.commit()
    c.close()


@pytest.mark.parametrize("with_runner,expect_counted", [(True, True), (False, False)])
def test_check_change_counts_runner_review(tmp_path, monkeypatch, with_runner,
                                           expect_counted):
    """TC-J65-PRV-003."""
    repo = tmp_path / "proj"
    pkg = repo / "openspec" / "changes" / "add-widget"   # иначе check_change выходит раньше
    pkg.mkdir(parents=True)
    rd = repo / "code-reviews" / "add-widget"
    rd.mkdir(parents=True)
    (rd / "review-1.1-001.md").write_text(
        f"# Ревью\nReviewer-Delegation: {DELEG}\n\n## Вердикт: approve\n",
        encoding="utf-8")
    hermes = tmp_path / "hermes"
    _hermes_db(hermes)
    state = tmp_path / "state" / "flowctl_state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps(_run() if with_runner else {"runs": {}}),
                     encoding="utf-8")
    monkeypatch.setattr(pv.fp, "hermes_home", lambda: hermes)
    monkeypatch.setattr(pv.fp, "flowctl_state_path", lambda: state)
    missing = pv.check_change(repo, "add-widget")
    assert any("proposal.md" in m for m in missing)   # до блока ревью дошли
    flagged = [m for m in missing if "review-1.1-001.md" in m]
    assert (not flagged) is expect_counted, flagged
    if not expect_counted:
        assert "не найдена в реестре делегаций" in flagged[0]
