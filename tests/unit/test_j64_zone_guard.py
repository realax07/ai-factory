# -*- coding: utf-8 -*-
"""J64.10: zone-guard в репо, раннер берет его оттуда; политика по роли;
лог отказов — вне worktree.

Решения Заказчика 2026-11-11: «Прямо из репо» (раннер подключает
`skills/pm-factory/pi/zone-guard.ts` репо движка, не копию в ~/.pi; нет
файла — STOP, sha256 — в отчет стадии) и «Всем, кроме devops» (docker-
мутации запрещены всем ролям, кроме devops; git push — всем).

Трассировка:
  TC-J64-ZG-001  раннер: `-e` — guard репо движка; env PI_ZONE_ROLE (роль
                 политики) и PI_ZONE_GUARD_LOG (вне worktree); sha256 guard'а
                 — в отчете стадии и в flow_gates state раннера
  TC-J64-ZG-002  guard отсутствует — STOP ZONE_GUARD_MISSING до ворот входа:
                 pi не вызван, резервации нет
  TC-J64-ZG-003  guard под node (заглушка ExtensionAPI): запись в зоне /
                 вне зоны / glob-сегмент / без PI_ZONE_WRITE / выход из
                 worktree; git push; docker-мутации — отказ всем, кроме
                 devops, чтение в той же команде мутацию не снимает; лог —
                 в PI_ZONE_GUARD_LOG, не в worktree. SKIP без node с
                 поддержкой TypeScript (strip types)
  TC-J64-ZG-004  эталон один: bootstrap ставит тот же файл, что берет раннер;
                 копии в паке regress-runner нет
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import package_runner as pr  # noqa: E402
import test_package_runner as tpr  # noqa: E402
from test_package_runner import flow_gates_sandbox  # noqa: E402,F401  (autouse: ворота-заглушки)

GUARD = FACTORY / "skills" / "pm-factory" / "pi" / "zone-guard.ts"


def _run(tmp_path, monkeypatch, stage=tpr.DEV_STAGE):
    repo, plan = tpr.gated_plan(tmp_path, stage)
    calls: list = []
    tpr.patch_executors(monkeypatch, repo, calls)
    return repo, plan, calls


def test_runner_uses_repo_guard_role_and_log(tmp_path, monkeypatch):
    """TC-J64-ZG-001."""
    repo, plan, calls = _run(tmp_path, monkeypatch)
    assert pr.cmd_run(plan, dry_run=False) == 0
    (call,) = calls
    args, env = call["args"], call["env"]
    assert Path(args[args.index("-e") + 1]) == GUARD == pr.ZONE_GUARD
    assert env["PI_ZONE_ROLE"] == "dev"
    log = Path(env["PI_ZONE_GUARD_LOG"])
    assert log.name == "express-x.log" and log.parent.name == "zone-guard"
    assert repo not in log.parents and Path(call["cwd"]) not in log.parents
    sha = pr.file_sha256(GUARD)
    state = pr.state_load(pr.state_path_for(plan))
    assert state["flow_gates"]["impl"]["zone_guard_sha256"] == sha
    (report,) = plan.with_name(plan.name + pr.REPORTS_SUFFIX).glob("impl-*.md")
    assert f"sha256 {sha}" in report.read_text(encoding="utf-8")


def test_runner_stops_without_guard(tmp_path, monkeypatch, capsys):
    """TC-J64-ZG-002."""
    repo, plan, calls = _run(tmp_path, monkeypatch)
    monkeypatch.setattr(pr, "ZONE_GUARD", tmp_path / "нет" / "zone-guard.ts")
    entered: list = []
    monkeypatch.setattr(pr, "gate_new", lambda *a: entered.append(a))
    assert pr.cmd_run(plan, dry_run=False) == 2
    assert "ZONE_GUARD_MISSING" in capsys.readouterr().err
    assert calls == [] and entered == []


# ------------------------------------------------------------ guard под node

HARNESS = """
import { pathToFileURL } from "node:url";
const [guard, cwd, eventJson] = process.argv.slice(2);
const handlers = {};
const mod = await import(pathToFileURL(guard).href);
mod.default({ on: (name, fn) => { handlers[name] = fn; } });
const res = await handlers.tool_call(JSON.parse(eventJson), { cwd, hasUI: false });
process.stdout.write(JSON.stringify(res ?? null));
"""


def _node_cmd() -> list[str] | None:
    node = shutil.which("node")
    if not node:
        return None
    for flags in ([], ["--experimental-strip-types"]):
        probe = subprocess.run([node, *flags, "--input-type=module", "-e",
                                "await import('data:text/javascript,0')"],
                               capture_output=True, text=True)
        if probe.returncode != 0:
            continue
        return [node, *flags, "--no-warnings"]
    return None


NODE = _node_cmd()


@pytest.fixture
def guard_call(tmp_path):
    if NODE is None:
        pytest.skip("node не найден")
    harness = tmp_path / "harness.mjs"
    harness.write_text(HARNESS, encoding="utf-8")
    wt = tmp_path / "wt"
    wt.mkdir()
    log = tmp_path / "state" / "zone-guard" / "pkg.log"

    def call(event: dict, zones: str | None = "src:tests/unit:code-reviews/x/review-*.md",
             role: str = "dev"):
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "home"),
               "PI_ZONE_ROLE": role, "PI_ZONE_GUARD_LOG": str(log)}
        if zones is not None:
            env["PI_ZONE_WRITE"] = zones
        r = subprocess.run([*NODE, str(harness), str(GUARD), str(wt),
                            json.dumps(event)], capture_output=True, text=True,
                           env=env, timeout=60)
        if r.returncode != 0 and "Unknown file extension" in r.stderr:
            pytest.skip("node без поддержки TypeScript (strip types)")
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)
    call.wt, call.log = wt, log
    return call


def _w(path):
    return {"toolName": "write", "input": {"path": path}}


def _b(cmd):
    return {"toolName": "bash", "input": {"command": cmd}}


def test_guard_policy_under_node(guard_call):
    """TC-J64-ZG-003."""
    allowed = [_w("src/a.py"), _w("tests/unit/test_a.py"),
               _w("code-reviews/x/review-1.1-001.md"), _b("pytest -q"),
               _b("docker ps"), _b("docker compose logs api")]
    for ev in allowed:
        assert guard_call(ev) is None, ev
    blocked = [_w("docs/a.md"), _w("../outside.py"), _w("srcx/a.py"),
               _w("code-reviews/y/review-1.1-001.md"), _w("code-reviews/x/notes.md"),
               {"toolName": "edit", "input": {}},
               _b("git push origin HEAD"), _b("cd x && git -C . push"),
               _b("docker rm -f api"), _b("docker compose up -d"),
               _b("docker ps && docker rm api")]
    for ev in blocked:
        res = guard_call(ev)
        assert res and res["block"] is True, ev
    # без PI_ZONE_WRITE запись запрещена целиком (прежний дефолт снят)
    assert guard_call(_w("tests/a.py"), zones=None)["block"] is True
    # docker-мутации — только devops; git push — никому
    assert guard_call(_b("docker compose up -d"), role="devops") is None
    assert guard_call(_b("git push"), role="devops")["block"] is True
    assert guard_call(_b("docker rm api"), role="regress_runner")["block"] is True
    # лог — в PI_ZONE_GUARD_LOG, в worktree ничего
    assert "BLOCK" in guard_call.log.read_text(encoding="utf-8")
    assert "role=dev" in guard_call.log.read_text(encoding="utf-8")
    assert not any(guard_call.wt.rglob("*"))


def test_single_guard_source():
    """TC-J64-ZG-004."""
    import factory_bootstrap as fb
    assert fb.ZONE_GUARD_SRC == GUARD == pr.ZONE_GUARD and GUARD.is_file()
    assert not list((FACTORY / "skills").rglob("extensions/zone-guard.ts"))
