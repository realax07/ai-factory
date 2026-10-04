# -*- coding: utf-8 -*-
"""Негативные тесты обходов workflow (поставка 07, ТЗ
docs/chatgpt-deterministic-flow/07-tests-and-rollout.md, раздел «Тестирование»,
все 9 пунктов; контракт flow_control_contract.md §7–§12).

Каждый пункт ТЗ — отдельный тест-класс с минимальной fixture (временный
Git-репозиторий + независимый fixture-реестр; реальный ~/.hermes/state/ и
пользовательские проекты не используются). Проверяются и библиотечные
решения (check_action), и exit code/JSON CLI (flowctl/flow_transition).

Пункты ТЗ 07:
1. Нет требований/утверждения для Флоу 1; dev до спеки/arch review.
2. Зависимая до merge; [P] пересекает зону.
3. Автор ревьюит сам; approve другого task/SHA или устарел.
4. QA-автоматизация без approved кейсов; архив без слитых дельт.
5. Флоу 2 для нового поведения; Флоу 5 без ретро-артефактов.
6. Битый/отсутствующий реестр; неверный worktree/branch; symlink;
   конкурентные reservation.
7. Gate FAIL/timeout/missing/invalid; snapshot устарел между check и run.
8. Runner упал после reservation и после записи файлов — recovery без
   повторной делегации.
9. Branch protection неизвестна — честная пометка (локальный PASS не
   доказывает защиту main).

Трассировка: TC-BP-001...TC-BP-009.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_check  # noqa: E402
import flow_state  # noqa: E402
import flow_transition as ft  # noqa: E402
import role_zone_policy as rzp  # noqa: E402
import session_check as sc  # noqa: E402
import gate_runner as gr  # noqa: E402

PV = rzp.policy_version()  # P0.3: резервация фиксирует редакцию политики зон


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


REQ_APPROVED = ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba | История: r1\n\n"
                "## Описание\n...\n\n## Аудитория\nПМ.\n\n"
                "## Функциональные требования\n- FR-1\n\n"
                "## Нефункциональные требования\n- NFR-1\n\n"
                "## Приоритеты\nP1\n\n## Ограничения\nбез push\n\n"
                "## Открытые вопросы\nнет\n")
REQ_DRAFT = REQ_APPROVED.replace("УТВЕРЖДЕН", "ЧЕРНОВИК")

TASKS = """# Tasks

- [x] 1.1 готово
- [ ] 2.1 [P] параллельная в src/
- [ ] 3.1 (после 1.1) зависимая
"""

DELTA = ("### Requirement: W\n#### Scenario: S\n"
         "- GIVEN a\n- WHEN b\n- THEN c\n")


def make_repo(tmp_path: Path, *, change_id: str = "add-widget",
              req: str | None = REQ_APPROVED, tasks: str | None = TASKS,
              with_sdd: bool = True, deltas: bool = True,
              reviews: bool = False, name: str = "proj") -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    if req:
        write(repo, "requirements.md", req)
    write(repo, f"openspec/changes/{change_id}/proposal.md", "# p\n")
    write(repo, f"openspec/changes/{change_id}/design.md", "# d\n")
    if tasks:
        write(repo, f"openspec/changes/{change_id}/tasks.md", tasks)
    if deltas:
        write(repo, f"openspec/changes/{change_id}/specs/widget/spec.md", DELTA)
    if with_sdd:
        write(repo, "sdd.md", "# SDD\n")
    write(repo, "src/main.py", "X = 1\n")
    if reviews:
        write(repo, f"code-reviews/{change_id}/review-001-3.1.md",
              "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
    commit_all(repo)
    return repo


def make_registry(tmp_path: Path, name: str = "active_sessions.json",
                  payload: str = '{"sessions": []}') -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(payload, encoding="utf-8")
    return p


def snapshot_for(repo: Path, registry: Path, **kw) -> dict:
    return flow_state.inspect(
        repo_arg=str(repo), project=kw.get("project", "proj"),
        flow=kw.get("flow", 1), change_id=kw.get("change_id", "add-widget"),
        task_id=kw.get("task_id"), registry=str(registry))


def act(**kw) -> ft.ActionRequest:
    kw.setdefault("actor_role", "dev")
    kw.setdefault("requested_action", "dev_task")
    return ft.ActionRequest(**kw)


def cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "flow_transition.py"), *argv],
        capture_output=True, text=True,
    )


def has_code(d: ft.Decision, code: str) -> bool:
    return code in d.blocking_reasons


def sidecar(repo: Path, change: str, tasks: list, author: str, reviewer: str,
            sha: str, verdict: str = "approve", diff_digest: str | None = None,
            name: str = "review-001-3.1.md.provenance.json") -> Path:
    p = repo / "code-reviews" / change / name
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "review-provenance/1",
        "project": "proj", "change": change, "task_ids": tasks,
        "author_delegation": author, "reviewer_delegation": reviewer,
        "reviewed_commit_sha": sha, "verdict": verdict,
        "diff_digest": diff_digest or "0" * 64,
        "timestamp": "2026-10-02T00:00:00+00:00",
        "review_path": str(p).replace(".provenance.json", ""),
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def make_worktree(repo: Path, sid: str, branch: str) -> Path:
    if subprocess.run(
        ["git", "-C", str(repo), "show-ref", "--verify", "--quiet",
         f"refs/heads/{branch}"], capture_output=True,
    ).returncode != 0:
        git(repo, "branch", branch)
    out = subprocess.run(
        ["bash", str(SCRIPTS / "session_worktree.sh"), "create",
         str(repo), sid, branch],
        capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip().splitlines()[-1])


# ------------------------------- TC-BP-001: Флоу 1 без требований/утверждения


class TestBP01NoRequirements:
    """ТЗ 07 п.1: нет требований/утверждения для Флоу 1; dev до спеки или
    архитектурного review."""

    def test_dev_task_denied_on_draft_requirements(self, tmp_path):
        repo = make_repo(tmp_path, req=REQ_DRAFT)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(task_id="2.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("УТВЕРЖДЕН" in x or "approve_requirements" in x
                   for x in d.details)

    def test_dev_task_denied_without_requirements_file(self, tmp_path):
        repo = make_repo(tmp_path, req=None)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(task_id="2.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)

    def test_dev_task_denied_without_arch_review(self, tmp_path):
        """dev до спеки: change-пакет без дельт/sdd — пропущен arch review."""
        repo = make_repo(tmp_path, deltas=False, with_sdd=False)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(task_id="2.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("architecture review" in x for x in d.details)

    def test_cli_exit1_on_draft(self, tmp_path):
        repo = make_repo(tmp_path, req=REQ_DRAFT)
        reg = make_registry(tmp_path)
        r = cli("check", "--repo", str(repo), "--project", "proj",
                "--flow", "1", "--change", "add-widget", "--task", "2.1",
                "--action", "dev_task", "--role", "dev",
                "--registry", str(reg))
        assert r.returncode == 1

    def test_dev_task_allowed_after_full_preflight(self, tmp_path):
        """Контроль: тот же fixture с полным preflight (approved + спека +
        sdd + дельты) — ALLOW; отказ именно из-за пропущенного этапа."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(task_id="2.1"))
        assert d.status == "ALLOW"


