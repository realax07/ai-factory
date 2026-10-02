# -*- coding: utf-8 -*-
"""Тесты P0.4: журнал решений Заказчика (пересмотр плана, раздел P0.4).

Непустая строка approval_ref НЕ достаточна: строковый ref обязан быть
decision_id записи decisions/<YYYY-MM-DD>-<slug>.md с машиночитаемым блоком
decision-record/1. Запись проверяется на соответствие запросу: action,
scope, SHA (предок/равен HEAD), expiration. Журнал — НЕ защищенная подпись:
формулировки «решение зафиксировано», не «личность подтверждена».

Трассировка: спека deterministic-flow, Requirement «Этапные ворота
Заказчика» (сценарии P0.4) и «Честная граница enforcement»; контракт §10;
releases/<id>.md (решение В1) — аналогичный журнал, согласованный каталог
decisions/ рядом с releases/.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_state  # noqa: E402
import flow_transition as ft  # noqa: E402
import gate_runner  # noqa: E402

# --------------------------------------------------------------- helpers
# (единый стиль test_flow_transition: fixture-репо без subprocess-слоя,
# кроме CLI-тестов record-decision)


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
TASKS = "- [x] 1.1 готово\n- [ ] 1.2 обычная\n"


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
    write(repo, f"openspec/changes/{change_id}/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    write(repo, "sdd.md", "# SDD\n")
    write(repo, "openspec/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    commit_all(repo)
    return repo


def make_registry(tmp_path: Path) -> Path:
    p = tmp_path / "active_sessions.json"
    p.write_text('{"sessions": []}', encoding="utf-8")
    return p


def snapshot_for(repo: Path, registry: Path, **kw) -> dict:
    return flow_state.inspect(
        repo_arg=str(repo),
        project=kw.get("project", "proj"),
        flow=kw.get("flow", 1),
        change_id=kw.get("change_id", "add-widget"),
        task_id=kw.get("task_id"),
        registry=str(registry),
    )


def act(**kw) -> ft.ActionRequest:
    kw.setdefault("actor_role", "sa")
    kw.setdefault("requested_action", "create_change")
    return ft.ActionRequest(**kw)


def has_code(d: ft.Decision, code: str) -> bool:
    return code in d.blocking_reasons


def decision_record_text(sha: str, decision_id: str = "2026-10-02-start-add-widget",
                         *, scope: dict | None = None, action="create_change",
                         expiration: str | None = None,
                         schema: str = ft.DECISION_RECORD_SCHEMA) -> str:
    scope = scope or {"project": "proj", "change_id": "add-widget", "phase": 1}
    payload = {
        "schema_version": schema,
        "decision_id": decision_id,
        "date": decision_id[:10],
        "scope": scope,
        "action": action,
        "commit": sha,
        "source": "чат-лог: «погнали» 2026-10-02",
    }
    if expiration:
        payload["expiration"] = expiration
    import json
    return (f"# Решение: {decision_id}\n\n```decision-record\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n")


def add_decision(repo: Path, sha: str, **kw) -> str:
    did = kw.pop("decision_id", "2026-10-02-start-add-widget")
    text = decision_record_text(sha, did, **kw)
    write(repo, f"decisions/{did}.md", text)
    return did


# ------------------------------------------------------------ happy path


class TestValidRecord:
    def test_valid_record_executes_gate(self, tmp_path):
        """Валидная запись журнала → ворота исполнены (ALLOW)."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        did = add_decision(repo, sha)
        commit_all(repo, "decision log entry")  # SHA записи — предок HEAD
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref=did))
        assert d.status == "ALLOW", d.details
        assert any(f"decisions/{did}.md" in x for x in d.evidence_refs)

    def test_record_sha_equal_head_ok(self, tmp_path):
        """SHA записи == HEAD (без коммита поверх) — тоже валидно."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        did = add_decision(repo, sha)  # не коммитим: запись в working tree
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref=did))
        assert d.status == "ALLOW", d.details

    def test_record_action_list_covers(self, tmp_path):
        """action записи — список, покрывающий запрошенное действие."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        did = add_decision(repo, sha, action=["create_change", "release"])
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        assert ft.check_action(s, act(approval_ref=did)).status == "ALLOW"


# ------------------------------------------------------------- negatives


