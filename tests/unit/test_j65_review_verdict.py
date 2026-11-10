# -*- coding: utf-8 -*-
"""J65.4 (уточняет J64.12): машиночитаемый вердикт ревью + авто-provenance.

До J65.4 вердикт-ворота раннера искали подстроку «Одобрить» где угодно в
файле: проходили «Не одобрить», шаблон «Одобрить / Вернуть» и файл с
«Вернуть» в первой строке и «Одобрить» ниже. Единый парсер J10
(flow_check.parse_verdict) при этом не знал «Вернуть» (пак code-reviewer
пишет именно так) и считал «Не одобрить» одобрением. Теперь:

- вердикт — заголовок `## Вердикт: approve|return` (Одобрить/Вернуть),
  решает последний заголовок файла; «Не одобрить» и заголовок с обоими
  словами — return; один парсер у раннера, pr_validate, gate_runner и
  pm_bounds_check;
- строка `Commit: <sha>` в файле, если есть, обязана совпасть с
  проверявшимся коммитом (STALE);
- раннер после review-стадии Pi пишет аудит-запись provenance (SHA, digest
  диффа, авторы/ревьюер) в каталог отчетов раннера; рядом с review-файлом
  sidecar не кладется — его читают ворота flow_transition/J10 со своей
  семантикой (интеграция — отдельная задача).

Трассировка:
  TC-J65-VRD-001  таблица заголовков: approve/return/None
  TC-J65-VRD-002  решает последний заголовок (повторная проверка в конце)
  TC-J65-VRD-003  review_commit — последняя строка Commit: (в т.ч. **Commit:**,
                  «- Commit:»)
  TC-J65-VRD-004  раннер: approve → аудит-запись provenance в отчетах раннера
                  (reviewed = HEAD до ревью, ревьюер — делегация стадии,
                  авторы — dev-стадия); рядом с review-файлом sidecar НЕТ
  TC-J65-VRD-005  раннер: return → запись verdict=return + STOP
  TC-J65-VRD-006  раннер: Commit: не тот → STOP STALE, записи нет
  TC-J65-VRD-007  раннер: нет заголовка вердикта → STOP, записи нет
  TC-J65-VRD-008  pm_bounds_check читает вердикт тем же парсером
  TC-J65-VRD-009  gate-стадия с вердиктом: STALE не сверяется (ложного STOP нет)
  TC-J65-VRD-010  «## Вердикт» и значение следующей строкой читаются
"""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import flow_check  # noqa: E402
import package_runner as pr  # noqa: E402
import pm_bounds_check  # noqa: E402

# Настоящий коммит стадии: песочница тестов раннера (autouse-фикстура в
# test_package_runner) его не трогает, но здесь коммиты нужны, чтобы
# reviewed commit отличался от HEAD после ревью.
REAL_COMMIT_STAGE = pr.commit_stage

TABLE = [
    ("## Вердикт: approve\n", "approve"),
    ("## Вердикт: Одобрить\n", "approve"),
    ("## 7. Вердикт: approved\n", "approve"),
    ("## Вердикт: return\n", "return"),
    ("## Вердикт: Вернуть\n", "return"),
    ("## Вердикт: на доработку\n", "return"),
    ("## Вердикт: Не одобрить\n", "return"),
    ("## Вердикт: Одобрить / Вернуть\n", "return"),
    ("Вердикт: Одобрить\n", None),  # проза, не заголовок
    ("## Ревью\n\nвсё хорошо\n", None),
]


@pytest.mark.parametrize("text,expected", TABLE)
def test_parse_verdict_table(text, expected):
    """TC-J65-VRD-001"""
    assert flow_check.parse_verdict(text) == expected


def test_last_heading_decides():
    """TC-J65-VRD-002"""
    assert flow_check.parse_verdict(
        "## Вердикт: Вернуть\n...\n## Повторная проверка\n"
        "## Вердикт: Одобрить\n") == "approve"
    assert flow_check.parse_verdict(
        "## Вердикт: approve\n...\n## Вердикт: return\n") == "return"
    # не решающий заголовок «Вердикт» не сбрасывает найденный
    assert flow_check.parse_verdict(
        "## Вердикт: approve\n### Вердикт по пунктам\n") == "approve"


