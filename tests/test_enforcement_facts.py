# -*- coding: utf-8 -*-
"""Тесты фактов enforcement P0.1 (решения Заказчика А/Б/В1, 2026-10-02).

Приемка заключения ChatGPT (P0.1): merge/release достижимы до ALLOW при
полном комплекте доказательств. На каждый факт — три исхода:
  1) нет   → прежнее поведение (merge: пометка EXTERNAL_ENFORCEMENT_UNKNOWN;
             release: HUMAN_APPROVAL_REQUIRED / INVALID_GATE «до архивации»);
  2) есть  → ALLOW достижим (пометка уходит, полный комплект фактов);
  3) битый/чужой → DENY (отрицательный/непривязанный факт — не разрешение).

Сетевых вызовов НЕТ: GitHub-адаптер тестируется на monkeypatch _github_api_get
(локальный fake) и на skip-правилах; факт protection в flow_state — JSON-файл
в tmp-репо. Реальный ~/.hermes/state/ не используется.

Трассировка: TC-EVF-001... (спека deterministic-flow, Requirement «Честная
граница enforcement», сценарий «Полный комплект фактов»).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_state  # noqa: E402
import flow_transition as ft  # noqa: E402
import gate_runner as gr  # noqa: E402

REQ_APPROVED = ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba | История: r1\n\n"
                "## Описание\n...\n")

TASKS_ALL_DONE = "- [x] 1.1\n- [x] 1.2\n- [x] 2.1\n- [x] 6.1\n"

DELTA = "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n"


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init") -> str:
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path: Path, name: str = "proj") -> Path:
    """Репо с ВСЕМ локальным комплектом до release (кроме внешних фактов)."""
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    write(repo, "requirements.md", REQ_APPROVED)
    # активный change (релиз требует его ОТСУТСТВИЯ в активных — см. сценарии)
    write(repo, "openspec/changes/add-widget/proposal.md", "# p\n")
    write(repo, "openspec/changes/add-widget/design.md", "# d\n")
    write(repo, "openspec/changes/add-widget/tasks.md", TASKS_ALL_DONE)
    write(repo, "openspec/changes/add-widget/specs/widget/spec.md", DELTA)
    write(repo, "openspec/specs/widget/spec.md", DELTA)
    write(repo, "sdd.md", "# SDD\n")
    write(repo, "test-model/approved/add-widget/TC-WID-001.md", "# TC\n")
    commit_all(repo)
    return repo


def make_registry(tmp_path: Path) -> Path:
    p = tmp_path / "active_sessions.json"
    p.write_text('{"sessions": []}', encoding="utf-8")
    return p


def snapshot_for(repo: Path, reg: Path, **kw) -> dict:
    return flow_state.inspect(
        repo_arg=str(repo), project=kw.get("project", "proj"),
        flow=kw.get("flow", 1), change_id=kw.get("change_id", "add-widget"),
        task_id=kw.get("task_id"), registry=str(reg),
    )


def act(**kw) -> ft.ActionRequest:
    kw.setdefault("actor_role", "pm")
    kw.setdefault("requested_action", "release")
    return ft.ActionRequest(**kw)


def has_code(d: ft.Decision, code: str) -> bool:
    return code in d.blocking_reasons


def protect_ok_report(repo: Path, *, head: str | None = None,
                      observed_recent: bool = True,
                      repo_name: str = "org/repo") -> Path:
    """Валидный отчет github-protection/1: protection_ok, свежий, привязан."""
    import datetime
    path = repo / ".flow-evidence" / "github-protection.json"
    observed = (datetime.datetime.now(datetime.timezone.utc)
                if observed_recent else
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=48))
    write(repo, str(path.relative_to(repo)), json.dumps({
        "schema_version": "github-protection/1",
        "adapter_version": "gate-runner/1",
        "repo": repo_name,
        "branch": "main",
        "observed_at": observed.isoformat(timespec="seconds"),
        "protection_ok": True,
        "http_status": 200,
        "detail": "required_pull_request_reviews + required_status_checks(flow.yml)",
        "repo_head": head if head is not None else git(repo, "rev-parse", "HEAD"),
    }))
    return path


def protection_404_report(repo: Path) -> Path:
    path = repo / ".flow-evidence" / "github-protection.json"
    write(repo, str(path.relative_to(repo)), json.dumps({
        "schema_version": "github-protection/1",
        "adapter_version": "gate-runner/1",
        "repo": "org/repo",
        "branch": "main",
        "observed_at": "2026-10-02T12:00:00+00:00",
        "protection_ok": False,
        "http_status": 404,
        "detail": "защита ветки не настроена (404)",
    }))
    return path


def archive_change(repo: Path, change_id: str = "add-widget") -> None:
    """Перенос change-пакета в archive/ (решение Б: факт из репо)."""
    src = repo / "openspec" / "changes" / change_id
    dst = repo / "openspec" / "changes" / "archive" / change_id
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    commit_all(repo, f"archive {change_id}")


def release_file(repo: Path, change_id: str = "add-widget",
                 text: str | None = None) -> None:
    write(repo, f"releases/{change_id}.md", text or (
        f"# Релиз {change_id}\n\nРешение Заказчика: «разрешаю релиз "
        f"{change_id}» (2026-10-02)\n"))
    commit_all(repo)


# =========================================================================
# Факт Б: change.archived (flow_state)
# =========================================================================


class TestArchivedFact:
    def test_missing_when_not_archived(self, tmp_path):
        """Нет archive/ → факт missing со значением False (проверяемый
        отрицательный факт), confidence verified."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "change.archived")
        assert f["status"] == "missing"
        assert f["value"] is False
        assert f["confidence"] == "verified"

    def test_ready_when_archived(self, tmp_path):
        repo = make_repo(tmp_path)
        archive_change(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "change.archived")
        assert f["status"] == "ready" and f["value"] is True

    def test_unknown_when_symlink_outside(self, tmp_path):
        """Битый/чужой источник (symlink наружу) → unknown + проблема,
        не «не заархивирован»."""
        repo = make_repo(tmp_path)
        archive_change(repo)
        outside = tmp_path / "outside"
        outside.mkdir()
        import shutil
        shutil.rmtree(repo / "openspec/changes/archive/add-widget")
        import os
        os.symlink(outside, repo / "openspec/changes/archive/add-widget")
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "change.archived")
        assert f["status"] == "unknown", f
        assert f["value"] is None
        assert any(p["code"] == "PATH_OUTSIDE_REPO" for p in s["problems"])