class TestInvalidRefs:
    def test_invented_decision_id_rejected(self, tmp_path):
        """Выдуманный decision_id (файла нет) → отказ с подсказкой формата."""
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(
            s, act(approval_ref="2026-10-02-never-recorded"))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert any("decisions/" in x for x in d.details)

    def test_free_form_string_rejected(self, tmp_path):
        """Строка-цитата НЕ из журнала («формат среза 1») → отказ."""
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(
            s, act(approval_ref="чат-лог: «погнали» 2026-10-02"))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)

    def test_wrong_action_rejected(self, tmp_path):
        """Чужой action: запись разрешает release, а не create_change."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        did = add_decision(repo, sha, action="release")
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref=did))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert any("release" in x for x in d.details)

    def test_wrong_scope_change_rejected(self, tmp_path):
        """Чужой scope: запись про другой change_id."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        did = add_decision(repo, sha, scope={"project": "proj",
                                             "change_id": "other-change",
                                             "phase": 1})
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref=did))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert any("change_id=other-change" in x for x in d.details)

    def test_wrong_scope_phase_rejected(self, tmp_path):
        """Решение другой фазы не переносится (спека, существующий сценарий,
        теперь через журнал)."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        did = add_decision(repo, sha, scope={"project": "proj",
                                             "change_id": "add-widget",
                                             "phase": 2})
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref=did))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)

    def test_expired_expiration_rejected(self, tmp_path):
        """Истекший expiration → отказ «истекло»."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00")
        did = add_decision(repo, sha, expiration=past)
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref=did))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert any("истекло" in x for x in d.details)

    def test_future_sha_rejected(self, tmp_path):
        """SHA записи «из будущего» (не предок HEAD) → STALE_EVIDENCE:
        решение не может быть принято после изменения, ломающего его
        применимость."""
        repo = make_repo(tmp_path)
        did = add_decision(repo, "f" * 40)  # несуществующий SHA
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref=did))
        assert d.status == "DENY"
        assert has_code(d, ft.STALE_EVIDENCE)

    def test_corrupt_record_rejected(self, tmp_path):
        """Побитая запись (нет машиночитаемого блока) → отказ, не «на глаз»."""
        repo = make_repo(tmp_path)
        write(repo, "decisions/2026-10-02-broken-record.md",
              "# Решение без блока\n\nтолько текст\n")
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref="2026-10-02-broken-record"))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert any("decision-record" in x for x in d.details)

    def test_bad_schema_version_rejected(self, tmp_path):
        """Нераспознанная schema_version → отказ (контракт §2)."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        write(repo, "decisions/2026-10-02-old-schema.md",
              decision_record_text(sha, "2026-10-02-old-schema",
                                   schema="decision-record/99"))
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref="2026-10-02-old-schema"))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)

    def test_path_traversal_id_rejected(self, tmp_path):
        """decision_id с разделителями путей не превращается в чтение файла
        вне decisions/ (шаблон ID отсекает traversal)."""
        repo = make_repo(tmp_path)
        write(repo, "decisions/../../../etc-passwd-note.md", "зло")
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref="../../2026-10-02-evil"))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)

    def test_no_repo_string_ref_rejected(self, tmp_path):
        """Строковый ref без контекста репозитория — честный отказ, не
        молчаливое разрешение."""
        f = ft._approval_finding(
            act(approval_ref="2026-10-02-something"),
            {"project": "proj"}, "create_change", repo=None)
        assert f is not None and f.code == ft.HUMAN_APPROVAL_REQUIRED


# --------------------------------------------------------------- release


class TestReleaseViaLog:
    def _released_repo(self, tmp_path: Path):
        """Релизный комплект как в test_enforcement_facts: задачи закрыты,
        change заархивирован, дельты слиты, protection ok."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        write(repo, "openspec/changes/add-widget/tasks.md",
              "- [x] 1.1 готово\n- [x] 1.2 обычная\n")
        write(repo, "test-model/approved/add-widget/TC-WID-001.md", "# TC\n")
        commit_all(repo, "ready to archive")
        # архивация: пакет + слитые дельты (rename через shutil, не git mv)
        import shutil
        src = repo / "openspec" / "changes" / "add-widget"
        dst = repo / "openspec" / "changes" / "archive" / "add-widget"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        commit_all(repo, "archive")
        flow_state.OPENSPEC_VALIDATE_CMD = lambda r, a: 0
        return repo, sha

    def teardown_method(self):
        flow_state.OPENSPEC_VALIDATE_CMD = None

    def test_release_by_decision_log_record(self, tmp_path):
        """release по записи журнала решений (вместо releases/<id>.md) —
        ворота Заказчика исполнены (остается внешний UNKNOWN → не ALLOW)."""
        repo, sha = self._released_repo(tmp_path)
        did = add_decision(repo, sha, action="release")
        commit_all(repo, "decision log entry")
        d = ft.check_action(snapshot_for(repo, make_registry(tmp_path)),
                            act(requested_action="release", actor_role="pm",
                                approval_ref=did))
        assert d.status == "UNKNOWN", d.details  # branch protection UNKNOWN
        assert not has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)


