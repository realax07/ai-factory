# -*- coding: utf-8 -*-
"""J65.2: ZONE_POLICY_MISMATCH — по зоне своей роли, не по версии реестра.

До J65.2 резервация хранила только policy_version (sha256 всего
agents/roles.json), и finish сравнивал его целиком: любая правка реестра
(зона чужой роли, текст таблицы) роняла все активные сессии — пакеты с
правкой зон приходилось мержить «без активных сессий на VPS» (J64.18,
J65.1, J66). Теперь в резервацию пишется role_zone_digest — отпечаток зоны
своей роли; finish сверяет его. policy_version остается полем аудита.

Трассировка:
  TC-J65-RZD-001  отпечаток роли не зависит от зон других ролей и меняется
                  при любом изменении зоны своей роли (сужение, расширение)
  TC-J65-RZD-002  finish: устаревший policy_version реестра при актуальном
                  отпечатке своей роли — accepted (правка чужой роли сессию
                  не задевает)
  TC-J65-RZD-003  finish: устаревший отпечаток своей роли — ZONE_POLICY_MISMATCH
  TC-J65-RZD-004  легаси-резервация без отпечатка: зона покрыта политикой —
                  accepted; зона вне текущей политики — ZONE_POLICY_MISMATCH
  TC-J65-RZD-005  prepare пишет role_zone_digest в резервацию (flowctl и раннер
                  через session_check.reserve)
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import role_zone_policy as rzp  # noqa: E402
import test_p03_zone_policy as p03  # noqa: E402  (модулем: класс в namespace pytest собрал бы повторно)


_ORIGINAL = copy.deepcopy(rzp.REGISTRY)


def _with_registry(monkeypatch, mutate):
    reg = copy.deepcopy(_ORIGINAL)
    for r in reg["roles"]:
        mutate(r)
    monkeypatch.setattr(rzp, "REGISTRY", reg)


def test_digest_isolated_per_role(monkeypatch):
    """TC-J65-RZD-001."""
    dev0, devops0 = rzp.role_zone_digest("dev"), rzp.role_zone_digest("devops")
    assert dev0.startswith("role=dev sha256 ") and dev0 != devops0

    def widen_devops(r):
        if r["id"] == "devops":
            r["zones"] = list(r["zones"]) + ["infra/**"]
    _with_registry(monkeypatch, widen_devops)
    assert rzp.role_zone_digest("dev") == dev0
    assert rzp.role_zone_digest("devops") != devops0

    def narrow_dev(r):
        if r["id"] == "dev":
            r["zones"] = [z for z in r["zones"] if z != "scripts/**"]
    _with_registry(monkeypatch, narrow_dev)
    assert rzp.role_zone_digest("dev") != dev0

    def reorder_dev(r):   # порядок зон в реестре — не изменение зоны
        if r["id"] == "dev":
            r["zones"] = list(reversed(r["zones"]))
    _with_registry(monkeypatch, reorder_dev)
    assert rzp.role_zone_digest("dev") == dev0


_H = p03.TestFinishZonePolicy()   # помощники цикла prepare→run→finish (без наследования тестов)


class TestFinish:
    def _run_cycle_to_running(self, tmp_path):
        return _H._run_cycle_to_running(tmp_path)

    def _finish(self, tmp_path, reg, state, report):
        return _H._finish(tmp_path, reg, state, report)

    def _commit_in_zone(self, repo):
        (repo / "src" / "widget.py").write_text("X = 42\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "in zone"], cwd=repo, check=True)

    def _tamper(self, reg, **fields):
        data = json.loads(reg.read_text(encoding="utf-8"))
        for k, v in fields.items():
            if v is None:
                data["sessions"][0].pop(k, None)
            else:
                data["sessions"][0][k] = v
        reg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _finish_out(self, tmp_path, reg, state):
        report = tmp_path / "rep.md"
        report.write_text("# Отчет\n", encoding="utf-8")
        r = self._finish(tmp_path, reg, state, report)
        return r, json.loads(r.stdout)

    def test_prepare_writes_digest(self, tmp_path):
        """TC-J65-RZD-005."""
        repo, reg, state = self._run_cycle_to_running(tmp_path)
        s = json.loads(reg.read_text(encoding="utf-8"))["sessions"][0]
        assert s["role_zone_digest"] == rzp.role_zone_digest("dev")
        assert s["policy_version"] == rzp.policy_version()

    def test_other_role_change_does_not_break(self, tmp_path):
        """TC-J65-RZD-002: реестр поменялся (чужая роль) — сессия dev живет."""
        repo, reg, state = self._run_cycle_to_running(tmp_path)
        self._commit_in_zone(repo)
        self._tamper(reg, policy_version="agents/roles.json sha256 OLD-registry")
        r, out = self._finish_out(tmp_path, reg, state)
        assert not any(d["code"] == "ZONE_POLICY_MISMATCH" for d in out["defects"]), out
        assert out["verdict"] == "accepted", out
        rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["corrFZ"]
        assert rec["verdict"]["zone"]["policy_confirmed"] is True
        assert rec["verdict"]["zone"]["role_zone_digest"] == rzp.role_zone_digest("dev")

    def test_own_role_change_is_mismatch(self, tmp_path):
        """TC-J65-RZD-003."""
        repo, reg, state = self._run_cycle_to_running(tmp_path)
        self._commit_in_zone(repo)
        self._tamper(reg, role_zone_digest="role=dev sha256 OLD")
        r, out = self._finish_out(tmp_path, reg, state)
        assert r.returncode == 1 and out["verdict"] == "returned"
        detail = next(d["detail"] for d in out["defects"]
                      if d["code"] == "ZONE_POLICY_MISMATCH")
        assert "role=dev sha256 OLD" in detail

    def test_legacy_reservation_covered_accepted(self, tmp_path):
        """TC-J65-RZD-004: резервация до J65.2 (без отпечатка, старый реестр)."""
        repo, reg, state = self._run_cycle_to_running(tmp_path)
        self._commit_in_zone(repo)
        self._tamper(reg, role_zone_digest=None,
                     policy_version="agents/roles.json sha256 OLD-registry")
        r, out = self._finish_out(tmp_path, reg, state)
        assert out["verdict"] == "accepted", out

    def test_legacy_reservation_outside_policy_mismatch(self, tmp_path):
        """TC-J65-RZD-004: легаси-зона вне текущей политики — дефект."""
        repo, reg, state = self._run_cycle_to_running(tmp_path)
        self._commit_in_zone(repo)
        self._tamper(reg, role_zone_digest=None, zones=["src/**", "docs/**"])
        r, out = self._finish_out(tmp_path, reg, state)
        assert any(d["code"] == "ZONE_POLICY_MISMATCH" for d in out["defects"]), out
        assert out["verdict"] == "returned"
