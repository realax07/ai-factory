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


def commit_all(repo: Path, msg: str = "init", amend: bool = False) -> str:
    git(repo, "add", "-A")
    if amend:
        git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "--amend", "-m", msg)
    else:
        git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-m", msg)
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
                 text: str | None = None,
                 sha: str | None = "auto") -> None:
    """Пишет releases/<id>.md. sha='auto' → актуальный HEAD; None → без
    строки SHA (битый формат); явная строка → подставить как есть.
    Файл пишется, коммитится, затем дописывается строка SHA с актуальным
    HEAD и коммитится вторым коммитом (рабочее дерево чистое — HEAD при
    проверке снимка совпадает с последним коммитом)."""
    body = text or (
        f"# Релиз {change_id}\n\nРешение Заказчика: «разрешаю релиз "
        f"{change_id}» (2026-10-02)\n")
    write(repo, f"releases/{change_id}.md", body)
    commit_all(repo, f"release decision {change_id}")
    if sha == "auto":
        sha = git(repo, "rev-parse", "HEAD")
    if sha is not None and "SHA:" not in body and "commit:" not in body:
        p = repo / "releases" / f"{change_id}.md"
        # Fixpoint SHA коммита от его же содержимого не существует, поэтому
        # строка SHA коммитится ВТОРЫМ коммитом, а незакоммиченная правка
        # НЕ делается: файл в рабочем дереве == файлу в HEAD (снимок читает
        # рабочее дерево), HEAD на коммит впереди — это сама природа журнала
        # «решение о HEAD, записанного после HEAD». Сверка факта допускает
        # строку SHA в HEAD^ (см. flow_state.release_approval_fact).
        p.write_text(p.read_text(encoding="utf-8") + f"\nSHA: {sha}\n",
                     encoding="utf-8")
        commit_all(repo, f"release decision {change_id}: SHA")
    elif sha is not None:
        # Явный SHA в тексте: перезапись после коммита (незакоммиченный файл
        # — снимок читает рабочее дерево, это ок для негативных сценариев).
        write(repo, f"releases/{change_id}.md", body)


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

    def test_ready_when_archived(self, tmp_path, monkeypatch):
        """Архивация при слитых дельтах и пройденном validate → ready."""
        repo = make_repo(tmp_path)
        archive_change(repo)
        monkeypatch.setattr(flow_state, "OPENSPEC_VALIDATE_CMD",
                            lambda repo, argv: 0)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "change.archived")
        assert f["status"] == "ready"
        assert f["value"]["archived"] is True
        assert f["value"]["deltas_merged"] is True
        assert f["value"]["validate"] == "ok"

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


