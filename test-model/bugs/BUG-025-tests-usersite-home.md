# BUG-025: подмена HOME в тестах (J64.2) ломает user-site subprocess-pytest

## Суть

J64.2 (PR #217) подменяет HOME и HERMES_HOME на временный каталог
(`tests/conftest.py`: `pytest_configure` + autouse `isolated_home`). Python
вычисляет user-site из HOME, поэтому дочерний интерпретатор с фейковым HOME
теряет `~/.local/lib/python3.X/site-packages`. Regress-тьеры запускают
`python -m pytest` subprocess'ом — на машине, где pytest и его зависимости
стоят через `pip --user`, внутренний pytest падает на импорте.

## Среда и воспроизведение

- Боевой VPS: Ubuntu 24, Python 3.14 (python Hermes tools), пакеты фабрики —
  `pip --user`, запуск `python3 -m pytest tests/` из корня клона без venv.
  Отчет агента VPS, 2026-11-03.
- Симптом: 18 FAILED — `tests/test_j51_worktree_regress.py` (7),
  `tests/test_j52_w1.py` (4), `tests/test_j54_tiers.py` (7); внутри —
  `ModuleNotFoundError: No module named 'pluggy'`. До J64.2 — 1140 passed.
- В CI и на чистой машине не проявляется: пакеты стоят системно или в venv,
  user-site не задействован.
- Воспроизведено на Mac (2026-11-03): pytest поставлен только в user-site
  под отдельным HOME (`HOME=<dir> python3.14 -m pip install --user pytest`),
  прогон трех файлов — 18 failed, 37 passed; в хвосте лога
  `No module named pytest`.

## Фикс

`tests/conftest.py`, `pytest_configure`: до подмены HOME реальный user base
(`site.getuserbase()`) фиксируется в `PYTHONUSERBASE` (если переменная уже
задана непустой — не трогается); `pytest_unconfigure` восстанавливает прежнее
значение. HOME и HERMES_HOME остаются временными — изоляция state не
меняется.

Выбран вариант 1 из отчета (прокинуть user-site), через `PYTHONUSERBASE`, а
не `PYTHONPATH`: сохраняется штатная обработка `.pth` user-site и порядок
путей. Вариант 2 (только venv) не выбран: требование среды, которое ворота
не проверяют, повторит дефект на следующей машине.

## Тесты

`tests/test_bug025_usersite_home.py`, TC-BUG-025-001..004. TC-001 падает на
любой машине без фикса (сравнение user-site процесса и subprocess), то есть
дефект ловится и в CI.

## Статус

- 2026-11-03: исправлено (ветка fix/bug-025-tests-usersite). OPEN — до merge
  и подтверждения прогоном на VPS.
