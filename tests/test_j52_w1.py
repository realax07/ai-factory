# -*- coding: utf-8 -*-
"""J52 волна 1 «машина»: деривация веток, flowctl release, домены-кейсы.

J52-w1.1 (шов пилота J51 #1): ветка делегации — ПОЛНЫЙ correlation-id;
длинный/небезопасный id → суффикс-хэш sha1[:8] от полного id, НЕ обрезка
8 символов (j51-pilot-A/B коллизировали в одну ветку flow/j51-pilo).

J52-w1.2 (шов пилота J51 #3): flowctl release <correlation-id> [--reason] —
явный сброс needs_attention/reserved-сессий решением ПМ: сессия → статус
"released" (зона освобождена), НИЧЕГО не удаляется молча (запись реестра и
worktree сохраняются), решение с причиной — в audit.

J52-w1.3 (решение Заказчика 2026-10-18): гранулярность доменов regress =
структура тест-кейсов; проектная карта доменов
test-model/regress-domains.json (контент у проекта — как J53), дефолт —
текущее поведение (frontend/→tests/web, backend/→tests/api, остальное→tests).

Трассировка:
  TC-J52-001  branch_name_for: коллизия префиксов — j51-pilot-A/B → разные
              ветки, полные id сохранены, обрезки flow/j51-pilo нет
  TC-J52-002  branch_name_for: длинный id (>40) → sha1[:8] от полного id,
              детерминированно; общий префикс ≠ общий хэш
  TC-J52-003  branch_name_for: небезопасные id → хэш; uuid4.hex → полный
  TC-J52-004  prepare --create-worktree без --branch: ветка из полного
              correlation-id в плане и записи цикла (не [:8])
  TC-J52-005  release reserved-сессии: статус released, зона освобождена,
              запись/worktree сохранены, решение в audit с --reason
  TC-J52-006  release needs_attention-сессии (после reconcile-разметки)
  TC-J52-007  release running-сессии → отказ (exit 1), статус не тронут
  TC-J52-008  release повторно → идемпотентно, audit-событие не дублируется
  TC-J52-009  release: неизвестный correlation-id → exit 2; без id → exit 2;
              позиционная форма работает
  TC-J52-010  release finished-сессии → отказ (штатный путь — finish)
  TC-J52-011  домены, дефолт: карты нет → дефолтное поведение (маппинг и
              свертка BUG-video-001), load_domain_map → "default"
  TC-J52-012  домены, карта: правила проекта приоритетны, collapse выключен
  TC-J52-013  regress e2e с картой: сьюты = кейс-домены проекта, артефакт
              и payload несут источник карты
  TC-J52-014  битая карта → заметный дефолт (диагностика в payload/артефакте)
  TC-J52-015  regress e2e с картой: несколько кейс-доменов НЕ сворачиваются
              в общий tests/ (карта = кейс-структура проекта)
  TC-J52-016  regress e2e: кейс-домен карты затронут диффом, но каталога
              нет → WARN-исход (не молчаливый PASS), домен в suites skipped
  TC-J52-017  release: гонка с «агент стартовал» — статус reserved→running
              между чтением prev и захватом лока → отказ (exit 1, статус
              сохранен); registry_transition: expect_from не совпал →
              status_changed
  TC-J52-018  branch_name_for: формы, отвергаемые git (a.lock/b, a//b,
              a/.x) → хэш-фолбэк; финальный арбитр git check-ref-format
  TC-J52-019  regress: частичный skip (часть кейс-доменов без каталога) →
              WARN, не PASS (review-001 #3)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
for p in (str(SCRIPTS),):
    if p not in sys.path:
        sys.path.insert(0, p)

import flowctl  # noqa: E402
import session_check as sc  # noqa: E402
from test_flowctl import (  # noqa: E402
    commit_all,
    flowctl_cmd,
    make_registry,
    make_repo,
    prepare_argv,
    registry_sessions,
    write,
)


# --------------------------------------------------------------- helpers

def stage(repo: Path, rel: str, text: str) -> None:
    write(repo, rel, text)
    subprocess.run(["git", "-C", str(repo), "add",
                    rel.replace("\\", "/")], check=True)


def prepare_with_worktree(tmp_path: Path, cid: str = "j52-branch-full-id",
                          **kw) -> tuple[dict, Path]:
    """prepare --create-worktree на fixture-репо Флоу 1 → (ALLOW-объект, reg)."""
    repo = make_repo(tmp_path)
    reg = make_registry(tmp_path)
    state = tmp_path / "state" / "flowctl_state.json"
    argv = prepare_argv(repo, reg, state, tmp_path, cid=cid, **kw)
    argv += ["--create-worktree"]
    r = flowctl_cmd(*argv)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout), reg


def release_argv(reg: Path, state: Path, audit: Path, cid: str = None,
                 reason: str = None) -> list[str]:
    argv = ["release", "--registry", str(reg), "--state", str(state),
            "--audit", str(audit), "--json"]
    if cid:
        argv.insert(1, cid)
    if reason:
        argv += ["--reason", reason]
    return argv


def audit_events(audit: Path) -> list[dict]:
    return [json.loads(ln) for ln in
            audit.read_text(encoding="utf-8").splitlines() if ln.strip()]


def state_runs(state: Path) -> dict:
    return json.loads(state.read_text(encoding="utf-8"))["runs"]


# ------------------------------------------- J52-w1.1: деривация веток

class TestBranchDerivation:
    def test_prefix_collision_j51_pilot(self):
        """TC-J52-001: два id с общим префиксом → разные ветки; полные id
        сохранены; обрезки до 8 символов (flow/j51-pilo) больше нет."""
        a = flowctl.branch_name_for("j51-pilot-A")
        b = flowctl.branch_name_for("j51-pilot-B")
        assert a == "flow/j51-pilot-A"
        assert b == "flow/j51-pilot-B"
        assert a != b
        assert a != "flow/j51-pilo" and b != "flow/j51-pilo"

    def test_long_id_hash_suffix(self):
        """TC-J52-002: id длиннее BRANCH_MAX_ID_LEN → sha1[:8] от ПОЛНОГО id;
        детерминированно; общий префикс не рождает общий хэш."""
        long_a = "deleg-" + "a" * 60
        long_b = "deleg-" + "a" * 59 + "b"   # тот же 8-символьный префикс
        ha = flowctl.branch_name_for(long_a)
        hb = flowctl.branch_name_for(long_b)
        assert ha == "flow/" + hashlib.sha1(long_a.encode()).hexdigest()[:8]
        assert hb == "flow/" + hashlib.sha1(long_b.encode()).hexdigest()[:8]
        assert ha != hb
        assert ha == flowctl.branch_name_for(long_a)  # детерминизм

    def test_unsafe_and_full_ids(self):
        """TC-J52-003: небезопасные как git-ref id → хэш; uuid4.hex (32)
        и точечные id — полный id в ветке."""
        for bad in ("с пробелом", "a..b", "-leading-dash", "x.lock",
                    "trailing.", "a@{b", "x" * 41):
            assert flowctl.branch_name_for(bad).startswith("flow/")
            assert flowctl.branch_name_for(bad) == (
                "flow/" + hashlib.sha1(bad.encode()).hexdigest()[:8])
        assert flowctl.branch_name_for("f" * 32) == "flow/" + "f" * 32
        assert flowctl.branch_name_for("chore.j52_w1") == "flow/chore.j52_w1"

    def test_git_rejected_shapes_fall_back_to_hash(self):
        """TC-J52-018 (review-001 #2): формы, которые git отвергает как имя
        ветки, но пропускал старый гард — компонент с хвостом .lock
        (a.lock/b), пустой компонент (a//b), ведущая точка (a/.x) — идут в
        детерминированный хэш-фолбэк; финальный арбитр git
        check-ref-format --branch подтверждает валидность результата."""
        for bad in ("j52.a.lock/b", "j52//b", "j52/.x"):
            assert flowctl._branch_id_ok(bad) is False
            b = flowctl.branch_name_for(bad)
            assert b == "flow/" + hashlib.sha1(bad.encode()).hexdigest()[:8]
            chk = subprocess.run(
                ["git", "check-ref-format", "--branch", b],
                capture_output=True, text=True)
            assert chk.returncode == 0, b
        # Валидные id по-прежнему идут полным id (не хэшем).
        assert flowctl.branch_name_for("chore/j52-w1") == "flow/chore/j52-w1"
        assert flowctl._branch_id_ok("chore.j52_w1") is True

    def test_prepare_uses_full_id_branch(self, tmp_path):
        """TC-J52-004: prepare --create-worktree без --branch → ветка из
        полного correlation-id (план, запись цикла, reservation)."""
        data, reg = prepare_with_worktree(tmp_path, cid="j52-branch-full-id")
        assert data["prepared"] is True
        rec = data["record"]
        assert rec["branch"] == "flow/j52-branch-full-id"
        # Reservation в реестре несет ту же (полную) ветку.
        session = registry_sessions(reg)[0]
        assert session["branch"] == "flow/j52-branch-full-id"
        # Дубль-проверка деривации: ветка NOT [:8]-обрезка.
        assert rec["branch"] != "flow/j52-bran"


# ------------------------------------------------ J52-w1.2: flowctl release

class TestRelease:
    def _prepared(self, tmp_path, cid="j52-rel-0001"):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        audit = tmp_path / "audit.jsonl"
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path, cid=cid))
        assert r.returncode == 0, r.stdout + r.stderr
        return repo, reg, state, audit

    def test_release_reserved_frees_zone_keeps_everything(self, tmp_path):
        """TC-J52-005: release reserved-сессии — статус released, зона
        освобождена, запись реестра/worktree сохранены, решение в audit."""
        repo, reg, state, audit = self._prepared(tmp_path)
        cid = "j52-rel-0001"
        runs = state_runs(state)
        assert runs[cid]["status"] == "prepared"
        session = registry_sessions(reg)[0]
        delegation_id = session["delegation_id"]

        r = flowctl_cmd(*release_argv(reg, state, audit, cid,
                                      reason="ПМ: делегация отозвана"))
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["released"] is True
        assert data["from_status"] == "reserved"

        # Запись реестра СОХРАНЕНА (не удалена молча), статус released.
        sessions = registry_sessions(reg)
        assert len(sessions) == 1
        assert sessions[0]["status"] == "released"
        assert sessions[0]["delegation_id"] == delegation_id
        assert sessions[0]["worktree"] == session["worktree"]
        hist = sessions[0]["lifecycle"]["history"]
        assert hist[-1]["to"] == "released"
        assert "ПМ: делегация отозвана" in hist[-1]["reason"]

        # Зона освобождена: та же зона резервуется новой делегацией.
        import role_zone_policy as rzp
        narrowed = rzp.narrow_zones("dev", ["src/**"])
        res = sc.reserve({
            "repo": str(repo), "delegation_id": "deleg-j52-next",
            "role": "dev", "project": "proj", "owner_pm": "pm-main",
            "paths": narrowed["zones"],
            "policy_version": narrowed["policy_version"],
        }, reg)
        assert res["allowed"] is True, res

        # state: запись цикла переведена в released, worktree сохранен.
        runs = state_runs(state)
        assert runs[cid]["status"] == "released"
        assert runs[cid]["release"]["worktree_preserved"] == bool(
            session["worktree"])

        # Решение ПМ с причиной — в audit (append-only JSONL).
        ev = [e for e in audit_events(audit) if e["event"] == "release"]
        assert len(ev) == 1
        assert ev[0]["correlation_id"] == cid
        assert ev[0]["from_status"] == "reserved"
        assert ev[0]["reason"] == "ПМ: делегация отозвана"

    def test_release_needs_attention(self, tmp_path):
        """TC-J52-006: needs_attention-сессия (после разметки сбоя) —
        release как явный выход ПМ."""
        repo, reg, state, audit = self._prepared(tmp_path)
        cid = "j52-rel-0001"
        delegation_id = registry_sessions(reg)[0]["delegation_id"]
        tr = flowctl.registry_transition(
            reg, delegation_id, "needs_attention", "reconcile: crash",
            "pid dead, dirty tree")
        assert tr["ok"] is True

        r = flowctl_cmd(*release_argv(reg, state, audit,
                                      cid=cid, reason="разбор завершен"))
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["released"] is True
        assert data["from_status"] == "needs_attention"
        assert registry_sessions(reg)[0]["status"] == "released"
        ev = [e for e in audit_events(audit) if e["event"] == "release"]
        assert ev and ev[0]["from_status"] == "needs_attention"

    def test_release_running_refused(self, tmp_path):
        """TC-J52-007: running-сессия не подлежит release — отказ (exit 1),
        статус и записи не тронуты."""
        repo, reg, state, audit = self._prepared(tmp_path)
        cid = "j52-rel-0001"
        delegation_id = registry_sessions(reg)[0]["delegation_id"]
        assert flowctl.registry_transition(
            reg, delegation_id, "running", "flowctl run", "agent started")

        r = flowctl_cmd(*release_argv(reg, state, audit, cid))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["refused"] is True
        assert registry_sessions(reg)[0]["status"] == "running"
        assert state_runs(state)[cid]["status"] == "prepared"
        assert not [e for e in audit_events(audit)
                    if e["event"] == "release"]

    def test_release_finished_refused(self, tmp_path):
        """TC-J52-010: finished-сессия — не подлежит release (штатный выход
        уже есть); отказ без изменения реестра."""
        repo, reg, state, audit = self._prepared(tmp_path)
        cid = "j52-rel-0001"
        delegation_id = registry_sessions(reg)[0]["delegation_id"]
        assert flowctl.registry_transition(
            reg, delegation_id, "finished", "flowctl finish: accepted",
            "zone ok; gates ok")
        r = flowctl_cmd(*release_argv(reg, state, audit, cid))
        assert r.returncode == 1
        assert registry_sessions(reg)[0]["status"] == "finished"

    def test_release_idempotent(self, tmp_path):
        """TC-J52-008: повторный release → no-op (exit 0, idempotent),
        audit-событие не дублируется."""
        repo, reg, state, audit = self._prepared(tmp_path)
        cid = "j52-rel-0001"
        assert flowctl_cmd(*release_argv(reg, state, audit, cid)
                           ).returncode == 0
        r = flowctl_cmd(*release_argv(reg, state, audit, cid))
        assert r.returncode == 0
        assert json.loads(r.stdout)["idempotent"] is True
        ev = [e for e in audit_events(audit) if e["event"] == "release"]
        assert len(ev) == 1

    def test_release_input_errors_and_positional(self, tmp_path):
        """TC-J52-009: неизвестный correlation-id → exit 2 (ничего не
        тронуто); без id → exit 2; позиционная форма работает."""
        repo, reg, state, audit = self._prepared(tmp_path)
        r = flowctl_cmd(*release_argv(reg, state, audit, "no-such-cid"))
        assert r.returncode == 2
        r = flowctl_cmd(*release_argv(reg, state, audit))
        assert r.returncode == 2
        # Позиционная форма (как в ТЗ: flowctl release <correlation-id>).
        r = flowctl_cmd(*release_argv(reg, state, audit, "j52-rel-0001",
                                      reason="positional ok"))
        assert r.returncode == 0, r.stdout + r.stderr
        assert registry_sessions(reg)[0]["status"] == "released"

    def test_release_race_status_changed_under_lock(self, tmp_path,
                                                    monkeypatch, capsys):
        """TC-J52-017 (review-001 #1, major): гонка release×run — между
        чтением prev и захватом лока сессию переводят reserved→running
        («агент стартовал») → валидация ПОД ЛОКОМ отказывает: exit 1,
        статус running сохранен, audit чист, ПМ повторяет release."""
        import argparse
        repo, reg, state, audit = self._prepared(tmp_path)
        cid = "j52-rel-0001"
        delegation_id = registry_sessions(reg)[0]["delegation_id"]

        real_load = sc.registry_load
        calls = {"n": 0}

        def racing_load(path):
            calls["n"] += 1
            if calls["n"] == 2:
                # 1-й вызов — чтение prev в cmd_release (без лока);
                # 2-й — registry_transition под локом: между ними
                # конкурентный процесс успел записать running.
                data, _ = real_load(path)
                for s in data.get("sessions", []):
                    if s.get("delegation_id") == delegation_id:
                        sc.transition(s, "running", "flowctl run",
                                      "agent started")
                sc.registry_write(path, data)
            return real_load(path)

        monkeypatch.setattr(sc, "registry_load", racing_load)

        args = argparse.Namespace(
            correlation_id_opt=None, correlation_pos=cid,
            reason="ПМ: делегация отозвана", registry=str(reg),
            state=str(state), audit=str(audit), as_json=True)
        rc = flowctl.cmd_release(args)
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["released"] is False and data["refused"] is True
        assert data["from_status"] == "reserved"
        assert data["status_now"] == "running"
        assert "статус изменился" in data["note"]
        assert "повтори release" in data["note"]

        # Реестр НЕ перезаписан released-ом: конкурентный running сохранен.
        assert registry_sessions(reg)[0]["status"] == "running"
        # state и audit не тронуты.
        assert state_runs(state)[cid]["status"] == "prepared"
        assert not [e for e in audit_events(audit)
                    if e["event"] == "release"]

    def test_registry_transition_expect_from_mismatch(self, tmp_path):
        """TC-J52-017 (unit): registry_transition с expect_from — не
        совпало под локом → ok:False reason:status_changed, статус не
        тронут; совпало → переход выполняется."""
        repo, reg, state, audit = self._prepared(tmp_path)
        delegation_id = registry_sessions(reg)[0]["delegation_id"]
        tr = flowctl.registry_transition(
            reg, delegation_id, "released", "test", "evidence",
            expect_from="running")
        assert tr["ok"] is False
        assert tr["reason"] == "status_changed"
        assert tr["current_status"] == "reserved"
        assert registry_sessions(reg)[0]["status"] == "reserved"
        tr = flowctl.registry_transition(
            reg, delegation_id, "released", "test", "evidence",
            expect_from="reserved")
        assert tr["ok"] is True
        assert registry_sessions(reg)[0]["status"] == "released"


# --------------------------------- J52-w1.3: домены regress = тест-кейсы

PROJECT_MAP = {
    "rules": [
        {"prefix": "frontend/editor/", "domain": "tests/editor"},
        {"prefix": "services/billing/", "domain": "tests/billing"},
        # Кейс-структура проекта: каталоги самих кейсов — те же домены
        # (approved-кейсы группируются по доменам).
        {"prefix": "tests/editor/", "domain": "tests/editor"},
        {"prefix": "tests/billing/", "domain": "tests/billing"},
    ]
}


class TestDomainMap:
    def test_default_behavior_without_map(self, tmp_path):
        """TC-J52-011: карты нет — дефолтное поведение полностью сохранено
        (маппинг и свертка BUG-video-001)."""
        repo = make_repo(tmp_path)
        rules, note = flowctl.load_domain_map(repo)
        assert rules == ()
        assert "default" in note
        assert flowctl.regress_domains(["frontend/a.js"]) == ["tests/web"]
        assert flowctl.regress_domains(["backend/x.py"]) == ["tests/api"]
        assert flowctl.regress_domains(["scripts/s.py"]) == ["tests"]
        assert flowctl.regress_domains(
            ["frontend/a.js", "backend/x.py"]) == ["tests"]

    def test_project_rules_priority_and_no_collapse(self):
        """TC-J52-012: правила проекта применяются до дефолтных; при активной
        карте кейс-домены не сворачиваются в общий tests/."""
        prules = (
            ("frontend/editor/", "tests/editor"),
            ("services/billing/", "tests/billing"),
        )
        rules = prules + flowctl.REGRESS_DOMAIN_RULES
        files = ["frontend/editor/app.js", "services/billing/invoice.py"]
        domains = flowctl.regress_domains(files, rules, collapse=False)
        assert domains == ["tests/editor", "tests/billing"]
        # Приоритет проекта: editor-путь забирается правилом проекта,
        # остальные frontend/ — дефолтным tests/web.
        assert flowctl.regress_domains(
            ["frontend/editor/a.js", "frontend/other.js"], rules,
            collapse=False) == ["tests/editor", "tests/web"]

    def test_regress_e2e_with_project_map(self, tmp_path):
        """TC-J52-013: regress e2e с картой — гоняются кейс-домены проекта;
        источник карты в payload и артефакте."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/regress-domains.json",
              json.dumps(PROJECT_MAP, ensure_ascii=False))
        stage(repo, "frontend/editor/toolbar.js", "// tb\n")
        stage(repo, "tests/editor/test_toolbar.py",
              "def test_toolbar():\n    assert True\n")
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j52-map", "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "PASS"
        assert data["domains"] == ["tests/editor"]
        assert data["suites"] == ["tests/editor"]
        assert "project map" in data["domain_map"]
        art = Path(data["artifact"]).read_text(encoding="utf-8")
        assert "domain map: project map" in art
        assert "suites: tests/editor" in art

    def test_regress_broken_map_is_not_silent(self, tmp_path):
        """TC-J52-014: битая карта — не молчаливый дефолт: диагностика в
        payload и артефакте, прогон идет по дефолту."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/regress-domains.json", "{не json")
        stage(repo, "tests/test_ok.py", "def test_ok():\n    assert True\n")
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j52-bad-map", "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["domains"] == ["tests"]     # дефолт: tests/** → tests/
        assert data["suites"] == ["tests"]
        assert data["domain_map"].startswith("error:")
        art = Path(data["artifact"]).read_text(encoding="utf-8")
        assert "domain map: error:" in art

    def test_map_multi_case_domains_not_collapsed(self, tmp_path):
        """TC-J52-015: e2e — несколько затронутых кейс-доменов проекта НЕ
        сворачиваются в общий tests/ (карта = структура тест-кейсов)."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/regress-domains.json",
              json.dumps(PROJECT_MAP, ensure_ascii=False))
        stage(repo, "tests/editor/test_a.py",
              "def test_a():\n    assert True\n")
        stage(repo, "tests/billing/test_b.py",
              "def test_b():\n    assert True\n")
        stage(repo, "frontend/editor/x.js", "//\n")
        stage(repo, "services/billing/y.py", "Y = 1\n")
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j52-map2", "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["domains"] == ["tests/editor", "tests/billing"]
        assert data["suites"] == ["tests/editor", "tests/billing"]
        assert data["pytest_exit"] == 0

    def test_map_missing_domain_dir_warns(self, tmp_path):
        """TC-J52-016: кейс-домен карты затронут диффом, но каталога нет →
        WARN-исход regress (не молчаливый PASS), домен в suites skipped."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/regress-domains.json",
              json.dumps(PROJECT_MAP, ensure_ascii=False))
        stage(repo, "frontend/editor/ghost.js", "//\n")
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j52-ghost", "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["verdict"] == "WARN"
        assert data["suites"] == []
        assert data["suites_skipped"] == ["tests/editor"]

    def test_map_partial_skip_warns_not_pass(self, tmp_path):
        """TC-J52-019 (review-001 #3): частичный skip — часть кейс-доменов
        карты затронута диффом и прогнана, часть без каталога → verdict
        WARN (не PASS), exit 0, затронутый диффом непокрытый домен заметен
        в payload и артефакте."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/regress-domains.json",
              json.dumps(PROJECT_MAP, ensure_ascii=False))
        stage(repo, "frontend/editor/toolbar.js", "// tb\n")
        stage(repo, "tests/editor/test_toolbar.py",
              "def test_toolbar():\n    assert True\n")
        stage(repo, "services/billing/invoice.py", "Y = 1\n")  # tests/billing — каталога нет
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j52-partial", "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "WARN"
        assert data["suites"] == ["tests/editor"]
        assert data["suites_skipped"] == ["tests/billing"]
        art = Path(data["artifact"]).read_text(encoding="utf-8")
        assert "частичный skip" in art
        assert "tests/billing" in art