def protection_ruleset_body(enforcement="active", pull_request=True,
                            bypass=None, checks=None):
    """Тело ответа GET /repos/{repo}/rules/branches/main (массив rulesets)."""
    rules = []
    if pull_request:
        rules.append({"type": "pull_request"})
    if checks is not None:
        rules.append({
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [
                {"context": c} for c in checks]},
        })
    return [{
        "id": 24385697,
        "name": "factory-protection",
        "enforcement": enforcement,
        "rules": rules,
        "bypass": bypass or [],
    }]


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

    def test_rulesets_endpoint_url(self, tmp_path):
        """Endpoint — Rulesets API /rules/branches, старый /branches/.../protection
        не вызывается."""
        repo = make_repo(tmp_path)
        captured = {}

        def fake_get(url, token):
            captured["url"] = url
            return 200, json.dumps(protection_ruleset_body())

        orig = gr._github_api_get
        gr._github_api_get = fake_get
        try:
            fact = gr.check_branch_protection(repo, "o/n", "T",
                                              token_env_os={"T": "tok"})
        finally:
            gr._github_api_get = orig
        assert captured["url"].endswith("/repos/o/n/rules/branches/main")
        assert "/branches/main/protection" not in captured["url"]
        assert fact["protection_ok"] is True

    def test_200_ruleset_active_pull_request_no_bypass(self, tmp_path):
        repo = make_repo(tmp_path)
        orig = gr._github_api_get
        gr._github_api_get = lambda url, tok: (
            200, json.dumps(protection_ruleset_body(checks=["flow.yml / gate"])))
        try:
            fact = gr.check_branch_protection(repo, "o/n", "T",
                                              token_env_os={"T": "tok"})
        finally:
            gr._github_api_get = orig
        assert fact["protection_ok"] is True
        assert fact["ruleset_report"][0]["pull_request"] is True
        assert fact["ruleset_report"][0]["bypass_always"] is False

    def test_200_bypass_always_fails(self, tmp_path):
        """bypass с bypass_mode=always у активного ruleset → защита не
        подтверждена (роль может обходить pull_request)."""
        repo = make_repo(tmp_path)
        body = protection_ruleset_body(
            bypass=[{"actor_id": 5, "bypass_mode": "always"}])
        orig = gr._github_api_get
        gr._github_api_get = lambda url, tok: (200, json.dumps(body))
        try:
            fact = gr.check_branch_protection(repo, "o/n", "T",
                                              token_env_os={"T": "tok"})
        finally:
            gr._github_api_get = orig
        assert fact["protection_ok"] is False
        assert fact["ruleset_report"][0]["bypass_always"] is True

    def test_200_bypass_not_always_ok(self, tmp_path):
        """bypass с bypass_mode=pull_request (обход только своего PR) —
        не отменяет защиту."""
        repo = make_repo(tmp_path)
        body = protection_ruleset_body(
            bypass=[{"actor_id": 5, "bypass_mode": "pull_request"}])
        orig = gr._github_api_get
        gr._github_api_get = lambda url, tok: (200, json.dumps(body))
        try:
            fact = gr.check_branch_protection(repo, "o/n", "T",
                                              token_env_os={"T": "tok"})
        finally:
            gr._github_api_get = orig
        assert fact["protection_ok"] is True

    def test_200_inactive_or_no_pull_request_fails(self, tmp_path):
        repo = make_repo(tmp_path)
        orig = gr._github_api_get
        for body in (
            protection_ruleset_body(enforcement="evaluate"),
            protection_ruleset_body(pull_request=False),
            [],
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
        flow_state.OPENSPEC_VALIDATE_CMD = lambda repo, argv: 0
        return repo, make_registry(tmp_path)

    def teardown_method(self):
        flow_state.OPENSPEC_VALIDATE_CMD = None

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

    def test_string_ref_not_from_log_rejected_p04(self, tmp_path):
        """P0.4 (пересмотр плана): непустая строка approval_ref больше не
        достаточна — строка без записи журнала решений → DENY с
        HUMAN_APPROVAL_REQUIRED и подсказкой формата (сужение D5 — это и
        есть цель P0.4)."""
        repo, reg = self._base(tmp_path)
        protect_ok_report(repo)
        d = ft.check_action(
            snapshot_for(repo, reg),
            act(approval_ref="чат-лог: «погнали» 2026-10-02"))
        assert d.status == "DENY", d.details
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert any("decisions/" in x for x in d.details)


# =========================================================================
# Усиление change.archived (пересмотр плана п.1): дельты + validate
# =========================================================================


class TestArchivedStrengthened:
    """Негативные исходы усиленного факта архивации (пересмотр плана)."""

    def test_not_ready_when_deltas_not_merged(self, tmp_path):
        """Дельта не слита в openspec/specs/ → invalid (знание), не ready."""
        repo = make_repo(tmp_path)
        archive_change(repo)
        # удаляем Requirement из master-spec → дельта больше не слита
        write(repo, "openspec/specs/widget/spec.md", "# пусто\n")
        commit_all(repo, "unmerge")
        flow_state.OPENSPEC_VALIDATE_CMD = lambda r, a: 0
        try:
            s = snapshot_for(repo, make_registry(tmp_path))
        finally:
            flow_state.OPENSPEC_VALIDATE_CMD = None
        f = next(f for f in s["facts"] if f["key"] == "change.archived")
        assert f["status"] == "invalid", f
        assert f["value"]["deltas_merged"] is False
        assert f["value"]["delta_problems"]

    def test_unknown_when_openspec_cli_unavailable(self, tmp_path):
        """CLI недоступен → unknown с причиной, НЕ ready (нет «молчаливого
        PASS»)."""
        repo = make_repo(tmp_path)
        archive_change(repo)
        flow_state.OPENSPEC_VALIDATE_CMD = ("definitely-missing-cli",)
        try:
            s = snapshot_for(repo, make_registry(tmp_path))
        finally:
            flow_state.OPENSPEC_VALIDATE_CMD = None
        f = next(f for f in s["facts"] if f["key"] == "change.archived")
        assert f["status"] == "unknown", f
        assert f["value"]["validate"] == "unavailable"
        assert "reason" in f["value"]

    def test_not_ready_when_validate_fails(self, tmp_path):
        """validate --strict падает → unknown с причиной (не ready)."""
        repo = make_repo(tmp_path)
        archive_change(repo)
        flow_state.OPENSPEC_VALIDATE_CMD = lambda r, a: 1
        try:
            s = snapshot_for(repo, make_registry(tmp_path))
        finally:
            flow_state.OPENSPEC_VALIDATE_CMD = None
        f = next(f for f in s["facts"] if f["key"] == "change.archived")
        assert f["status"] == "unknown", f
        assert f["value"]["validate"] == "failed"
        assert any(p["code"] == "OPENSPEC_VALIDATE_ERROR" for p in s["problems"])

    def test_release_denied_on_unmerged_deltas(self, tmp_path):
        """Негатив на release: архив-пакет есть, дельты не слиты → не ALLOW."""
        repo = make_repo(tmp_path)
        archive_change(repo)
        write(repo, "openspec/specs/widget/spec.md", "# пусто\n")
        commit_all(repo, "unmerge")
        release_file(repo)
        protect_ok_report(repo)
        flow_state.OPENSPEC_VALIDATE_CMD = lambda r, a: 0
        try:
            d = ft.check_action(snapshot_for(repo, make_registry(tmp_path)), act())
        finally:
            flow_state.OPENSPEC_VALIDATE_CMD = None
        assert d.status != "ALLOW"
        assert d.local_ready != "ALLOW"


# =========================================================================
# Раздельный вывод local_ready / external_enforcement (пересмотр плана п.3)
# =========================================================================


class TestLocalExternalSplit:
    def test_local_ready_allow_with_external_unknown(self, tmp_path):
        """Локальные факты чисты, внешний факт нет → local_ready=ALLOW при
        общем UNKNOWN (явное разделение, не скрытое превращение)."""
        repo, reg = merge_snapshot(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        assert d.status == "UNKNOWN"
        assert d.local_ready == "ALLOW"
        assert d.allowed_local is True
        assert d.external_enforcement == "UNKNOWN"
        # в JSON-представлении поля раздельны
        as_dict = d.to_dict()
        assert as_dict["local_ready"] == "ALLOW"
        assert as_dict["external_enforcement"] == "UNKNOWN"

    def test_local_ready_allow_with_external_pass(self, tmp_path):
        """Полный комплект → общий ALLOW, external_enforcement=PASS."""
        repo, reg = merge_snapshot(tmp_path)
        protect_ok_report(repo)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        assert d.status == "ALLOW"
        assert d.local_ready == "ALLOW"
        assert d.external_enforcement == "PASS"

    def test_external_deny_shown_separately(self, tmp_path):
        """404-факт → external_enforcement=DENY; local_ready остается ALLOW
        (локально все чисто) — DENY именно внешний."""
        repo, reg = merge_snapshot(tmp_path)
        protection_404_report(repo)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        assert d.status == "DENY"
        assert d.local_ready == "ALLOW"
        assert d.allowed_local is True
        assert d.external_enforcement == "DENY"

    def test_local_deny_not_masked_by_external_pass(self, tmp_path):
        """Локальный DENY (нет approve) при внешнем PASS → local_ready != ALLOW,
        общий DENY: внешний PASS не маскирует локальные проблемы."""
        repo = make_repo(tmp_path)
        protect_ok_report(repo)
        d = ft.check_action(snapshot_for(repo, make_registry(tmp_path),
                                         task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        assert d.status == "DENY"
        assert d.local_ready != "ALLOW"
        assert d.external_enforcement == "PASS"

    def test_human_output_shows_split(self, tmp_path):
        """Человекочитаемый вывод содержит строку local_ready/external_
        enforcement (явное разделение в отчете)."""
        repo, reg = merge_snapshot(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        human = ft._decision_human(d)
        assert "local_ready: ALLOW" in human
        assert "external_enforcement: UNKNOWN" in human

    def test_policy_flag_false_lets_local_allow(self, tmp_path, monkeypatch):
        """Явно выбранная политика merge_requires_external=false: решение по
        локальным фактам (ALLOW при чистой локали), внешний UNKNOWN показан
        рядом — не скрытое превращение, а явная политика."""
        repo, reg = merge_snapshot(tmp_path)
        monkeypatch.setattr(ft, "MERGE_REQUIRES_EXTERNAL", False)
        d = ft.check_action(snapshot_for(repo, reg, task_id="2.1"),
                            act(actor_role="dev_lead",
                                requested_action="merge_task", task_id="2.1"))
        assert d.status == "ALLOW", d.details
        assert d.local_ready == "ALLOW"
        assert d.external_enforcement == "UNKNOWN"
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)


# =========================================================================
# Усиление release.approval (пересмотр плана п.4): SHA + конфликты
# =========================================================================


class TestReleaseApprovalSha:
    def test_ready_with_sha_line(self, tmp_path):
        """Файл с change-id, словом согласия и строкой SHA (HEAD или HEAD^)
        → ready; формулировка «решение зафиксировано»."""
        repo = make_repo(tmp_path)
        release_file(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "release.approval")
        assert f["status"] == "ready", f
        assert f["value"]["sha"]
        assert "решение зафиксировано" in f["value"]["note"]

    def test_invalid_without_sha_line(self, tmp_path):
        """Негатив: нет строки SHA → invalid (привязка к версии работы
        отсутствует), решение не засчитано."""
        repo = make_repo(tmp_path)
        release_file(repo, sha=None)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "release.approval")
        assert f["status"] == "invalid", f
        assert "SHA" in f["value"]["reason"]

    def test_invalid_stale_sha(self, tmp_path):
        """Негатив: SHA записи старше (есть коммит поверх) → invalid
        (устаревшее решение), не ready."""
        repo = make_repo(tmp_path)
        release_file(repo)
        write(repo, "unrelated.txt", "later work\n")
        commit_all(repo, "later commit")
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "release.approval")
        assert f["status"] == "invalid", f
        assert "устарело" in f["value"]["reason"]

    def test_unknown_conflicting_two_sha_lines(self, tmp_path):
        """Негатив: две строки SHA с разными хешами в одном файле → unknown
        с AMBIGUOUS_STATE."""
        repo = make_repo(tmp_path)
        head = git(repo, "rev-parse", "HEAD")
        release_file(repo, text=(
            f"# Релиз add-widget\n\nразрешаю релиз add-widget\n\n"
            f"SHA: {head}\nSHA: {'b' * 40}\n"))
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "release.approval")
        assert f["status"] == "unknown", f
        assert "AMBIGUOUS_STATE" in f["value"]["reason"]
        assert len(f["value"]["shas"]) == 2

    def test_unknown_conflicting_two_files(self, tmp_path):
        """Негатив: второй файл releases/<id>*.md с другим SHA → unknown
        с AMBIGUOUS_STATE."""
        repo = make_repo(tmp_path)
        release_file(repo)
        head2 = "c" * 40
        write(repo, "releases/add-widget-2.md",
              f"# Релиз add-widget\n\ncommit: {head2}\n")
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "release.approval")
        assert f["status"] == "unknown", f
        assert "AMBIGUOUS_STATE" in f["value"]["reason"]

    def test_release_blocked_by_conflicting_records(self, tmp_path):
        """Негатив на release: конфликт записей → HUMAN_APPROVAL_REQUIRED
        уходит, но появляется AMBIGUOUS_STATE; ALLOW недостижим без
        approval_ref."""
        repo = make_repo(tmp_path)
        archive_change(repo)
        head = git(repo, "rev-parse", "HEAD")
        release_file(repo, text=(
            f"# Релиз add-widget\n\nразрешаю релиз add-widget\n\n"
            f"SHA: {head}\nSHA: {'d' * 40}\n"))
        protect_ok_report(repo)
        flow_state.OPENSPEC_VALIDATE_CMD = lambda r, a: 0
        try:
            d = ft.check_action(snapshot_for(repo, make_registry(tmp_path)),
                                act())
        finally:
            flow_state.OPENSPEC_VALIDATE_CMD = None
        assert d.status != "ALLOW"
        assert has_code(d, ft.AMBIGUOUS_STATE)

    def test_report_says_decision_recorded_not_identity(self, tmp_path):
        """Формулировка: значение факта говорит «решение зафиксировано»,
        не «личность подтверждена»."""
        repo = make_repo(tmp_path)
        release_file(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        f = next(f for f in s["facts"] if f["key"] == "release.approval")
        dumped = json.dumps(f["value"], ensure_ascii=False)
        assert "решение зафиксировано" in dumped
        assert "личность подтверждена" not in dumped.replace(
            "не независимое одобрение личности", "")



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