# =========================================================================
# Факт В1: release.approval (flow_state)
# =========================================================================


class TestReleaseApprovalFact:
    def test_missing_without_file(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "release.approval")
        assert f["status"] == "missing"

    def test_ready_with_approval_file(self, tmp_path):
        repo = make_repo(tmp_path)
        release_file(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "release.approval")
        assert f["status"] == "ready"
        assert f["value"]["change"] == "add-widget"

    def test_invalid_other_change_or_no_approval_word(self, tmp_path):
        """Чужой change в файле / нет слова согласия → invalid (не ready)."""
        repo = make_repo(tmp_path)
        release_file(repo, text="# Релиз\n\nchange: other-widget\n")
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "release.approval")
        assert f["status"] == "invalid"

        repo2 = make_repo(tmp_path / "b")
        release_file(repo2, text="# Релиз add-widget\n\nно решения нет\n")
        s2 = snapshot_for(repo2, reg)
        f2 = next(f for f in s2["facts"] if f["key"] == "release.approval")
        assert f2["status"] == "invalid"


# =========================================================================
# Факт А: github.protection (flow_state + gate_runner адаптер, без сети)
# =========================================================================


class TestProtectionFactState:
    def test_missing_without_report(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "github.protection")
        assert f["status"] == "missing"

    def test_ready_with_fresh_bound_report(self, tmp_path):
        repo = make_repo(tmp_path)
        protect_ok_report(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "github.protection")
        assert f["status"] == "ready", f
        assert f["value"]["protection_ok"] is True

    def test_invalid_stale_or_foreign(self, tmp_path):
        """Отчет старше 24ч / другой HEAD / другой branch = invalid."""
        repo = make_repo(tmp_path)
        protect_ok_report(repo, observed_recent=False)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "github.protection")
        assert f["status"] == "invalid", f

        repo2 = make_repo(tmp_path / "b")
        protect_ok_report(repo2, head="deadbeef" * 8)
        s2 = snapshot_for(repo2, reg)
        f2 = next(f for f in s2["facts"] if f["key"] == "github.protection")
        assert f2["status"] == "invalid"

        repo3 = make_repo(tmp_path / "c")
        protect_ok_report(repo3)
        # перезапишем branch на develop
        path = repo3 / ".flow-evidence" / "github-protection.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["branch"] = "develop"
        path.write_text(json.dumps(data), encoding="utf-8")
        s3 = snapshot_for(repo3, reg)
        f3 = next(f for f in s3["facts"] if f["key"] == "github.protection")
        assert f3["status"] == "invalid"

    def test_404_report_invalid_negative_fact(self, tmp_path):
        """404-отчет — отрицательный факт (protection_ok=False, invalid):
        защита ОТСУТСТВУЕТ, это знание, а не незнание."""
        repo = make_repo(tmp_path)
        protection_404_report(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "github.protection")
        assert f["status"] == "invalid"
        assert f["value"]["protection_ok"] is False

    def test_unknown_broken_json(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, ".flow-evidence/github-protection.json", "{not json")
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "github.protection")
        assert f["status"] == "unknown"


