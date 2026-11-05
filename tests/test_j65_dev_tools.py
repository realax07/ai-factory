# -*- coding: utf-8 -*-
"""J65.12: инструменты отладки — ci_local.py и factory_paths --doctor.

ci_local воспроизводит job test-flow-control CI: shallow-клон коммита HEAD,
пустой HOME, без GITHUB_*/HERMES_HOME. factory_paths --doctor/--compare
заменяет ручную сверку путей из шелла, крона и Hermes перед мержем.

Трассировка:
  TC-J65-DT-001  doctor: снимок несет label, env и пути текущего контекста
  TC-J65-DT-002  compare: одинаковые снимки → OK (rc 0), разошедшийся путь
                 → перечень с метками контекстов (rc 1)
  TC-J65-DT-003  --doctor --out <каталог> пишет factory-paths-<label>.json
  TC-J65-DT-004  ci_env: только PATH/LANG/…/PYTHONUSERBASE + пустой HOME;
                 GITHUB_EVENT_PATH, HERMES_HOME, AF_STATE_DIR не протекают
  TC-J65-DT-005  ci_local на fixture-репо: прогон видит shallow-клон, пустой
                 HOME и только закоммиченное (грязная правка не попадает)
  TC-J65-DT-006  ci_local: красный тест в коммите → rc 1
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import ci_local  # noqa: E402
import factory_paths as fp  # noqa: E402


def test_doctor_snapshot(monkeypatch, tmp_path):
    """TC-J65-DT-001"""
    monkeypatch.setenv("AF_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    snap = fp.doctor("shell")
    assert snap["label"] == "shell"
    assert snap["paths"]["state_dir"] == str(tmp_path / "state")
    assert snap["env"]["AF_STATE_DIR"] == str(tmp_path / "state")
    assert snap["checks"]["state_dir_exists"] is True
    assert snap["checks"]["registry_exists"] is False


def test_compare(monkeypatch, tmp_path, capsys):
    """TC-J65-DT-002"""
    monkeypatch.setenv("AF_STATE_DIR", str(tmp_path / "a"))
    shell = fp.doctor("shell")
    cron_same = fp.doctor("cron")
    assert fp.compare([shell, cron_same]) == []
    monkeypatch.setenv("AF_STATE_DIR", str(tmp_path / "b"))
    hermes = fp.doctor("hermes")
    diffs = fp.compare([shell, cron_same, hermes])
    assert len(diffs) == 3  # state_dir, registry, flowctl_state
    assert any(d.startswith("state_dir:") and "hermes=" in d
               and str(tmp_path / "b") in d for d in diffs)

    files = []
    for s in (shell, hermes):
        f = tmp_path / f"{s['label']}.json"
        f.write_text(json.dumps(s), encoding="utf-8")
        files.append(str(f))
    assert fp.main(["--compare", files[0], files[0]]) == 0
    assert fp.main(["--compare", *files]) == 1
    assert "РАСХОЖДЕНИЕ" in capsys.readouterr().out


def test_doctor_out_dir(tmp_path):
    """TC-J65-DT-003"""
    out = tmp_path / "doctor"
    assert fp.main(["--doctor", "cron", "--out", f"{out}/"]) == 0
    snap = json.loads((out / "factory-paths-cron.json").read_text("utf-8"))
    assert snap["label"] == "cron"


def test_ci_env_strips_machine_env(monkeypatch, tmp_path):
    """TC-J65-DT-004"""
    for k in ("GITHUB_EVENT_PATH", "HERMES_HOME", "AF_STATE_DIR"):
        monkeypatch.setenv(k, "/leak")
    monkeypatch.setenv("PYTHONUSERBASE", "/real/userbase")
    env = ci_local.ci_env(tmp_path)
    assert env["HOME"] == str(tmp_path)
    assert env["PYTHONUSERBASE"] == "/real/userbase"
    assert not {"GITHUB_EVENT_PATH", "HERMES_HOME", "AF_STATE_DIR"} & set(env)
    assert set(env) <= set(ci_local._KEEP_ENV) | {"HOME"}


PROBE = '''
import os, subprocess
from pathlib import Path

def test_probe():
    """TC-PROBE-001"""
    assert not any(Path.home().iterdir()), "HOME не пустой"
    assert "GITHUB_EVENT_PATH" not in os.environ
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True).stdout.strip()
    assert shallow == "true"
'''


def _fixture_repo(root: Path, probe: str = PROBE) -> Path:
    repo = root / "proj-ci"
    (repo / "tests").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "flow_check.py").write_text(
        "print('flow_check: OK')\n", encoding="utf-8")
    (repo / "tests" / "test_probe.py").write_text(probe, encoding="utf-8")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "one"], check=True)
    (repo / "NOTE").write_text("2\n", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "two"], check=True)
    return repo


def test_ci_local_runs_committed_shallow(tmp_path):
    """TC-J65-DT-005"""
    repo = _fixture_repo(tmp_path)
    # незакоммиченный красный тест в прогон не попадает
    (repo / "tests" / "test_dirty.py").write_text(
        "def test_dirty():\n    assert False\n", encoding="utf-8")
    assert ci_local.main(["--repo", str(repo)]) == 0


def test_ci_local_red_commit(tmp_path):
    """TC-J65-DT-006"""
    repo = _fixture_repo(tmp_path, probe="def test_red():\n    assert False\n")
    assert ci_local.main(["--repo", str(repo)]) == 1