def test_review_commit():
    """TC-J65-VRD-003"""
    assert flow_check.review_commit("Commit: abc1234\n") == "abc1234"
    assert flow_check.review_commit(
        "Commit: abc1234\n...\nReviewed-Commit: `DEF5678`\n") == "def5678"
    assert flow_check.review_commit("**Commit:** abc1234\n") == "abc1234"
    assert flow_check.review_commit("- Commit: `abc1234`\n") == "abc1234"
    assert flow_check.review_commit("**Commit**: abc1234\n") == "abc1234"
    assert flow_check.review_commit("коммит не указан\n") is None


MANIFEST = """\
# PLAN-x

```yaml
pipeline:
  package: vrd-pkg
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [backend/**]
    - id: review
      run: pi:code-reviewer
      zones: [code-reviews/vrd-pkg/**]
      verdict:
        file: code-reviews/vrd-pkg/review-001.md
    - id: next
      run: gate:true
```
"""
REVIEW = "code-reviews/vrd-pkg/review-001.md"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)
    git = ["git", "-C", str(repo)]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "config", "user.email", "t@t"], check=True)
    subprocess.run([*git, "config", "user.name", "t"], check=True)
    subprocess.run([*git, "config", "commit.gpgsign", "false"], check=True)
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    (repo / "PLAN-x.md").write_text(MANIFEST, encoding="utf-8")
    return repo


def _run(tmp_path, monkeypatch, review_text):
    """dev пишет код, ревьюер — review_text; прочее — песочница раннера
    с уникальной делегацией на стадию и настоящими коммитами."""
    repo = _repo(tmp_path)
    ids = itertools.count(1)

    def gate_new(stage, repo_, wt):
        n = next(ids)
        return {"kind": "fake", "cid": f"cid-{n}",
                "delegation_id": f"deleg-{stage['id']}-{n}",
                "role": pr.flow_role(stage["payload"]),
                "registry": str(tmp_path / "reg.json"),
                "state": str(tmp_path / "st.json"), "repo": str(repo_),
                "base_sha": pr._git_head(wt)}

    def pi(args, cwd, env, timeout):
        if "code-reviews" in env["PI_ZONE_WRITE"]:
            f = cwd / REVIEW
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(review_text, encoding="utf-8")
        else:
            (cwd / "backend").mkdir(exist_ok=True)
            (cwd / "backend" / "app.py").write_text("print(1)\n",
                                                    encoding="utf-8")
        return 0, "", ""

    # Ворота flowctl — разрешающие (их проверка — test_package_runner,
    # секция (м)); здесь предмет — вердикт и provenance.
    monkeypatch.setenv("PIPELINE_FLOW_REGISTRY", str(tmp_path / "reg.json"))
    monkeypatch.setenv("PIPELINE_FLOW_STATE", str(tmp_path / "st.json"))
    monkeypatch.setattr(pr, "gate_new", gate_new)
    monkeypatch.setattr(pr, "gate_begin", lambda m, s, r, w, b, g: g)
    monkeypatch.setattr(pr, "gate_end", lambda g, w, rep: (True, "fake ok"))
    monkeypatch.setattr(pr, "gate_close", lambda g, c: None)
    monkeypatch.setattr(pr, "gate_abandon", lambda g, why: None)
    monkeypatch.setattr(pr, "zone_recheck", lambda g, w: [])
    monkeypatch.setattr(pr, "_registry_status", lambda reg, did: None)
    monkeypatch.setattr(pr, "commit_stage", REAL_COMMIT_STAGE)
    monkeypatch.setattr(pr, "run_pi", pi)
    monkeypatch.setattr(pr, "run_shell",
                        lambda cmd, cwd, timeout, stand_env=None: (0, "", ""))
    monkeypatch.setattr(pr, "ensure_worktree", lambda r, sid, br: r)
    monkeypatch.setattr(pr, "pi_provider_model", lambda role: ("p", "m"))
    head_before = pr._git_head(repo)
    rc = pr.cmd_run(repo / "PLAN-x.md", dry_run=False)
    return repo, rc, head_before


