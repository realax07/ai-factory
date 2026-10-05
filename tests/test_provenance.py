# -*- coding: utf-8 -*-
"""Тесты provenance review в flow_transition.py (поставка 05: строгий режим).

Приемка ТЗ 05 (Provenance review):
- ложный approve для другого SHA/task/change отклоняется (DENY);
- после нового коммита прежний approve устаревает (STALE_EVIDENCE);
- автор ревьюит себя → DENY/WRONG_ROLE;
- легаси-review без sidecar: legacy evidence + UNKNOWN, новый автоматический
  merge не разрешается, старые merge задним числом не объявляются незаконными;
- согласованный sidecar с task/change/SHA и независимой ролью → ALLOW.

Fixture-репозитории и sidecar в tmp_path; реальный ~/.hermes не используется.

Трассировка: TC-PRV-001...TC-PRV-014 (спека deterministic-flow, Requirement
«Provenance review (строгий режим)»; ТЗ 05; контракт §9).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_state  # noqa: E402
import flow_transition as ft  # noqa: E402
import gate_runner as gr  # noqa: E402


# --------------------------------------------------------------- helpers


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init") -> str:
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


REQ_APPROVED = "# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | История: r1\n\n## Описание\n...\n"
TASKS = """# Tasks

- [x] 1.1 готово
- [ ] 1.2 вторая
"""


def make_repo(tmp_path: Path, change_id: str = "add-widget") -> Path:
    repo = tmp_path / "proj"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    write(repo, "requirements.md", REQ_APPROVED)
    write(repo, f"openspec/changes/{change_id}/proposal.md", "# p\n")
    write(repo, f"openspec/changes/{change_id}/design.md", "# d\n")
    write(repo, f"openspec/changes/{change_id}/tasks.md", TASKS)
    write(repo,
          f"openspec/changes/{change_id}/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    write(repo, "sdd.md", "# SDD\n")
    write(repo, "openspec/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    commit_all(repo)
    return repo


def add_review_with_sidecar(repo: Path, change_id: str, task_ids: list[str],
                            sha: str, verdict: str = "approve",
                            author: str = "deleg_author",
                            reviewer: str = "deleg_reviewer",
                            rev: int = 1,
                            diff_digest: str | None = None) -> Path:
    """Review-файл (человекочитаемый) + sidecar по формату gate_runner."""
    name = f"review-{rev:03d}-{'-'.join(task_ids)}.md"
    rf = repo / "code-reviews" / change_id / name
    write(repo, str(rf.relative_to(repo)),
          f"# Review\n\n## Вердикт: {verdict}\n\nДата: 2026-10-02\n")
    _, payload = gr.write_review_provenance(
        rf, "proj", change_id, task_ids, author, reviewer, sha, verdict,
        diff_digest=diff_digest)
    return rf


def snapshot_for(repo: Path, task_id: str = "1.1") -> dict:
    return flow_state.inspect(
        repo_arg=str(repo), project="proj", flow=1,
        change_id="add-widget", task_id=task_id,
        registry=str(repo.parent / "reg.json"),
    )


def accept_review_action(task_id: str = "1.1") -> ft.ActionRequest:
    return ft.ActionRequest(actor_role="code_reviewer",
                            requested_action="accept_review", task_id=task_id)


def merge_action(task_id: str = "1.1") -> ft.ActionRequest:
    return ft.ActionRequest(actor_role="dev_lead",
                            requested_action="merge_task", task_id=task_id)


def has_code(d: ft.Decision, code: str) -> bool:
    return code in d.blocking_reasons


def sidecar_now(repo: Path, change_id: str = "add-widget",
                task_ids: list[str] | None = None) -> str:
    """Валидный sidecar для ТЕКУЩЕГО HEAD (включая digest диффа HEAD)."""
    head = git(repo, "rev-parse", "HEAD")
    diff = ft._git_diff_for_head({"scope": {"repo": str(repo)}}, head)
    return add_review_with_sidecar(
        repo, change_id, task_ids or ["1.1"], head,
        diff_digest=ft._sha256_text(diff)).name


# ------------------------------------------- TC-PRV-001: честный ALLOW


class TestStrictAllow:
    def test_matching_sidecar_allows_accept(self, tmp_path):
        """Согласованный sidecar: task/change/SHA/роль совпали → ALLOW
        (strict mode больше не UNKNOWN)."""
        repo = make_repo(tmp_path)
        sidecar_now(repo)
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "ALLOW", d.details
        assert d.allowed is True

    def test_matching_sidecar_merge_only_external_marker(self, tmp_path):
        repo = make_repo(tmp_path)
        sidecar_now(repo)
        d = ft.check_action(snapshot_for(repo), merge_action())
        # merge: provenance чиста; остается только внешняя пометка
        assert d.status == "UNKNOWN"
        assert not has_code(d, ft.STALE_EVIDENCE)
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)


# ------------------------------------- TC-PRV-002: ложный/чужой approve


class TestWrongBinding:
    def test_approve_other_sha_stale(self, tmp_path):
        """Приемка ТЗ 05: approve для SHA X, появился коммит Y → DENY
        STALE_EVIDENCE; после нового commit прежний approve устаревает."""
        repo = make_repo(tmp_path)
        old_sha = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "add-widget", ["1.1"], old_sha)
        # новый коммит после approve
        write(repo, "extra.txt", "new work\n")
        commit_all(repo, "new work after approve")
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "DENY"
        assert has_code(d, ft.STALE_EVIDENCE)
        assert d.allowed is False

    def test_approve_other_task_rejected(self, tmp_path):
        """Ложный approve для другой задачи отклоняется (ТЗ 05): sidecar
        под 1.2 не является evidence для 1.1 → нет approve для 1.1 → DENY."""
        repo = make_repo(tmp_path)
        sidecar_now(repo, task_ids=["1.2"])
        d = ft.check_action(snapshot_for(repo, "1.1"),
                            accept_review_action("1.1"))
        assert d.status == "DENY"
        assert d.allowed is False
        assert has_code(d, ft.INVALID_GATE)  # approve 1.1 отсутствует
        assert any("1.1" in x for x in d.details)

    def test_approve_other_change_rejected(self, tmp_path):
        """Approve чужого change отклоняется (ТЗ 05): sidecar из
        code-reviews/other-change/ не evidence для add-widget —
        approve для этого change отсутствует → DENY/MISSING_INPUT."""
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "other-change", ["1.1"], head)
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)  # code-reviews/add-widget пуст
        assert d.allowed is False

    def test_diff_digest_mismatch_stale(self, tmp_path):
        """ digest-проверка: sidecar с чужим diff_digest → STALE_EVIDENCE."""
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "add-widget", ["1.1"], head,
                                diff_digest="f" * 64)
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert has_code(d, ft.STALE_EVIDENCE)
        assert any("diff_digest" in x for x in d.details)

    def test_missing_sha_in_sidecar_unknown(self, tmp_path):
        """Sidecar без reviewed_commit_sha — provenance неполна → UNKNOWN,
        не разрешение."""
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "add-widget", ["1.1"], head)
        # затираем SHA в sidecar
        pf = next((repo / "code-reviews" / "add-widget").glob(
            "review-*.provenance.json"))
        data = json.loads(pf.read_text(encoding="utf-8"))
        data["reviewed_commit_sha"] = ""
        pf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.MISSING_INPUT)

    def test_foreign_task_sidecar_denied_not_unknown(self, tmp_path):
        """review-005 M1: sidecar ЧУЖОЙ задачи — единственный под change →
        DENY «approve другой задачи», а не тихий legacy-UNKNOWN."""
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        diff = ft._git_diff_for_head({"scope": {"repo": str(repo)}}, head)
        add_review_with_sidecar(repo, "add-widget", ["1.2"], head,
                                diff_digest=ft._sha256_text(diff))
        d = ft.check_action(snapshot_for(repo, "1.1"),
                            accept_review_action("1.1"))
        assert d.status == "DENY", d.details
        assert d.allowed is False
        assert has_code(d, ft.MISSING_INPUT)
        assert any("не покрывают задачу 1.1" in x for x in d.details)
        assert any("1.2" in x for x in d.details)
        # это НЕ legacy-ветка: sidecar назван и виден
        assert not any("legacy evidence" in x for x in d.details)

    def test_missing_diff_digest_unknown_not_allow(self, tmp_path):
        """review-005 M3: sidecar с task/change/SHA и независимой ролью,
        но БЕЗ diff_digest → UNKNOWN (не ALLOW): digest — единственная
        защита от approve «того же SHA, другой content»."""
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "add-widget", ["1.1"], head,
                                diff_digest=None)
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "UNKNOWN", d.details
        assert d.allowed is False
        assert has_code(d, ft.MISSING_INPUT)
        assert any("diff_digest" in x for x in d.details)

    def test_missing_diff_digest_merge_not_allowed(self, tmp_path):
        """M3 на merge_task: неполная провенанс не разрешает merge."""
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "add-widget", ["1.1"], head,
                                diff_digest=None)
        d = ft.check_action(snapshot_for(repo), merge_action())
        assert d.status != "ALLOW"
        assert has_code(d, ft.MISSING_INPUT)


# ----------------------------------------- TC-PRV-003: независимость роли


class TestRoleIndependence:
    def test_self_review_denied(self, tmp_path):
        """Спека: author delegation == reviewer delegation → DENY
        WRONG_ROLE."""
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "add-widget", ["1.1"], head,
                                author="deleg_same", reviewer="deleg_same")
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "DENY"
        assert has_code(d, ft.WRONG_ROLE)

    def test_self_review_merge_denied(self, tmp_path):
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "add-widget", ["1.1"], head,
                                author="deleg_same", reviewer="deleg_same")
        d = ft.check_action(snapshot_for(repo), merge_action())
        assert d.status == "DENY"
        assert has_code(d, ft.WRONG_ROLE)

    def test_wrong_actor_role_still_denied(self, tmp_path):
        """Независимость делегаций в sidecar не отменяет роль исполнителя."""
        repo = make_repo(tmp_path)
        sidecar_now(repo)
        d = ft.check_action(snapshot_for(repo),
                            ft.ActionRequest(actor_role="dev",
                                             requested_action="accept_review",
                                             task_id="1.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.WRONG_ROLE)


# ------------------------------------ TC-PRV-004: legacy compatibility


class TestLegacyCompat:
    def test_legacy_review_unknown_not_allow(self, tmp_path):
        """ТЗ 05: старые review без sidecar — legacy evidence, новый
        автоматический merge НЕ разрешается (UNKNOWN)."""
        repo = make_repo(tmp_path)
        write(repo, "code-reviews/add-widget/review-001-1.1.md",
              "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "UNKNOWN"
        assert d.allowed is False
        assert has_code(d, ft.STALE_EVIDENCE)
        assert any("legacy evidence" in x for x in d.details)
        assert "provenance.sidecar" in d.requirements_checked

    def test_legacy_review_merge_not_auto_merged(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "code-reviews/add-widget/review-001-1.1.md",
              "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        d = ft.check_action(snapshot_for(repo), merge_action())
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.STALE_EVIDENCE)
        assert any("legacy evidence" in x for x in d.details)

    def test_historic_merges_not_outlawed(self, tmp_path):
        """ТЗ 05: старые merge не объявляются незаконными задним числом —
        compatibility не выдает DENY по самому факту отсутствия sidecar."""
        repo = make_repo(tmp_path)
        write(repo, "code-reviews/add-widget/review-001-1.1.md",
              "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        # UNKNOWN (compat), не DENY: легаси ≠ нарушение
        assert d.status != "DENY"
        assert not has_code(d, ft.WRONG_ROLE)

    def test_recording_sidecar_upgrades_legacy(self, tmp_path):
        """Дописанный к легаси-review sidecar поднимает UNKNOWN → ALLOW."""
        repo = make_repo(tmp_path)
        rf = repo / "code-reviews" / "add-widget" / "review-001-1.1.md"
        write(repo, str(rf.relative_to(repo)), "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        d0 = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d0.status == "UNKNOWN"
        head = git(repo, "rev-parse", "HEAD")
        diff = ft._git_diff_for_head({"scope": {"repo": str(repo)}}, head)
        gr.write_review_provenance(rf, "proj", "add-widget", ["1.1"],
                                   "deleg_a", "deleg_b", head, "approve",
                                   diff_digest=ft._sha256_text(diff))
        d1 = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d1.status == "ALLOW"


# ------------------------------------- TC-PRV-005: битые входы provenance


class TestBrokenInputs:
    def test_corrupt_sidecar_unknown(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "code-reviews/add-widget/review-001-1.1.md",
              "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        write(repo,
              "code-reviews/add-widget/review-001-1.1.md.provenance.json",
              "{not json")
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.AMBIGUOUS_STATE)

    def test_unknown_schema_unknown(self, tmp_path):
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "add-widget", ["1.1"], head)
        pf = next((repo / "code-reviews" / "add-widget").glob(
            "review-*.provenance.json"))
        data = json.loads(pf.read_text(encoding="utf-8"))
        data["schema_version"] = "review-provenance/99"
        pf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.AMBIGUOUS_STATE)

    def test_return_verdict_sidecar_not_approve_evidence(self, tmp_path):
        """Sidecar с verdict=return — это не approve: return-вердикт
        не проходит как approve-evidence (_approvals_for_task)."""
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        add_review_with_sidecar(repo, "add-widget", ["1.1"], head,
                                verdict="return")
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert has_code(d, ft.INVALID_GATE)  # нет approve для задачи
        assert d.status == "DENY"


# ------------------------------------------- TC-PRV-006: CLI record-review


class TestCliRecordReview:
    def test_cli_record_review_writes_sidecar(self, tmp_path):
        repo = make_repo(tmp_path)
        rf = repo / "code-reviews" / "add-widget" / "review-001-1.1.md"
        write(repo, str(rf.relative_to(repo)), "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        head = git(repo, "rev-parse", "HEAD")
        diff = ft._git_diff_for_head({"scope": {"repo": str(repo)}}, head)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "record-review",
             "--review-path", str(rf), "--project", "proj",
             "--change", "add-widget", "--tasks", "1.1",
             "--author-delegation", "deleg_a",
             "--reviewer-delegation", "deleg_b",
             "--commit", head, "--verdict", "approve",
             "--diff-digest", ft._sha256_text(diff), "--json"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert Path(payload["sidecar_path"]).is_file()
        # строгая проверка по записанному sidecar проходит
        d = ft.check_action(snapshot_for(repo), accept_review_action())
        assert d.status == "ALLOW"

    def test_cli_record_review_without_diff_digest_exit2(self, tmp_path):
        """review-005 M3: sidecar без diff_digest через record-review не
        пишется — digest обязателен (M3-негатив на уровне CLI)."""
        repo = make_repo(tmp_path)
        rf = repo / "code-reviews" / "add-widget" / "review-001-1.1.md"
        write(repo, str(rf.relative_to(repo)), "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        head = git(repo, "rev-parse", "HEAD")
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "record-review",
             "--review-path", str(rf), "--project", "proj",
             "--change", "add-widget", "--tasks", "1.1",
             "--author-delegation", "deleg_a",
             "--reviewer-delegation", "deleg_b",
             "--commit", head, "--verdict", "approve"],
            capture_output=True, text=True,
        )
        assert r.returncode == 2
        assert "diff-digest" in r.stderr
        assert not list((repo / "code-reviews" / "add-widget").glob(
            "*.provenance.json"))

    def test_cli_record_review_verdict_mismatch_exit2(self, tmp_path):
        """review-005 m2: sidecar-approve поверх .md с вердиктом RETURN
        не записывается — машинное и человеческое доказательства
        не расходятся."""
        repo = make_repo(tmp_path)
        rf = repo / "code-reviews" / "add-widget" / "review-001-1.1.md"
        write(repo, str(rf.relative_to(repo)), "## Вердикт: RETURN\n")
        head = git(repo, "rev-parse", "HEAD")
        diff = ft._git_diff_for_head({"scope": {"repo": str(repo)}}, head)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "record-review",
             "--review-path", str(rf), "--project", "proj",
             "--change", "add-widget", "--tasks", "1.1",
             "--author-delegation", "deleg_a",
             "--reviewer-delegation", "deleg_b",
             "--commit", head, "--verdict", "approve",
             "--diff-digest", ft._sha256_text(diff)],
            capture_output=True, text=True,
        )
        assert r.returncode == 2
        assert "вердикт" in r.stderr
        assert not list((repo / "code-reviews" / "add-widget").glob(
            "*.provenance.json"))

    def test_cli_record_review_unknown_sha_exit2(self, tmp_path):
        """review-005 m2: reviewed_commit_sha, отсутствующий в репо,
        отклоняется (--repo задан)."""
        repo = make_repo(tmp_path)
        rf = repo / "code-reviews" / "add-widget" / "review-001-1.1.md"
        write(repo, str(rf.relative_to(repo)), "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        head = git(repo, "rev-parse", "HEAD")
        diff = ft._git_diff_for_head({"scope": {"repo": str(repo)}}, head)
        bogus = "0" * 40
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "record-review",
             "--review-path", str(rf), "--project", "proj",
             "--change", "add-widget", "--tasks", "1.1",
             "--author-delegation", "deleg_a",
             "--reviewer-delegation", "deleg_b",
             "--commit", bogus, "--verdict", "approve",
             "--diff-digest", ft._sha256_text(diff), "--repo", str(repo)],
            capture_output=True, text=True,
        )
        assert r.returncode == 2
        assert "не найден" in r.stderr

    def test_cli_record_review_bad_input_exit2(self, tmp_path):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "record-review",
             "--review-path", "/nonexistent.md", "--project", "p",
             "--change", "a-b", "--tasks", "1.1",
             "--author-delegation", "a", "--reviewer-delegation", "b",
             "--commit", "x", "--verdict", "approve",
             "--diff-digest", "d" * 64],
            capture_output=True, text=True,
        )
        assert r.returncode == 2
        assert "GATE-RUNNER-ERROR" in r.stderr