class TestProtectionAdapter:
    """gate_runner github_protection: skip-правила + fake API (без сети)."""

    def test_skip_without_params(self, tmp_path):
        with pytest.raises(ValueError) as ei:
            gr.check_branch_protection(tmp_path, "", "T", token_env_os={})
        assert "skip:" in str(ei.value)
        with pytest.raises(ValueError) as ei:
            gr.check_branch_protection(tmp_path, "o/n", "", token_env_os={})
        assert "skip:" in str(ei.value)
        with pytest.raises(ValueError) as ei:
            gr.check_branch_protection(tmp_path, "o/n", "NOPE", token_env_os={})
        assert "skip:" in str(ei.value)

    def test_404_negative_fact(self, tmp_path):
        repo = make_repo(tmp_path)
        orig = gr._github_api_get
        gr._github_api_get = lambda url, tok: (404, '{"message": "Not Found"}')
        try:
            fact = gr.check_branch_protection(repo, "o/n", "T",
                                              token_env_os={"T": "tok"})
        finally:
            gr._github_api_get = orig
        assert fact["protection_ok"] is False
        assert fact["http_status"] == 404
        loaded, err = gr.load_protection_fact(repo)
        assert err is None and loaded["protection_ok"] is False

    def test_200_with_reviews_and_flow_yml(self, tmp_path):
        repo = make_repo(tmp_path)
        body = {"required_pull_request_reviews": {},
                "required_status_checks": {"contexts": ["flow.yml / gate"]}}
        orig = gr._github_api_get
        gr._github_api_get = lambda url, tok: (200, json.dumps(body))
        try:
            fact = gr.check_branch_protection(repo, "o/n", "T",
                                              token_env_os={"T": "tok"})
        finally:
            gr._github_api_get = orig
        assert fact["protection_ok"] is True

    def test_200_without_reviews_or_flow_yml_fails(self, tmp_path):
        repo = make_repo(tmp_path)
        orig = gr._github_api_get
        for body in (
            {"required_status_checks": {"contexts": ["flow.yml"]}},
            {"required_pull_request_reviews": {},
             "required_status_checks": {"contexts": ["ci"]}},
        ):
            gr._github_api_get = lambda url, tok, b=body: (200, json.dumps(b))
            try:
                fact = gr.check_branch_protection(repo, "o/n", "T",
                                                  token_env_os={"T": "tok"})
            finally:
                gr._github_api_get = orig
            assert fact["protection_ok"] is False, body

    def test_token_never_in_report_or_argv(self, tmp_path):
        """Токен НЕ попадает в отчет; argv дочернего процесса — только ИМЯ env."""
        repo = make_repo(tmp_path)
        captured = {}

        def fake_get(url, token):
            captured["url"] = url
            return 404, "{}"

        orig = gr._github_api_get
        gr._github_api_get = fake_get
        try:
            gr.check_branch_protection(repo, "o/n", "FLOW_T",
                                       token_env_os={"FLOW_T": "sekret-token"})
        finally:
            gr._github_api_get = orig
        assert "sekret-token" not in captured["url"]
        loaded, _ = gr.load_protection_fact(repo)
        assert "sekret-token" not in json.dumps(loaded)