# ------------------------------------------------------ record-decision CLI


class TestRecordDecisionCLI:
    def test_record_and_check_roundtrip(self, tmp_path):
        """record-decision пишет валидную запись; flow_transition ее принимает
        (сквозной прогон: запись → ворота)."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "record-decision", "--repo", str(repo),
             "--decision-id", "2026-10-02-roundtrip",
             "--project", "proj", "--change", "add-widget", "--phase", "1",
             "--action", "create_change", "--commit", sha,
             "--source", "чат-лог", "--quote", "погнали", "--json"],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert "решение зафиксировано" not in proc.stderr
        import json
        payload = json.loads(proc.stdout)
        assert payload["schema_version"] == "decision-record/1"
        text = (repo / "decisions" / "2026-10-02-roundtrip.md").read_text()
        assert "решение зафиксировано" in text
        assert "личность подтверждена" in text  # формулировка-отрицание
        commit_all(repo, "decision log entry")
        d = ft.check_action(snapshot_for(repo, make_registry(tmp_path)),
                            act(approval_ref="2026-10-02-roundtrip"))
        assert d.status == "ALLOW", d.details

    def test_record_decision_rejects_bad_input(self, tmp_path):
        repo = make_repo(tmp_path)
        base = [sys.executable, str(SCRIPTS / "gate_runner.py"),
                "record-decision", "--repo", str(repo)]
        cases = [
            base + ["--decision-id", "нет-формата", "--project", "proj",
                    "--action", "create_change", "--commit", "a" * 40,
                    "--source", "s"],
            base + ["--decision-id", "2026-10-02-ok", "--project", "proj",
                    "--action", "create_change", "--commit", "не-ша",
                    "--source", "s"],
            base + ["--decision-id", "2026-10-02-ok", "--project", "proj",
                    "--action", "create_change", "--commit", "a" * 40],
            base + ["--decision-id", "2026-10-02-ok", "--action",
                    "create_change", "--commit", "a" * 40, "--source", "s"],
        ]
        for cmd in cases:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            assert proc.returncode == 2, cmd
            assert ("GATE-RUNNER-ERROR" in proc.stderr
                    or "arguments are required" in proc.stderr)

    def test_record_decision_no_overwrite(self, tmp_path):
        """Append-only: существующая запись не перезаписывается молча."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        base = [sys.executable, str(SCRIPTS / "gate_runner.py"),
                "record-decision", "--repo", str(repo),
                "--decision-id", "2026-10-02-twice", "--project", "proj",
                "--action", "create_change", "--commit", sha, "--source", "s"]
        assert subprocess.run(base, capture_output=True).returncode == 0
        proc = subprocess.run(base, capture_output=True, text=True)
        assert proc.returncode == 2
        assert "append-only" in proc.stderr

    def test_record_decision_commit_auto(self, tmp_path):
        """--commit auto → привязка к текущему HEAD."""
        repo = make_repo(tmp_path)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "record-decision", "--repo", str(repo),
             "--decision-id", "2026-10-02-auto", "--project", "proj",
             "--action", "create_change", "--commit", "auto",
             "--source", "s", "--json"],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        import json
        assert json.loads(proc.stdout)["commit"] == git(repo, "rev-parse", "HEAD")


# ----------------------------------------------------------- независимость


class TestNotASignature:
    def test_agent_self_write_does_not_satisfy_independence(self, tmp_path):
        """Самозапись агентом в ходе задачи НЕ покрывает требование
        независимости: journal-запись, созданная в рабочей зоне (uncommitted
        или валидная формально), дает «решение зафиксировано», но проверка
        НЕ утверждает подтвержденной личности Заказчика. В Decision нет
        утверждений о личности; формулировка gates — «решение
        зафиксировано» (спека «Честная граница»; контракт §10)."""
        repo = make_repo(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        did = add_decision(repo, sha)  # запись рабочей зоны, не коммит
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(approval_ref=did))
        assert d.status == "ALLOW"
        joined = " ".join(d.details + d.evidence_refs)
        assert "личность" not in joined
        # Нет поля/утверждения «подпись подтверждена».
        assert not any("подпис" in x for x in d.details)

    def test_record_text_uses_fixed_wording(self, tmp_path):
        """Формулировка записи: «решение зафиксировано», не «личность
        подтверждена» (P0.4; пересмотр плана п.3)."""
        repo = make_repo(tmp_path)
        payload = gate_runner.write_decision_record(
            repo, "2026-10-02-wording", {"project": "proj"},
            "create_change", git(repo, "rev-parse", "HEAD"), "чат-лог")
        text = (repo / "decisions" / "2026-10-02-wording.md").read_text()
        assert "решение зафиксировано" in text
        assert "НЕ является независимым одобрением" in text
