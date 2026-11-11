# Эталонный межагентный прогон (J65.10)

Фиктивный проект и выходы агентов для сквозного прогона пакетного раннера
по Флоу 1: change (sa) → architecture review (architect) → dev по задачам
tasks.md с парным code review → gate → merge в main → ворота мержа
(flow_check, pr_validate). Тест — `tests/unit/test_j65_reference_run.py`.

- `project/` — проект до старта пакета: утвержденные требования и план
  релиза с манифестом `pipeline:`. Решение Заказчика (approval_ref) тест
  пишет сам: decision-record ссылается на SHA коммита.
- `outputs/<stage-id>/` — что «пишет агент» стадии: заглушка копирует
  дерево в worktree стадии; суффикс `.tmpl` снимается (тесты фиктивного
  проекта не попадают в pytest и flow_check фабрики).
- `bin/pi` — заглушка исполнителя: та же командная строка, что у pi
  (`-p <бриф>`), id стадии — из первой строки брифа. Раннер, flowctl,
  session_check, gate_runner и ворота — настоящие.

Отладка заглушки: `REFERENCE_STUB_EXTRA=<путь>` — дописать файл вне выходов
стадии; `REFERENCE_STUB_VERDICT=<stage-id>:return` — вердикт ревью стадии
заменить на return.

Реальные исполнители (GLM Flash, Qwen Coder, Claude Code) — после J65.5
(адаптер исполнителя): тот же проект, вместо `bin/pi` — исполнитель.