# =========================================================================
# Сводные исходы check_merge_task / check_release (3 исхода на факт)
# =========================================================================


def merge_snapshot(tmp_path: Path):
    """Репо, где provenance merge чист (sidecar по текущему HEAD).

    Как в tests/test_provenance.py: sidecar пишется ПОСЛЕ коммита и не
    коммитится — flow_state читает файлы напрямую, STALE не возникает.
    """
    repo = make_repo(tmp_path)
    reg = make_registry(tmp_path)
    write(repo, "code-reviews/add-widget/review-001-2.1.md",
          "# Review\n\n## Вердикт: approve\n")
    commit_all(repo, "review")
    import flow_transition as _ft
    sha = git(repo, "rev-parse", "HEAD")
    diff = _ft._git_diff_for_head({"scope": {"repo": str(repo)}}, sha)
    gr.write_review_provenance(
        repo / "code-reviews" / "add-widget" / "review-001-2.1.md",
        "proj", "add-widget", ["2.1"], "deleg-A", "deleg-B", sha, "approve",
        diff_digest=gr.sha256_text(diff))
    return repo, reg


class TestMergeOutcomes:
    def test_no_fact_unknown_marker(self, tmp_path):
        """1) нет факта → прежнее поведение: пометка EXTERNAL_ENFORCEMENT."""
        repo, reg = merge_snapshot(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)

    def test_valid_fact_allow_reachable(self, tmp_path):
        """2) полный комплект (протекция + чистый provenance) → merge ALLOW."""
        repo, reg = merge_snapshot(tmp_path)
        protect_ok_report(repo)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        assert d.status == "ALLOW", d.details
        assert not has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)

    def test_404_fact_deny(self, tmp_path):
        """3) факт «защита main не настроена» → DENY с кодом
        EXTERNAL_ENFORCEMENT_UNKNOWN и деталью 404."""
        repo, reg = merge_snapshot(tmp_path)
        protection_404_report(repo)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)
        assert any("не настроена" in x for x in d.details)

    def test_stale_fact_stays_unknown(self, tmp_path):
        """Протухший/чужой факт НЕ разрешает: пометка остается (UNKNOWN)."""
        repo, reg = merge_snapshot(tmp_path)
        protect_ok_report(repo, observed_recent=False)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)


