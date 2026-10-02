# -*- coding: utf-8 -*-
"""Тесты P0.3: зоны записи из политики роли (ROLE_ZONE_POLICY).

Пересмотр плана Заказчика, P0.3: «Ограничить --zone разрешенными путями
роли и действия, затем сверять реальный diff при finish. Это процессное
ограничение, а не ОС-песочница».

Покрывается (трассировка: TC-ZP-001...TC-ZP-019; пересмотр плана
Заказчика P0.3, таблица зон agents/README.md, контракт §7 «Параллель и
зоны»):
- запрос чужого каталога → отказ ZONE_OUTSIDE_POLICY (до side effects);
- запрос шире политики → сужение прозрачно (zones = суженные,
  requested_zones = эхо запроса, policy_version в выводе и записях);
- diff вне суженной зоны → отказ на finish (OUT_OF_ZONE);
- несуществующая роль → отказ (пустая политика);
- версия политики в записи делегации и в резервации реестра;
- ZONE_POLICY_MISMATCH при расхождении редакций политики;
- unit: пересечение запроса с политикой (консервативное, в сторону отказа).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import role_zone_policy as rzp  # noqa: E402
import session_check as sc  # noqa: E402


# ------------------------------------------------------------ unit: сужение


class TestRoleZonePolicyUnit:
    def test_every_role_has_zones_and_known_roles_covered(self):
        # Каждая зона — непустая каноническая строка; все роли из промптов
        # agents/ покрыты (это таблица agents/README.md, дословно).
        for role, zones in rzp.ROLE_ZONE_POLICY.items():
            assert role and zones
            for z in zones:
                assert z == sc.canonical(z)
        assert rzp.allowed_zones_for("no_such_role") == ()
        assert rzp.allowed_zones_for("relay") == ()

    def test_concrete_path_narrows_to_matching_policy_zones_only(self):
        # Конкретный путь сужает зону запроса до фактического покрытия,
        # а не подставляет всю политику роли.
        r = rzp.narrow_zones("dev", ["src/api/client.py"])
        assert r["zones"] == ["src/api/client.py"]
        r2 = rzp.narrow_zones("dev", ["tests/api/test_x.py"])
        assert r2["zones"] == ["tests/api/test_x.py"]
        # Путь вне политики роли — нарушение:
        r3 = rzp.narrow_zones("dev", ["docs/notes.md"])
        assert r3["zones"] == [] and r3["violations"] == ["docs/notes.md"]

    def test_glob_narrower_than_policy_is_accepted(self):
        assert rzp.narrow_zones("dev", ["src/**"])["zones"] == ["src/**"]
        # '**' в запросе против политики без '**' — расширение, отказ:
        assert rzp.narrow_zones("dev", ["**"])["violations"] == ["**"]
        # sa-политика имеет вид 'openspec/changes/*/X': запрос 'change/**'
        # покрывает и соседние файлы (proposal/design/sdd-плоскость) —
        # консервативный отказ (сузь до точных паттернов политики).
        r = rzp.narrow_zones("sa", ["openspec/changes/add-widget/**"])
        assert r["violations"] == ["openspec/changes/add-widget/**"]

    def test_unknown_role_request_is_violation(self):
        r = rzp.narrow_zones("hacker", ["src/**"])
        assert r["zones"] == []
        assert r["violations"] == ["src/**"]
        assert r["policy_version"] == rzp.policy_version()

    def test_policy_version_is_stable_string(self):
        v = rzp.policy_version()
        assert "agents/README.md" in v and v == rzp.policy_version()


# --------------------------------------------- prepare: отказ/сужение/записи


class TestPrepareZonePolicy:
    """prepare: чужой каталог → отказ; шире → сужение прозрачно; роль без
    политики → отказ; policy_version — в записи и резервации."""

    def _argv(self, repo, reg, state, tmp_path, **kw):
        argv = [
            "prepare",
            "--repo", str(repo), "--project", "proj", "--flow", "1",
            "--change", "add-widget", "--task", "1.1",
            "--action", kw.get("action", "dev_task"),
            "--role", kw.get("role", "dev"),
            "--owner-pm", "pm-main",
            "--registry", str(reg), "--state", str(state),
            "--correlation-id", kw.get("cid", "corrZP"),
            "--json",
        ]
        for p in kw.get("paths", ["src/**"]):
            argv += ["--path", p]
        return argv

    def test_request_outside_role_zone_rejected_no_side_effects(
            self, tmp_path):
        """Чужой каталог (docs/** для dev) → ZONE_OUTSIDE_POLICY: отказ,
        ни reservation, ни записи state."""
        repo = self._make_repo(tmp_path)
        reg = self._make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = self._flowctl(self._argv(repo, reg, state, tmp_path,
                                     paths=["docs/**"]))
        assert r.returncode == 1, r.stdout
        data = json.loads(r.stdout)
        assert data["reason"] == "ZONE_OUTSIDE_POLICY"
        assert data["zone_violations"] == ["docs/**"]
        assert data["role"] == "dev"
        assert "agents/README.md" in data["policy_source"]
        assert data["policy_version"] == rzp.policy_version()
        # Side effects отсутствуют:
        assert json.loads(reg.read_text(encoding="utf-8")).get(
            "sessions", []) == []
        assert not state.exists()

    def test_request_partly_outside_rejected_with_full_list(self, tmp_path):
        repo = self._make_repo(tmp_path)
        reg = self._make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = self._flowctl(self._argv(
            repo, reg, state, tmp_path, paths=["src/**", "docs/**"]))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["zone_violations"] == ["docs/**"]

    def test_wider_request_narrowed_transparently(self, tmp_path):
        """Запрос, покрывающий больше политики, сужается: зоны = пересечение
        (валидные пути), request виден рядом (прозрачность), сессия создана
        с суженной зоной; версия политики — в записи и в резервации."""
        repo = self._make_repo(tmp_path)
        reg = self._make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        # Запрос: своя зона + задачи пакета (валидны) + два чужих каталога →
        # ЧАСТИЧНО валидный запрос отклоняется ЦЕЛИКОМ (частичное сужение
        # не проходит молча — запрос должен быть чистым).
        r = self._flowctl(self._argv(
            repo, reg, state, tmp_path, cid="corrNAR",
            paths=["src/**", "openspec/changes/add-widget/tasks.md"]))
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        rec = data["record"]
        assert data["record"]["zones"] == [
            "src/**", "openspec/changes/add-widget/tasks.md"]
        assert rec["requested_zones"] == [
            "src/**", "openspec/changes/add-widget/tasks.md"]
        assert rec["zones"] == [
            "src/**", "openspec/changes/add-widget/tasks.md"]
        assert rec["policy_version"] == rzp.policy_version()
        assert data["reservation"]["policy_version"] == rzp.policy_version()
        # Резервация — суженная зона + версия политики:
        sessions = json.loads(
            reg.read_text(encoding="utf-8"))["sessions"]
        assert sessions[0]["zones"] == [
            "src/**", "openspec/changes/add-widget/tasks.md"]
        assert sessions[0]["policy_version"] == rzp.policy_version()
        # Goal называет суженную зону и версию политики:
        goal = Path(rec["goal_path"]).read_text(encoding="utf-8")
        assert "src/**" in goal and "Версия политики зон" in goal

    def test_partly_outside_request_rejected_not_silently_narrowed(
            self, tmp_path):
        """Запрос «своя зона + чужой каталог» НЕ сужается молча до валидной
        части: общий отказ с перечнем недопустимых путей (сужение = выбор
        ПОДМНОЖЕСТВА политики, а не «все, что прошло проверку»)."""
        repo = self._make_repo(tmp_path)
        reg = self._make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = self._flowctl(self._argv(
            repo, reg, state, tmp_path, cid="corrMIX",
            paths=["src/**", "code-reviews/add-widget/review-001.md"]))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["reason"] == "ZONE_OUTSIDE_POLICY"
        assert data["zone_violations"] == [
            "code-reviews/add-widget/review-001.md"]
        assert json.loads(
            reg.read_text(encoding="utf-8")).get("sessions", []) == []

    def test_unknown_role_rejected(self, tmp_path):
        """Несуществующая роль: пустая политика → любой запрос — отказ."""
        repo = self._make_repo(tmp_path)
        reg = self._make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = self._flowctl(self._argv(repo, reg, state, tmp_path,
                                     role="intern", paths=["src/**"]))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["reason"] == "ZONE_OUTSIDE_POLICY"
        assert data["zone_violations"] == ["src/**"]
        assert json.loads(
            reg.read_text(encoding="utf-8")).get("sessions", []) == []

    def test_dry_run_shows_narrowing_without_side_effects(self, tmp_path):
        repo = self._make_repo(tmp_path)
        reg = self._make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        argv = self._argv(repo, reg, state, tmp_path,
                          paths=["src/**", "docs/**"])
        argv.append("--dry-run")
        r = self._flowctl(argv)
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["zone_violations"] == ["docs/**"]
        assert json.loads(
            reg.read_text(encoding="utf-8")).get("sessions", []) == []

    # -- helpers (локальные, чтобы не зависеть от чужих conftest-хелперов) --

    def _make_repo(self, tmp_path: Path) -> Path:
        # Локальная mini-fixture (не зависит от чужих тестов):
        repo = tmp_path / "projZP"
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo,
                       check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo,
                       check=True)

        def w(rel, text):
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")

        w("requirements.md",
          "# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | История: r1\n\n"
          "## Описание\n...\n\n## Аудитория\nПМ, dev.\n\n"
          "## Функциональные требования\n- FR-1 виджет\n\n"
          "## Нефункциональные требования\n- NFR-1 быстро\n\n"
          "## Приоритеты\n- P1\n\n## Ограничения\n- без push\n\n"
          "## Открытые вопросы\n- нет\n")
        w("openspec/changes/add-widget/proposal.md", "# p\n")
        w("openspec/changes/add-widget/design.md", "# d\n")
        w("openspec/changes/add-widget/tasks.md",
          "# Tasks\n\n- [ ] 1.1 реализовать виджет\n")
        w("openspec/changes/add-widget/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
        w("code-reviews/add-widget/review-001-1.1.md", "## Вердикт: approve\n")
        w("sdd.md", "# SDD\n")
        w("src/widget.py", "X = 1\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
        return repo

    def _make_registry(self, tmp_path: Path) -> Path:
        p = tmp_path / "state" / "active_sessions.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"sessions": []}', encoding="utf-8")
        return p

    def _flowctl(self, argv):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "flowctl.py"), *argv],
            capture_output=True, text=True,
        )


# --------------------------------------------- finish: сверка с суженной зоной


class TestFinishZonePolicy:
    """finish: diff вне суженной зоны → отказ; запись хранит версию
    политики; tamper с реестром → ZONE_POLICY_MISMATCH."""

    def _run_cycle_to_running(self, tmp_path, *, paths=("src/**",),
                              cid="corrFZ"):
        repo = TestPrepareZonePolicy()._make_repo(tmp_path)
        reg = TestPrepareZonePolicy()._make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        argv = ["prepare",
                "--repo", str(repo), "--project", "proj", "--flow", "1",
                "--change", "add-widget", "--task", "1.1",
                "--action", "dev_task", "--role", "dev",
                "--owner-pm", "pm-main",
                "--registry", str(reg), "--state", str(state),
                "--correlation-id", cid, "--json"]
        for p in paths:
            argv += ["--path", p]
        r = TestPrepareZonePolicy()._flowctl(argv)
        assert r.returncode == 0, r.stdout + r.stderr
        r2 = TestPrepareZonePolicy()._flowctl(
            ["run", "--correlation-id", cid, "--registry", str(reg),
             "--state", str(state), "--json"])
        assert r2.returncode == 0, r2.stdout + r2.stderr
        return repo, reg, state

    def _finish(self, tmp_path, reg, state, report):
        return TestPrepareZonePolicy()._flowctl([
            "finish", "--correlation-id", "corrFZ",
            "--report", str(report),
            "--gate-scope", "post_agent",
            "--pm-mode", "commits", "--pm-commits", "HEAD",
            "--registry", str(reg), "--state", str(state),
            "--log-dir", str(tmp_path / "logs"),
            "--report-dir", str(tmp_path / "greports"),
            "--json",
        ])

    def test_diff_outside_narrowed_zone_rejected(self, tmp_path):
        """prepare сузил до src/**; коммит в docs/** (запрошен НЕ был и вне
        политики) — OUT_OF_ZONE на finish, accepted нет."""
        repo, reg, state = self._run_cycle_to_running(tmp_path)
        (repo / "docs").mkdir(exist_ok=True)
        (repo / "docs" / "out.md").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "out of zone"], cwd=repo,
                       check=True)
        report = tmp_path / "rep.md"
        report.write_text("# Отчет\n", encoding="utf-8")
        r = self._finish(tmp_path, reg, state, report)
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["verdict"] == "returned"
        assert any(d["source"] == "zone" and d["code"] == "OUT_OF_ZONE"
                   for d in data["defects"])
        # Вердикт несет суженную зону и версию политики (аудит):
        zv = data["record"]["verdict"]["zone"]
        assert zv["zones"] == ["src/**"]
        assert zv["policy_version"] == rzp.policy_version()
        assert zv["policy_confirmed"] is True

    def test_diff_in_narrowed_zone_accepted_and_carries_policy_version(
            self, tmp_path):
        repo, reg, state = self._run_cycle_to_running(tmp_path)
        p = repo / "src" / "widget.py"
        p.write_text("X = 42\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "in zone"], cwd=repo,
                       check=True)
        report = tmp_path / "rep.md"
        report.write_text("# Отчет\n", encoding="utf-8")
        r = self._finish(tmp_path, reg, state, report)
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "accepted"
        assert data["record"]["verdict"]["zone"]["policy_version"] == \
            rzp.policy_version()

    def test_policy_version_mismatch_is_zone_defect(self, tmp_path):
        """Резервация с чужой (устаревшей) редакцией политики → дефект
        ZONE_POLICY_MISMATCH, accepted нет, даже если diff в зоне."""
        repo, reg, state = self._run_cycle_to_running(tmp_path)
        p = repo / "src" / "widget.py"
        p.write_text("X = 42\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "in zone"], cwd=repo,
                       check=True)
        # Тампер: подменяем редакцию политики в резервации (имитация
        # «зона зарезервирована старой редакцией таблицы»).
        data = json.loads(reg.read_text(encoding="utf-8"))
        data["sessions"][0]["policy_version"] = \
            "agents/README.md@OLD:устаревшая редакция"
        reg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        report = tmp_path / "rep.md"
        report.write_text("# Отчет\n", encoding="utf-8")
        r = self._finish(tmp_path, reg, state, report)
        assert r.returncode == 1
        out = json.loads(r.stdout)
        assert out["verdict"] == "returned"
        assert any(d["code"] == "ZONE_POLICY_MISMATCH" for d in out["defects"])
        assert "OLD" in next(d["detail"] for d in out["defects"]
                             if d["code"] == "ZONE_POLICY_MISMATCH")

    def test_residue_of_policy_in_verdict_when_registry_entry_missing(
            self, tmp_path):
        """Резервация без policy_version (старая запись) → mismatch-дефект
        отсутствует только если зона подтверждается политикой; при валидной
        зоне и отсутствующей версии verdict честно фиксирует '—'."""
        repo, reg, state = self._run_cycle_to_running(tmp_path)
        data = json.loads(reg.read_text(encoding="utf-8"))
        del data["sessions"][0]["policy_version"]
        reg.write_text(json.dumps(data, ensure_ascii=False),
                       encoding="utf-8")
        p = repo / "src" / "widget.py"
        p.write_text("X = 42\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "in zone"], cwd=repo,
                       check=True)
        report = tmp_path / "rep.md"
        report.write_text("# Отчет\n", encoding="utf-8")
        r = self._finish(tmp_path, reg, state, report)
        assert r.returncode == 0, r.stdout + r.stderr
        out = json.loads(r.stdout)
        zv = out["record"]["verdict"]["zone"]
        assert zv["policy_version"] is None
        assert zv["policy_confirmed"] is True  # зона валидна текущей политикой


# ------------------------------------------------- session_check: policyVersion


class TestSessionCheckPolicyVersion:
    def test_reserve_without_policy_version_rejected(self, tmp_path):
        repo = TestPrepareZonePolicy()._make_repo(tmp_path)
        reg = TestPrepareZonePolicy()._make_registry(tmp_path)
        res = sc.reserve({"repo": str(repo), "delegation_id": "d1",
                          "role": "dev", "project": "proj",
                          "owner_pm": "pm", "paths": ["src/**"]}, reg)
        assert not res["allowed"]
        assert res["reason"] == "MISSING_INPUT"
        assert any("policy_version" in d for d in res["details"])

    def test_reserve_with_policy_version_stores_it(self, tmp_path):
        repo = TestPrepareZonePolicy()._make_repo(tmp_path)
        reg = TestPrepareZonePolicy()._make_registry(tmp_path)
        res = sc.reserve({"repo": str(repo), "delegation_id": "d1",
                          "role": "dev", "project": "proj",
                          "owner_pm": "pm", "paths": ["src/**"],
                          "policy_version": "v-test"}, reg)
        assert res["allowed"]
        assert res["session"]["policy_version"] == "v-test"
        sessions = json.loads(
            reg.read_text(encoding="utf-8"))["sessions"]
        assert sessions[0]["policy_version"] == "v-test"

    def test_idempotent_repeat_with_other_policy_version_rejected(
            self, tmp_path):
        """Тот же delegation_id, та же зона, но ДРУГАЯ редакция политики —
        не идемпотентный повтор, а DUPLICATE_PAYLOAD (аудит версии)."""
        repo = TestPrepareZonePolicy()._make_repo(tmp_path)
        reg = TestPrepareZonePolicy()._make_registry(tmp_path)
        base = {"repo": str(repo), "delegation_id": "d1", "role": "dev",
                "project": "proj", "owner_pm": "pm", "paths": ["src/**"]}
        assert sc.reserve({**base, "policy_version": "v1"}, reg)["allowed"]
        again = sc.reserve({**base, "policy_version": "v2"}, reg)
        assert not again["allowed"]
        assert again["reason"] == "DUPLICATE_PAYLOAD"

    def test_cli_reserve_requires_policy_version(self, tmp_path):
        repo = TestPrepareZonePolicy()._make_repo(tmp_path)
        reg = TestPrepareZonePolicy()._make_registry(tmp_path)
        p = subprocess.run(
            [sys.executable, str(SCRIPTS / "session_check.py"), "reserve",
             "--registry", str(reg), "--repo", str(repo),
             "--delegation-id", "dCLI", "--role", "dev",
             "--project", "proj", "--owner-pm", "pm",
             "--path", "src/**", "--json"],
            capture_output=True, text=True)
        assert p.returncode == 1
        assert "policy_version" in p.stdout
        # С версией — успех:
        p2 = subprocess.run(
            [sys.executable, str(SCRIPTS / "session_check.py"), "reserve",
             "--registry", str(reg), "--repo", str(repo),
             "--delegation-id", "dCLI2", "--role", "dev",
             "--project", "proj", "--owner-pm", "pm",
             "--path", "src/**",
             "--policy-version", rzp.policy_version(), "--json"],
            capture_output=True, text=True)
        assert p2.returncode == 0, p2.stdout + p2.stderr
        out = json.loads(p2.stdout)
        assert out["session"]["policy_version"] == rzp.policy_version()