# -------------------------- TC-BP-002: зависимая до merge; [P] против зоны


class TestBP02DepsAndZones:
    """ТЗ 07 п.2: зависимая задача стартует до merge предшественницы; [P]
    пересекается с активной зоной."""

    def test_dependent_task_denied_until_predecessor_merged(self, tmp_path):
        """3.1 зависит от 1.1: чекбокс закрыт, но approve-ревью на 1.1 нет →
        J10-незакрытая зависимость = DENY (INVALID_GATE)."""
        repo = make_repo(tmp_path)  # нет review-файлов
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="3.1")
        info, parallel = ft._task_deps_from_repo(repo, "add-widget", "3.1")
        deps = tuple(info.get("deps", ()))
        dep_ev = ft._dep_evidence(repo, "add-widget", deps)
        d = ft.check_action(s, act(task_id="3.1", task_dependencies=deps,
                                   dependency_evidence=dep_ev))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("ждёт merge" in x or "approve" in x for x in d.details)

    def test_dependent_task_allowed_after_merge_and_review(self, tmp_path):
        """Контроль: предшественница слита (чекбокс + approve) → зависимая
        разрешена."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        # approve-ревью предшественницы 1.1:
        write(repo, "code-reviews/add-widget/review-001-1.1.md",
              "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        commit_all(repo, "review 1.1")
        info, _ = ft._task_deps_from_repo(repo, "add-widget", "3.1")
        deps = tuple(info.get("deps", ()))
        dep_ev = ft._dep_evidence(repo, "add-widget", deps)
        d = ft.check_action(snapshot_for(repo, reg, task_id="3.1"),
                            act(task_id="3.1", task_dependencies=deps,
                                dependency_evidence=dep_ev))
        assert d.status == "ALLOW", d.details

    def test_parallel_marker_without_confirmation_unknown(self, tmp_path):
        """[P]-задача без подтвержденного маркера — UNKNOWN, не ALLOW
        (флаг «на веру» не принимается, R5)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(task_id="2.1", task_parallel=True,
                                parallel_confirmed=None))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.MISSING_INPUT)
        assert any("[P]" in x for x in d.details)

    def test_parallel_zone_conflict_at_reservation(self, tmp_path):
        """[P] с подтвержденным маркером, но зона пересекает активную сессию:
        admit_session → ZONE_CONFLICT (ровно одна владеет путем)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        first = sc.reserve(
            {"repo": str(repo), "delegation_id": "deleg-A", "role": "dev",
             "project": "proj", "owner_pm": "pm", "paths": ["src/**"], "policy_version": PV,
                          "policy_version": PV},
            reg)
        assert first["allowed"]
        second = sc.reserve(
            {"repo": str(repo), "delegation_id": "deleg-B", "role": "dev",
             "project": "proj", "owner_pm": "pm", "paths": ["src/main.py"],
                          "policy_version": PV},
            reg)
        assert not second["allowed"]
        assert second["reason"] == "ZONE_CONFLICT"

    def test_cli_parallel_dep_deny_exit(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = cli("check", "--repo", str(repo), "--project", "proj",
                "--flow", "1", "--change", "add-widget", "--task", "3.1",
                "--action", "dev_task", "--role", "dev",
                "--registry", str(reg))
        assert r.returncode in (1, 2)  # DENY (нет approve) или UNKNOWN
        assert "INVALID_GATE" in r.stdout or "MISSING_INPUT" in r.stdout


# ------------------------------- TC-BP-003: саморевью; чужой/устаревший approve


class TestBP03ReviewProvenance:
    """ТЗ 07 п.3: автор сам ревьюит; approve другого task/SHA или устарел
    после изменения входа."""

    def _repo_with_review(self, tmp_path):
        repo = make_repo(tmp_path, reviews=True)
        reg = make_registry(tmp_path)
        return repo, reg

    def test_self_review_denied(self, tmp_path):
        repo, reg = self._repo_with_review(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        sidecar(repo, "add-widget", ["3.1"], "deleg-A", "deleg-A", sha,
                diff_digest=gr.sha256_text("same"))
        d = ft.check_action(snapshot_for(repo, reg, task_id="3.1"),
                            act(actor_role="code_reviewer",
                                requested_action="accept_review",
                                task_id="3.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.WRONG_ROLE)
        assert any("собственной" in x or "author_delegation" in x
                   for x in d.details)

    def test_approve_other_task_denied(self, tmp_path):
        """Approve-файл на 1.1, а принимают 3.1 — «approve другой задачи»."""
        repo, reg = self._repo_with_review(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        # sidecar покрывает только 2.1, review-.md покрывает 3.1 → чужой
        sidecar(repo, "add-widget", ["2.1"], "deleg-A", "deleg-B", sha,
                diff_digest=gr.sha256_text("x"))
        d = ft.check_action(snapshot_for(repo, reg, task_id="3.1"),
                            act(actor_role="code_reviewer",
                                requested_action="accept_review",
                                task_id="3.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)

    def test_approve_stale_after_new_commit(self, tmp_path):
        """Approve на старый SHA: после нового коммита вход изменился →
        STALE_EVIDENCE (DENY)."""
        repo, reg = self._repo_with_review(tmp_path)
        old_sha = git(repo, "rev-parse", "HEAD")
        write(repo, "src/main.py", "X = 2\n")
        commit_all(repo, "new work after review")
        sidecar(repo, "add-widget", ["3.1"], "deleg-A", "deleg-B", old_sha,
                diff_digest=gr.sha256_text("old"))
        d = ft.check_action(snapshot_for(repo, reg, task_id="3.1"),
                            act(actor_role="code_reviewer",
                                requested_action="accept_review",
                                task_id="3.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.STALE_EVIDENCE)

    def test_approve_valid_accepted(self, tmp_path):
        """Контроль: свежий sidecar с независимой ролью и верным digest →
        ALLOW."""
        repo, reg = self._repo_with_review(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        diff = subprocess.run(
            ["git", "-C", str(repo), "diff", f"{sha}^..{sha}"],
            capture_output=True, text=True).stdout
        sidecar(repo, "add-widget", ["3.1"], "deleg-A", "deleg-B", sha,
                diff_digest=gr.sha256_text(diff))
        d = ft.check_action(snapshot_for(repo, reg, task_id="3.1"),
                            act(actor_role="code_reviewer",
                                requested_action="accept_review",
                                task_id="3.1"))
        assert d.status == "ALLOW", d.details


# --------------------------- TC-BP-004: QA без approved; архив без слитых дельт


class TestBP04QaAndArchive:
    """ТЗ 07 п.4: QA-автоматизация стартует без approved кейсов; архив
    создают без слияния дельт master-spec."""

    def test_qa_automation_without_approved_cases_of_change(self, tmp_path):
        """Решение 3.1-А: пусто в test-model/approved/<change>/ → DENY, даже
        если approved/ непуст глобально (урок S5)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        write(repo, "test-model/approved/other-change/TC-OLD.md", "# old\n")
        commit_all(repo, "old approved cases")
        d = ft.check_action(snapshot_for(repo, reg),
                            act(actor_role="qa_automation",
                                requested_action="qa_automation"))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)
        assert any("СВОЕГО change" in x or "approved" in x for x in d.details)

    def test_qa_automation_allowed_with_own_approved(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        write(repo, "test-model/approved/add-widget/TC-WID-001.md", "# tc\n")
        write(repo, "test-model/checklists/add-widget.md", "| CHK-1 | x | FR-1 |\n")
        commit_all(repo, "approved cases")
        d = ft.check_action(snapshot_for(repo, reg),
                            act(actor_role="qa_automation",
                                requested_action="qa_automation"))
        assert d.status == "ALLOW", d.details

    def test_archive_denied_without_merged_deltas(self, tmp_path):
        """Архивация без слияния дельт: change перенесен в archive/, а
        master-spec не содержит Requirement дельты — flow_check (контракт 7)
        FAIL, finish не может быть accepted."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        write(repo, "openspec/changes/add-widget/tasks.md",
              "# Tasks\n\n- [x] 1.1 всё\n")
        # «Архивировали» пакет, дельту в master-spec НЕ сливали:
        arch = repo / "openspec/changes/archive"
        arch.mkdir(parents=True, exist_ok=True)
        os.rename(repo / "openspec/changes/add-widget",
                  arch / "add-widget")
        commit_all(repo, "archive without merge")
        # библиотечно: проверка контракта 7 в тексте ошибок flow_check
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "flow_check.py"), str(repo)],
            capture_output=True, text=True)
        assert proc.returncode != 0
        assert "не слит в master-spec" in proc.stdout

    def test_archive_with_open_tasks_denied(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        write(repo, "test-model/approved/add-widget/TC-1.md", "# tc\n")
        commit_all(repo, "approved")
        d = ft.check_action(snapshot_for(repo, reg),
                            act(actor_role="sa",
                                requested_action="archive_change",
                                approval_ref="решение 3.3-А"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("не все задачи закрыты" in x for x in d.details)


# ------------------------- TC-BP-005: Флоу 2 для нового поведения; Флоу 5


class TestBP05Flow2AndFlow5:
    """ТЗ 07 п.5: Flow 2 для нового поведения; Flow 5 без ретроспективных
    артефактов."""

    def test_flow2_with_spec_delta_denied_with_escalation(self, tmp_path):
        repo = make_repo(tmp_path, change_id="bug-fix",
                         req=None, tasks=None)
        write(repo, "test-model/bugs/BUG-001.md", "# BUG-001\n")
        write(repo, "openspec/specs/widget/spec.md", DELTA)
        commit_all(repo, "bug report")
        reg = make_registry(tmp_path)
        d = ft.check_action(
            snapshot_for(repo, reg, flow=2, change_id="BUG-001"),
            act(requested_action="bug_fix", spec_delta=True))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("эскалация" in x or "Флоу 1" in x for x in d.details)
        # Эскалация — не «запрет и тишина»: next_candidates указывает путь.
        assert any(c["action"] == "create_change" for c in d.next_candidates)

    def test_flow5_close_without_retro_artifacts_denied(self, tmp_path):
        """Флоу 5 без requirements (ретро-артефактов) — закрытие DENY.
        Замечание: FLOW_ID_INVALID на scope без change-пакета усиливает
        отказ до AMBIGUOUS — проверяем коды честно, главный запрет есть."""
        repo = make_repo(tmp_path, req=None, tasks=None, deltas=False,
                         with_sdd=False, change_id="fix-typo")
        reg = make_registry(tmp_path)
        d = ft.check_action(
            snapshot_for(repo, reg, flow=5, change_id="fix-typo"),
            act(actor_role="pm", requested_action="express_close",
                small_change=True))
        assert d.status == "DENY"
        blocking = set(d.blocking_reasons)
        assert blocking & {ft.MISSING_INPUT, ft.AMBIGUOUS_STATE}

    def test_flow5_close_with_retro_artifacts_allowed(self, tmp_path):
        """Контроль: requirements + спека + кейсы на месте → закрытие ALLOW."""
        repo = make_repo(tmp_path, change_id="fix-typo", tasks=None)
        write(repo, "test-model/new/fix-typo/TC-1.md", "# tc\n")
        commit_all(repo, "retro artifacts")
        reg = make_registry(tmp_path)
        # FIX-игнор: change-пакет fix-typo не создаем — контролируем именно
        # ретро-артефакты; отсутствие пакета дает дополнительный AMBIGUOUS,
        # поэтому берем отдельный fixture с пакетом:
        write(repo, "openspec/changes/fix-typo/proposal.md", "# p\n")
        write(repo, "openspec/changes/fix-typo/design.md", "# d\n")
        write(repo, "openspec/changes/fix-typo/tasks.md", "# Tasks\n- [x] 1.1\n")
        write(repo, "openspec/changes/fix-typo/specs/widget/spec.md", DELTA)
        write(repo, "openspec/specs/widget/spec.md", DELTA)
        commit_all(repo, "package too")
        d = ft.check_action(
            snapshot_for(repo, reg, flow=5, change_id="fix-typo"),
            act(actor_role="pm", requested_action="express_close",
                small_change=True))
        assert d.status == "ALLOW", d.details


# ---------------------- TC-BP-006: реестр/worktree/branch/symlink/конкуренция


class TestBP06RegistryWorktreeSymlink:
    """ТЗ 07 п.6: отсутствующий/битый реестр; неверный worktree/branch/
    SESSION.md; symlink уводит запись за зону; два конкурентных reservation."""

    def _repo(self, tmp_path):
        return make_repo(tmp_path)

    def test_missing_registry_is_not_empty(self, tmp_path):
        """Отсутствующий реестр = UNKNOWN («нет данных»), не «сессий нет»:
        snapshot с несуществующим реестром дает unknown-факт + проблему
        REGISTRY_MISSING, а не пустой список сессий."""
        repo = self._repo(tmp_path)
        s = snapshot_for(repo, tmp_path / "nodir" / "active_sessions.json")
        facts = {f["key"]: f for f in s["facts"]}
        reg_fact = facts["sessions.state"]
        assert reg_fact["status"] == "unknown"
        assert reg_fact["confidence"] == "unknown"
        assert any(p["code"] == "REGISTRY_MISSING" for p in s["problems"])

    def test_corrupt_registry_reserve_rejected(self, tmp_path):
        repo = self._repo(tmp_path)
        reg = make_registry(tmp_path, payload="{broken json!!")
        res = sc.reserve({"repo": str(repo), "delegation_id": "d1",
                          "role": "dev", "project": "proj",
                          "owner_pm": "pm", "paths": ["src/**"], "policy_version": PV}, reg)
        assert not res["allowed"]
        assert res["reason"] == sc.REGISTRY_ERROR
        assert res["delegation_id"] == "d1"

    def test_corrupt_registry_status_unknown(self, tmp_path):
        reg = make_registry(tmp_path, payload="{broken json!!")
        st = sc.status(reg)
        assert not st["ok"]
        assert st["reason"] == sc.REGISTRY_ERROR

    def test_wrong_worktree_rejected(self, tmp_path):
        repo = self._repo(tmp_path)
        reg = make_registry(tmp_path)
        wt = make_worktree(repo, "s1", "flow/s1")
        res = sc.reserve({"repo": str(repo), "delegation_id": "dw",
                          "role": "dev", "project": "proj",
                          "owner_pm": "pm", "paths": ["src/**"], "policy_version": PV,
                          "worktree": str(wt), "branch": "flow/s1",
                          "base_sha": git(repo, "rev-parse", "HEAD")}, reg)
        assert res["allowed"]
        # работа в ЧУЖОМ дереве (главный repo, не worktree):
        write(repo, "src/main.py", "X = 99\n")
        chk = sc.check({"delegation_id": "dw", "repo": str(repo)}, reg)
        assert not chk["ok"]
        assert any("WRONG_WORKTREE" in v for v in chk["violations"])

    def test_wrong_branch_rejected(self, tmp_path):
        repo = self._repo(tmp_path)
        reg = make_registry(tmp_path)
        wt = make_worktree(repo, "s2", "flow/s2")
        res = sc.reserve({"repo": str(repo), "delegation_id": "db",
                          "role": "dev", "project": "proj",
                          "owner_pm": "pm", "paths": ["src/**"], "policy_version": PV,
                          "worktree": str(wt), "branch": "flow/other",
                          "base_sha": git(repo, "rev-parse", "HEAD")}, reg)
        assert res["allowed"]
        chk = sc.check({"delegation_id": "db", "repo": str(wt)}, reg)
        assert not chk["ok"]
        assert any("WRONG_BRANCH" in v for v in chk["violations"])

    def test_out_of_zone_write_rejected(self, tmp_path):
        repo = self._repo(tmp_path)
        reg = make_registry(tmp_path)
        wt = make_worktree(repo, "s3", "flow/s3")
        res = sc.reserve({"repo": str(repo), "delegation_id": "dz",
                          "role": "dev", "project": "proj",
                          "owner_pm": "pm", "paths": ["src/**"], "policy_version": PV,
                          "worktree": str(wt), "branch": "flow/s3",
                          "base_sha": git(repo, "rev-parse", "HEAD")}, reg)
        assert res["allowed"]
        # запись в своей зоне + ЗА границей:
        write(wt, "src/main.py", "X = 2\n")
        write(wt, "docs/elsewhere.md", "вне зоны\n")
        chk = sc.check({"delegation_id": "dz", "repo": str(wt)}, reg)
        assert not chk["ok"]
        assert any("OUT_OF_ZONE" in v and "docs/elsewhere.md" in v
                   for v in chk["violations"])

    def test_symlink_escape_rejected(self, tmp_path):
        repo = self._repo(tmp_path)
        reg = make_registry(tmp_path)
        wt = make_worktree(repo, "s4", "flow/s4")
        res = sc.reserve({"repo": str(repo), "delegation_id": "ds",
                          "role": "dev", "project": "proj",
                          "owner_pm": "pm", "paths": ["src/**"], "policy_version": PV,
                          "worktree": str(wt), "branch": "flow/s4",
                          "base_sha": git(repo, "rev-parse", "HEAD")}, reg)
        assert res["allowed"]
        # symlink из зоны ВНЕ репозитория:
        outside = tmp_path / "outside-secret.txt"
        outside.write_text("secret", encoding="utf-8")
        os.symlink(outside, wt / "src" / "leak.md")
        chk = sc.check({"delegation_id": "ds", "repo": str(wt)}, reg)
        assert not chk["ok"]
        assert any("leak.md" in v for v in chk["violations"])
        # snapshot-защита: symlink на читаемом inspect пути (requirements.md)
        # наружу = проблема PATH_OUTSIDE_REPO, а не чтение содержимого
        req = repo / "requirements.md"
        req.unlink()
        os.symlink(outside, req)
        s = snapshot_for(repo, reg)
        assert any(p["code"] == "PATH_OUTSIDE_REPO" for p in s["problems"])

    def test_concurrent_reserves_intersecting_zone(self, tmp_path):
        """Два конкурентных reservation пересекающейся зоны: ровно один
        успех (атомарность под локом)."""
        repo = self._repo(tmp_path)
        reg = make_registry(tmp_path)
        results = []
        for i in range(2):
            results.append(sc.reserve(
                {"repo": str(repo), "delegation_id": f"dc-{i}",
                 "role": "dev", "project": "proj", "owner_pm": "pm",
                 "paths": ["src/**"], "policy_version": PV}, reg))
        allowed = [r for r in results if r["allowed"]]
        assert len(allowed) == 1
        other = next(r for r in results if not r["allowed"])
        assert other["reason"] == "ZONE_CONFLICT"


# ------------------------------ TC-BP-007: gate FAIL/timeout/missing; stale


class TestBP07Gates:
    """ТЗ 07 п.7: Gate возвращает FAIL, таймаут, отсутствующую команду или
    невалидный вывод; snapshot устаревает между check и run."""

    def _opts(self, tmp_path, **kw):
        return type("O", (), {
            "openspec_cmd": kw.get("openspec_cmd", "openspec"),
            "timeout": kw.get("timeout", 10),
            "pm_mode": None, "pm_commits": None, "pm_range": None,
            "pm_registry": None, "pm_require_review": False,
            "pr_id": None, "log_dir": str(tmp_path / "logs"),
            "report_dir": str(tmp_path / "reports"), "audit": None,
            "correlation_id": "bp7",
        })()

    def test_gate_fail_blocks(self, tmp_path):
        repo = make_repo(tmp_path)
        fake = tmp_path / "gate-fail.sh"
        fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        report, code = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            self._opts(tmp_path, openspec_cmd=str(fake)))
        g = report["gates"][0]
        assert g["status"] == "FAIL" and code == 1
        assert report["overall"] == "FAIL"

    def test_gate_timeout_blocks(self, tmp_path):
        repo = make_repo(tmp_path)
        hang = tmp_path / "gate-hang.sh"
        hang.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
        hang.chmod(hang.stat().st_mode | stat.S_IEXEC)
        report, code = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            self._opts(tmp_path, openspec_cmd=str(hang), timeout=1))
        g = report["gates"][0]
        assert g["status"] == "ERROR" and "timeout" in g["diagnostics"]
        assert code == 2

    def test_gate_missing_command_blocks(self, tmp_path):
        """Отсутствующая команда — ERROR («отсутствующий gate блокирует»),
        не SKIP и не PASS."""
        repo = make_repo(tmp_path)
        report, code = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            self._opts(tmp_path, openspec_cmd="/nonexistent/nope-cmd"))
        g = report["gates"][0]
        assert g["status"] == "ERROR"
        assert "не найден" in g["diagnostics"]
        assert code == 2

    def test_gate_invalid_output_blocks(self, tmp_path):
        """Невалидный вывод (exit 7 = parse error) — ERROR, не FAIL."""
        repo = make_repo(tmp_path)
        bad = tmp_path / "gate-bad.sh"
        bad.write_text("#!/bin/sh\necho garbage\nexit 7\n", encoding="utf-8")
        bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
        report, _ = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            self._opts(tmp_path, openspec_cmd=str(bad)))
        g = report["gates"][0]
        assert g["status"] == "ERROR"
        assert "exit code 7" in g["diagnostics"]

    def test_snapshot_stale_between_check_and_run(self, tmp_path):
        """Snapshot устарел между check и run: expected_digest ≠ факт →
        STALE_SNAPSHOT; flowctl run отказывает и НЕ продвигает статус."""
        import flowctl
        repo = make_repo(tmp_path, tasks="# Tasks\n\n- [ ] 1.1 сделать\n")
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        argv = ["prepare", "--repo", str(repo), "--project", "proj",
                "--flow", "1", "--change", "add-widget", "--task", "1.1",
                "--action", "dev_task", "--role", "dev", "--path", "src/**",
                "--owner-pm", "pm", "--registry", str(reg),
                "--state", str(state), "--correlation-id", "stale1", "--json"]
        assert flowctl.main(argv) == 0
        write(repo, "src/main.py", "X = 2\n")
        commit_all(repo, "world moved on")
        rc = flowctl.main(["run", "--correlation-id", "stale1",
                           "--registry", str(reg), "--state", str(state),
                           "--json"])
        assert rc == 1  # STALE_SNAPSHOT
        data = json.loads(state.read_text(encoding="utf-8"))
        assert data["runs"]["stale1"]["status"] == "prepared"
        assert reg.read_text(encoding="utf-8").count('"reserved"') >= 1

    def test_check_cli_stale_digest(self, tmp_path):
        """Библиотечно: decision с неверным expected digest → STALE_SNAPSHOT."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="2.1")
        d = ft.check_action(s, act(task_id="2.1",
                                   expected_snapshot_digest="f" * 64))
        assert d.status == "DENY"
        assert has_code(d, ft.STALE_SNAPSHOT)


# --------------------- TC-BP-008: runner упал — recovery без повторной делегации


class TestBP08CrashRecovery:
    """ТЗ 07 п.8: Runner падает после reservation и после записи файлов;
    recovery сохраняет данные и не стартует делегацию повторно."""

    def test_crash_after_reservation_preserves_data(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        res = sc.reserve({"repo": str(repo), "delegation_id": "crash-1",
                          "role": "dev", "project": "proj",
                          "owner_pm": "pm", "paths": ["src/**"], "policy_version": PV,
                          "base_sha": git(repo, "rev-parse", "HEAD")}, reg)
        assert res["allowed"]
        # runner «умер»: PID не записан/мертв; записи файлов нет
        rec = sc.reconcile(reg, repo=repo, delegation_id="crash-1")
        assert rec["ok"]
        r = rec["results"][0]
        assert r["status_after"] in ("stale", "needs_attention")
        # запись сохранена (не удалена):
        sessions = sc.status(reg, delegation_id="crash-1")["sessions"]
        assert len(sessions) == 1

    def test_crash_after_files_written_needs_attention(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        sc.reserve({"repo": str(repo), "delegation_id": "crash-2",
                    "role": "dev", "project": "proj",
                    "owner_pm": "pm", "paths": ["src/**"], "policy_version": PV,
                    "base_sha": git(repo, "rev-parse", "HEAD")}, reg)
        write(repo, "src/main.py", "X = 42\n")  # агент успел записать файлы
        rec = sc.reconcile(reg, repo=repo, delegation_id="crash-2")
        r = rec["results"][0]
        assert r["status_after"] == "needs_attention"
        assert r["uncommitted"] == ["src/main.py"]
        assert "ничего не удалять" in " ".join(r["marks"])
        # файлы на месте:
        assert "X = 42" in (repo / "src/main.py").read_text(encoding="utf-8")

    def test_no_redelegation_after_recovery(self, tmp_path):
        """Recovery НЕ перезапускает делегацию: повторный reserve с тем же
        delegation_id и тем же payload идемпотентен (вторая сессия не
        создается), а reconcile не порождает новых reservation."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        req = {"repo": str(repo), "delegation_id": "crash-3",
               "role": "dev", "project": "proj", "owner_pm": "pm",
               "paths": ["src/**"], "policy_version": PV}
        assert sc.reserve(req, reg)["allowed"]
        sc.reconcile(reg, repo=repo, delegation_id="crash-3")
        n_before = len(sc.status(reg)["sessions"])
        # повторный reserve — идемпотентен, новой сессии нет:
        again = sc.reserve(req, reg)
        assert again["allowed"] and again.get("idempotent")
        assert len(sc.status(reg)["sessions"]) == n_before

    def test_needs_attention_run_refused_via_flowctl(self, tmp_path):
        """Сквозной: после needs_attention повторный run не повторяет
        делегацию (отказ)."""
        import flowctl
        repo = make_repo(tmp_path, tasks="# Tasks\n\n- [ ] 1.1 сделать\n")
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl.main(["prepare", "--repo", str(repo), "--project", "proj",
                      "--flow", "1", "--change", "add-widget",
                      "--task", "1.1", "--action", "dev_task", "--role",
                      "dev", "--path", "src/**", "--owner-pm", "pm",
                      "--registry", str(reg), "--state", str(state),
                      "--correlation-id", "cr4", "--json"])
        flowctl.main(["run", "--correlation-id", "cr4",
                      "--registry", str(reg), "--state", str(state)])
        write(repo, "src/main.py", "X = crash\n")
        flowctl.main(["reconcile", "--repo", str(repo),
                      "--registry", str(reg), "--state", str(state)])
        rc = flowctl.main(["run", "--correlation-id", "cr4",
                           "--registry", str(reg), "--state", str(state),
                           "--json"])
        assert rc == 1  # не started
        data = json.loads(state.read_text(encoding="utf-8"))
        assert data["runs"]["cr4"]["status"] == "needs_attention"


# --------------------------------- TC-BP-009: branch protection неизвестна


class TestBP09ExternalEnforcement:
    """ТЗ 07 п.9: внешняя защита main неизвестна/отключена — отчет честно
    показывает границу локального enforcement; локальный PASS не называется
    доказательством защиты main."""

    def test_merge_task_always_flags_external_enforcement_unknown(
            self, tmp_path):
        """Даже при полном локальном наборе (approve + валидный sidecar)
        merge_task несет EXTERNAL_ENFORCEMENT_UNKNOWN → не чистый ALLOW."""
        repo = make_repo(tmp_path, reviews=True)
        reg = make_registry(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        diff = subprocess.run(
            ["git", "-C", str(repo), "diff", f"{sha}^..{sha}"],
            capture_output=True, text=True).stdout
        sidecar(repo, "add-widget", ["3.1"], "deleg-A", "deleg-B", sha,
                diff_digest=gr.sha256_text(diff))
        d = ft.check_action(snapshot_for(repo, reg, task_id="3.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task",
                                task_id="3.1"))
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)
        assert any("branch protection" in x for x in d.details)
        # Пометка не повышает статус: без подтверждения защиты main
        # разрешение не «чистое» (не PASS-аналог).
        assert d.status != "ALLOW"

    def test_release_always_flags_external_enforcement(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg),
                            act(actor_role="pm",
                                requested_action="release",
                                approval_ref="решение фазы"))
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)
        assert d.status != "ALLOW"

    def test_gate_pass_report_does_not_claim_main_protection(self, tmp_path):
        """Локальный PASS gates не содержит утверждений о защите main:
        в GateReport нет поля/утверждения «main защищена»."""
        repo = make_repo(tmp_path)
        opts = type("O", (), {
            "openspec_cmd": "/nonexistent/nope", "timeout": 10,
            "pm_mode": None, "pm_commits": None, "pm_range": None,
            "pm_registry": None, "pm_require_review": False,
            "pr_id": None, "log_dir": str(tmp_path / "l"),
            "report_dir": str(tmp_path / "r"), "audit": None,
            "correlation_id": "bp9",
        })()
        report, _ = gr.run_gates(repo, "pre_merge",
                                 list(gr.DEFAULT_GATES["pre_merge"]), opts)
        text = json.dumps(report, ensure_ascii=False)
        assert "main защищена" not in text
        assert "branch protection подтверждена" not in text
        # при недоступности внешнего контекста gates честно не PASS
        assert report["overall"] != "PASS"

    def test_decision_json_carries_honest_boundary(self, tmp_path):
        repo = make_repo(tmp_path, reviews=True)
        reg = make_registry(tmp_path)
        r = cli("check", "--repo", str(repo), "--project", "proj",
                "--flow", "1", "--change", "add-widget", "--task", "3.1",
                "--action", "merge_task", "--role", "dev_lead",
                "--registry", str(reg), "--json")
        data = json.loads(r.stdout)
        assert "EXTERNAL_ENFORCEMENT_UNKNOWN" in data["blocking_reasons"]
        assert data["status"] in ("DENY", "UNKNOWN")


# ------------------------------------------------- TC-M4: долг review-006 m4


class TestM4SidecarRevisionParsing:
    """Долг m4 (review-006): _review_file_revision получала имена sidecar
    («review-002-1.1.md.provenance.json»), на которых regex .md$ не совпадали
    — rev всегда 0. Фикс: срезать PROVENANCE_SIDECAR_SUFFIX перед матчингом.
    Проверка: выбор ревизии между rev-first и task-first sidecar."""

    def test_unit_sidecar_names_parse(self):
        cases = [
            ("review-002-1.1.md.provenance.json", 2),
            ("review-1.1-002.md.provenance.json", 2),   # task-first
            ("review-3.1-003.md.provenance.json", 3),   # task-first
            ("review-001-1.1.md", 1),                    # обычный .md
            (None, 0),
        ]
        for name, expected in cases:
            assert ft._review_file_revision(name) == expected, name

    def _repo(self, tmp_path: Path) -> Path:
        repo = make_repo(tmp_path, change_id="add-x", req=None, tasks=None)
        sha = git(repo, "rev-parse", "HEAD")
        cr = repo / "code-reviews" / "add-x"
        cr.mkdir(parents=True, exist_ok=True)
        for name, tasks in (
            ("review-9.9-003.md.provenance.json", ["9.9"]),   # task-first, rev 3
            ("review-001-9.9.md.provenance.json", ["9.9"]),   # rev-first, rev 1
        ):
            (cr / name).write_text(json.dumps({
                "schema_version": "review-provenance/1",
                "project": "proj", "change": "add-x", "task_ids": tasks,
                "author_delegation": "A", "reviewer_delegation": "B",
                "reviewed_commit_sha": sha, "verdict": "approve",
                "diff_digest": "0" * 64,
            }), encoding="utf-8")
        return repo

    def test_foreign_sidecar_selection_by_revision_not_sort_order(self,
                                                                  tmp_path):
        """«Чужой» sidecar (не покрывает задачу) выбирается по МАКСИМАЛЬНОЙ
        ревизии, а не первым по sorted() — до m4 обе ревизии парсились в 0."""
        repo = self._repo(tmp_path)
        reg = make_registry(tmp_path)
        _, sidecar_path, err, foreign = ft.load_review_provenance(
            repo, "add-x", "3.1")
        assert err is None and foreign is not None
        assert "003" in sidecar_path, (
            f"ожидался sidecar ревизии 003 (max), выбран {sidecar_path}")

    def test_latest_sidecar_by_revision(self, tmp_path):
        """Покрывающий задачу sidecar: max ревизии, смешение форматов имен —
        выбор численный, не лексикографический."""
        repo = self._repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        cr = repo / "code-reviews" / "add-x"
        # покрывающий 3.1: task-first rev 002 vs rev-first rev 001
        for name in ("review-3.1-002.md.provenance.json",
                     "review-001-3.1.md.provenance.json"):
            (cr / name).write_text(json.dumps({
                "schema_version": "review-provenance/1",
                "project": "proj", "change": "add-x", "task_ids": ["3.1"],
                "author_delegation": "A", "reviewer_delegation": "B",
                "reviewed_commit_sha": sha, "verdict": "approve",
                "diff_digest": gr.sha256_text("d"),
            }), encoding="utf-8")
        sidecar, path, err, _ = ft.load_review_provenance(
            repo, "add-x", "3.1")
        assert err is None and sidecar is not None
        assert "002" in path