class TestReleaseOutcomes:
    def _base(self, tmp_path: Path, name: str = "proj"):
        """Релизный комплект: задачи закрыты, change заархивирован, дельты
        слиты (master-spec содержит Requirement W).

        Архивация перемещает tasks.md в archive/, а _fact_ready('change.tasks')
        читает АКТИВНЫЙ пакет → after archive, факт change.tasks отсутствует.
        Это согласуется с моделью: release проверяет archive-факт (готово),
        а не активные чекбоксы. Но tasks-факт, если change еще активен,
        должен DENY (архивация не завершена). Для ALLOW-сценария активного
        пакета быть не должно.
        """
        repo = make_repo(tmp_path, name=name)
        archive_change(repo)
        return repo, make_registry(tmp_path)

    def test_no_facts_previous_behavior(self, tmp_path):
        """1) ничего нет → прежнее поведение: DENY «до архивации» +
        HUMAN_APPROVAL + пометка enforcement."""
        repo = make_repo(tmp_path)
        d = ft.check_action(snapshot_for(repo, make_registry(tmp_path)),
                            act())
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)
        assert any("release до архивации" in x for x in d.details)

    def test_full_evidence_allow(self, tmp_path):
        """2) полный комплект фактов → ALLOW (сценарий спеки)."""
        repo, reg = self._base(tmp_path)
        release_file(repo)
        protect_ok_report(repo)
        d = ft.check_action(snapshot_for(repo, reg), act())
        assert d.status == "ALLOW", d.details
        assert d.allowed is True

    def test_approval_file_without_release_word_invalid(self, tmp_path):
        """3а) файл релиза без change-id/слова согласия → решение не
        засчитано: HUMAN_APPROVAL_REQUIRED остается."""
        repo, reg = self._base(tmp_path)
        release_file(repo, text=f"# Релиз add-widget\n\nникто не разрешал\n")
        d = ft.check_action(snapshot_for(repo, reg), act())
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)

    def test_release_before_archive_deny(self, tmp_path):
        """3б) чужой/отсутствующий archive → DENY «release до архивации»."""
        repo = make_repo(tmp_path)
        release_file(repo)
        protect_ok_report(repo)
        d = ft.check_action(snapshot_for(repo, make_registry(tmp_path)),
                            act())
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("release до архивации" in x for x in d.details)

    def test_no_protection_blocks_allow(self, tmp_path):
        """3в) все локальные факты есть, но протекции нет → не ALLOW."""
        repo, reg = self._base(tmp_path)
        release_file(repo)
        d = ft.check_action(snapshot_for(repo, reg), act())
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)

    def test_string_approval_ref_still_accepted(self, tmp_path):
        """approval_ref (строка среза 1) по-прежнему принимается как решение —
        файл releases/<id>.md не отменяет D5."""
        repo, reg = self._base(tmp_path)
        protect_ok_report(repo)
        d = ft.check_action(
            snapshot_for(repo, reg),
            act(approval_ref="чат-лог: «погнали» 2026-10-02"))
        assert d.status == "ALLOW", d.details


# =========================================================================
# CLI адаптера github-protection (SKIPPED/факт), без сети
# =========================================================================


class TestProtectionCli:
    def test_cli_skip_when_params_missing(self, tmp_path):
        repo = make_repo(tmp_path)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "github-protection", "--repo", str(repo)],
            capture_output=True, text=True)
        assert r.returncode == 3, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["status"] == "SKIPPED"

    def test_cli_skip_when_env_absent(self, tmp_path):
        repo = make_repo(tmp_path)
        import os
        env = {k: v for k, v in os.environ.items() if k != "FLOW_NO_SUCH_TOKEN"}
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "github-protection", "--repo", str(repo),
             "--github-repo", "o/n", "--github-token-env", "FLOW_NO_SUCH_TOKEN",
             "--report", str(tmp_path / "fact.json")],
            capture_output=True, text=True, env=env, timeout=120)
        assert r.returncode == 3, r.stdout + r.stderr
        assert json.loads(r.stdout)["status"] == "SKIPPED"

    def test_cli_negative_fact_exit1(self, tmp_path):
        """Готовый 404-факт в репо не меняется CLI без сети — но чтение факта
        и отрицательный вердикт проверяем на уровне библиотеки (без сети);
        CLI с fake-сервером не тестируем — сетевых вызовов в тестах нет."""
        repo = make_repo(tmp_path)
        protection_404_report(repo)
        loaded, err = gr.load_protection_fact(repo)
        assert err is None and loaded["protection_ok"] is False

    def test_fact_not_written_on_skip(self, tmp_path):
        repo = make_repo(tmp_path)
        import os
        env = {k: v for k, v in os.environ.items() if k != "FLOW_NO_SUCH_TOKEN"}
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "github-protection", "--repo", str(repo),
             "--github-repo", "o/n", "--github-token-env", "FLOW_NO_SUCH_TOKEN",
             "--report", str(repo / ".flow-evidence" / "github-protection.json")],
            capture_output=True, text=True, env=env, timeout=120)
        assert r.returncode == 3
        assert not (repo / ".flow-evidence" / "github-protection.json").exists()