def _records(repo: Path) -> list:
    rdir = repo / "PLAN-x.md.runner-reports"
    return sorted(rdir.glob("review-*.provenance.json")) if rdir.is_dir() else []


def test_runner_approve_writes_provenance(tmp_path, monkeypatch):
    """TC-J65-VRD-004"""
    repo, rc, _ = _run(tmp_path, monkeypatch, "## Вердикт: approve\n")
    assert rc == 0
    recs = _records(repo)
    assert len(recs) == 1
    side = json.loads(recs[0].read_text(encoding="utf-8"))
    assert side["verdict"] == "approve" and side["scope"] == "runner-audit"
    assert side["reviewer_delegation"].startswith("deleg-review-")
    assert len(side["authors"]) == 1 and side["authors"][0].startswith("deleg-impl-")
    # reviewed commit — коммит dev-стадии (HEAD до ревью), не коммит ревью
    subj = subprocess.run(
        ["git", "-C", str(repo), "show", "-s", "--format=%s",
         side["reviewed_commit_sha"]], capture_output=True, text=True).stdout
    assert "vrd-pkg/impl" in subj
    assert side["diff_digest"]
    # рядом с review-файлом sidecar не кладется (его читают flow_transition/J10)
    assert not (repo / (REVIEW + ".provenance.json")).exists()
    # J65.4b (TC-J65-PRV-004): в закоммиченном review-файле — штамп раннера
    # с делегацией стадии ревью (доказательство независимости для J10)
    committed = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{REVIEW}"],
        capture_output=True, text=True).stdout
    assert f"Reviewer-Delegation: {side['reviewer_delegation']}" in committed


def test_runner_return_records_and_stops(tmp_path, monkeypatch, capsys):
    """TC-J65-VRD-005"""
    repo, rc, _ = _run(tmp_path, monkeypatch, "## Вердикт: Вернуть\n")
    assert rc == 2
    assert "return — ЖДУ ПМ: возврат ревью" in capsys.readouterr().err
    side = json.loads(_records(repo)[0].read_text(encoding="utf-8"))
    assert side["verdict"] == "return"


def test_runner_stale_commit_stops(tmp_path, monkeypatch, capsys):
    """TC-J65-VRD-006"""
    repo, rc, _ = _run(tmp_path, monkeypatch,
                       "## Вердикт: approve\nCommit: 0000000\n")
    assert rc == 2
    assert "STALE" in capsys.readouterr().err
    assert _records(repo) == []


def test_runner_no_verdict_stops(tmp_path, monkeypatch, capsys):
    """TC-J65-VRD-007"""
    repo, rc, _ = _run(tmp_path, monkeypatch, "Вердикт: Одобрить\n")
    assert rc == 2
    assert "нет вердикта" in capsys.readouterr().err
    assert _records(repo) == []


def test_pm_bounds_uses_shared_parser():
    """TC-J65-VRD-008"""
    ok = "## Вердикт: Одобрить\n**Дата:** 2026-11-06\n"
    assert pm_bounds_check.review_approve_date(ok) == "2026-11-06"
    assert pm_bounds_check.review_approve_date(
        "## Вердикт: Не одобрить\nДата: 2026-11-06\n") is None



def test_gate_stage_verdict_no_stale(tmp_path):
    """TC-J65-VRD-009: gate-стадия не знает «коммит до ревью» — строка
    Commit: на более ранний коммит не дает ложного STALE."""
    f = tmp_path / "r.md"
    f.write_text("## Вердикт: approve\nCommit: 1234567\n", encoding="utf-8")
    assert pr.check_verdict(tmp_path, {"file": "r.md"}) == ("approve", None)
    value, problem = pr.check_verdict(tmp_path, {"file": "r.md"}, "abcdef0123")
    assert value == "approve" and "STALE" in problem


def test_heading_value_on_next_line():
    """TC-J65-VRD-010: «## Вердикт» и значение следующей строкой — формат,
    принятый в проектах (19 реальных файлов), читается."""
    assert flow_check.parse_verdict("## Вердикт\n\n**approve**\n") == "approve"
    assert flow_check.parse_verdict("### Вердикт\nВернуть\n") == "return"
