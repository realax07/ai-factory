"""Исполнитель hermes — делегации Hermes (delegate_task) по решению ПМ.

Единственное место ядра, которое знает устройство данных Hermes (J65.6,
критерий «ядро готово»): реестр делегаций `<HERMES_HOME>/state.db`, кеш
транскриптов, лог ошибок чата. Остальные скрипты ворот спрашивают этот
модуль; тест tests/unit/test_j65_core_ready.py держит границу.

Для пакетного раннера — ручная стоп-точка (`run: hermes:<роль>`): раннер не
запускает процесс, печатает «ЖДУ ПМ» и ждет (как до J65.5). Активные запуски
— делегации платформенного реестра `<HERMES_HOME>/state.db →
async_delegations` (пишется платформой при каждом delegate_task): по ним
delegate_watchdog сверяет обход с записями flowctl.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from . import ActiveRun, Executor

ACTIVE_STATES = ("running", "dispatched", "pending")


def _home() -> Path:
    import factory_paths as fp
    return fp.hermes_home()


def _db() -> Path:
    return _home() / "state.db"


def _live_dir() -> Path:
    return _home() / "cache" / "delegation" / "live"


class HermesExecutor(Executor):
    name = "hermes"
    manual = True

    def delegations(self, db: Path | None = None) -> list[dict] | None:
        """Все делегации реестра Hermes; нет/битый state.db — None."""
        db = db or _db()
        if not db.exists():
            return None
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT delegation_id, parent_session_id, state, delivery_state,"
                " dispatched_at, completed_at FROM async_delegations").fetchall()
            conn.close()
        except sqlite3.Error as e:
            print(f"WARN: state.db недоступен ({e})", file=sys.stderr)
            return None
        return [{k: r[k] for k in ("delegation_id", "state", "delivery_state",
                                   "dispatched_at", "completed_at",
                                   "parent_session_id")} for r in rows]

    def registry_db(self) -> Path:
        """Путь реестра делегаций (для диагностики и тестов)."""
        return _db()

    def delegation(self, ref: str, db: Path | None = None) -> tuple[bool, str | None]:
        """(реестр доступен, состояние делегации ref или None — нет такой).
        Реестр недоступен (нет файла, битая база) — (False, None): вызывающий
        решает сам, fail-closed это или пометка «не проверено» (pr_validate)."""
        db = db or _db()
        if not db.is_file():
            return False, None
        norm = (ref or "").replace("-", "_")
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                row = conn.execute("SELECT state FROM async_delegations"
                                   " WHERE delegation_id=?", (norm,)).fetchone()
            finally:
                conn.close()
        except sqlite3.Error as e:
            print(f"WARN: state.db недоступен ({e})", file=sys.stderr)
            return False, None
        return True, (row[0] if row else None)

    def errors_log(self) -> Path:
        """Лог ошибок платформы Hermes (chat_degrade_watchdog)."""
        return _home() / "logs" / "errors.log"

    def finished_runs(self) -> list[tuple[str, Path]]:
        live = _live_dir()
        if not live.is_dir():
            return []
        return [(d.name, d / "task-0.log") for d in sorted(live.iterdir())
                if d.is_dir() and (d / "task-0.log").is_file()]

    def list_active(self) -> list[ActiveRun]:
        return [ActiveRun(self.name, None, "", "delegate_task", d["delegation_id"])
                for d in (self.delegations() or [])
                if d.get("state") in ACTIVE_STATES]

    def transcript(self, ref: str) -> str | None:
        log = _live_dir() / ref / "task-0.log"
        try:
            return log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None


EXECUTOR = HermesExecutor()
