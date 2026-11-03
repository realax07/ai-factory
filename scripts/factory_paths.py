#!/usr/bin/env python3
"""factory_paths.py — единственный источник машинных путей фабрики (J64.5).

Фабрика не прошивает пути машины в коде: каждый путь вычисляется здесь и
переопределяется переменной окружения. Перенос фабрики на другую машину
или под другого пользователя = задать env, а не править скрипты.

Пути делятся на четыре вида — у каждого свой смысл и своя переменная:

| Функция            | Что это                                   | env                | Дефолт            |
|--------------------|-------------------------------------------|--------------------|-------------------|
| `state_dir()`      | память движка ворот: реестр сессий,       | `AF_STATE_DIR`     | `~/.hermes/state` |
|                    | flowctl_state, режим flow_mode, инциденты |                    |                   |
| `hermes_home()`    | данные исполнителя Hermes: state.db       | `HERMES_HOME`      | `~/.hermes`       |
|                    | (async_delegations), sessions, кеш, логи  |                    |                   |
| `factory_home()`   | где лежит репозиторий фабрики             | `AI_FACTORY_HOME`  | `~/ai-factory`    |
| `projects_root()`  | где лежат проекты (`<root>/<project>`)    | `AF_PROJECTS_ROOT` | `~`               |
| `pi_agent_dir()`   | конфиг исполнителя Pi (models, extensions)| `PI_AGENT_DIR`     | `~/.pi/agent`     |

`state_dir()` по умолчанию — `~/.hermes/state` (историческое место: фабрика
выросла на Hermes), но от `HERMES_HOME` он НЕ зависит: память движка общая
для всех процессов (шелл ПМ, крон, процесс Hermes, раннер). Если бы она
следовала `HERMES_HOME`, процесс с другим `HERMES_HOME` (например, профиль
Hermes) не нашел бы flow_mode.json — режим молча стал бы shadow — и реестр
резерваций раздвоился бы (ревью J64.5). Переопределение — только явно,
через `AF_STATE_DIR`.

Функции вычисляются в момент вызова (env и HOME читаются каждый раз):
скрипты с константами уровня модуля фиксируют значение при импорте, как и
раньше; тесты подменяют env (tests/conftest.py) или сами константы.

Модуль копируется в проекты вместе со скриптами ворот (factory_init:
COPY_FILES/FLOW_CONTROL_FILES) — только stdlib, без побочных эффектов.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    return Path(raw).expanduser() if raw else default


def hermes_home() -> Path:
    """Данные исполнителя Hermes (state.db, sessions, кеш делегаций, логи)."""
    return _env_path("HERMES_HOME", Path.home() / ".hermes")


def state_dir() -> Path:
    """Память движка ворот: реестр сессий, flowctl_state, flow_mode, инциденты."""
    return _env_path("AF_STATE_DIR", Path.home() / ".hermes" / "state")


def registry_path() -> Path:
    """Реестр сессий (резервации зон) — общий для делегаций и раннера."""
    return state_dir() / "active_sessions.json"


def flowctl_state_path() -> Path:
    """State циклов flowctl (prepare/run/finish)."""
    return state_dir() / "flowctl_state.json"


def factory_home() -> Path:
    """Репозиторий фабрики (агенты, скрипты, скиллы)."""
    return _env_path("AI_FACTORY_HOME", Path.home() / "ai-factory")


def projects_root() -> Path:
    """Каталог, в котором лежат проекты (`<root>/<project>`)."""
    return _env_path("AF_PROJECTS_ROOT", Path.home())


def pi_agent_dir() -> Path:
    """Конфиг исполнителя Pi (models.json, extensions/)."""
    return _env_path("PI_AGENT_DIR", Path.home() / ".pi" / "agent")


def describe() -> dict[str, str]:
    """Текущие пути (для диагностики: `python3 scripts/factory_paths.py`)."""
    return {
        "state_dir": str(state_dir()),
        "registry": str(registry_path()),
        "flowctl_state": str(flowctl_state_path()),
        "hermes_home": str(hermes_home()),
        "factory_home": str(factory_home()),
        "projects_root": str(projects_root()),
        "pi_agent_dir": str(pi_agent_dir()),
    }


if __name__ == "__main__":
    for key, value in describe().items():
        print(f"{key:14} {value}")
