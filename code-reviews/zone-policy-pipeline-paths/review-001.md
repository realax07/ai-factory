Вердикт: Одобрить
Ревьюер: code_reviewer (сабагент Claude Code)
Коммит: 55dd7e525a8640a68def61a3d9c530d8694573f6

Предмет: `git diff origin/main...HEAD` ветки `chore/zone-policy-dev-infra` (J64.18: владельцы путей пайплайна в политике зон + сводка отказа в сообщении энфорсера).

## Замечания

| Severity | Файл:строка | Проблема | Сценарий отказа | Рекомендация |
|---|---|---|---|---|
| minor | scripts/role_zone_policy.py:113-115 | `pytest.ini` в зоне qa_automation дает автору автотестов рычаг ослабить ворота: `addopts = -m "not real_flow_gates"`, `--deselect`, `-p no:<плагин>`, переопределение `markers`, `testpaths` | Автоматизатор правит `pytest.ini` так, что тесты самих ворот (J41, package_runner real_flow_gates) молча не собираются; сьют зеленый. Новый риск невелик — роль уже владеет `tests/**` (может удалить/заскипать тест), но правка через конфиг менее заметна в диффе | В оси G8 у qa_case_reviewer явно проверять дифф `pytest.ini` (addopts/deselect/-p/testpaths); опционально — CI-проверка, что `addopts` не содержит фильтров `-m`/`-k`/`--deselect`. Кандидат в бэклог |
| minor | plugins/flow-enforcer/enforcer.py:1183-1189 | `decision_summary` предполагает dict у `record`/`decision` и list у `details`/`zone_violations`; при иной форме — `AttributeError` (или посимвольный вывод строки) | Сейчас prepare всегда эмитит эти формы (проверено по `flowctl.py:610-770`, `Decision.to_dict`), поэтому сценарий гипотетический; при исключении срабатывает fail-closed `except Exception` — делегация всё равно блокируется, но теряется информативное сообщение | Обернуть тело в `try/except (AttributeError, TypeError)` → `""` или проверять `isinstance`. Не блокирует |
| minor | plugins/flow-enforcer/enforcer.py:1176-1183 | Для отказа `J3_PROTECTED_PATHS` сводка выводит только `причина:`, без `protected_paths`; для enforcing-ветки (`reason = decision.status`) строки «причина: DENY» и «решение: DENY» дублируются | Косметика: ПМ видит код, но для J3 список путей — только в хвосте | Добавить `protected_paths` в сводку; дубль можно не трогать |
| minor | scripts/role_zone_policy.py:33-36, 42-44 | `POLICY_TABLE_DIGEST` по-прежнему указывает на таблицу `agents/README.md@1b6040b`, хотя строки таблицы изменены; расхождение фиксируется лишь текстом поправки | Аудитор, сверяющий digest с текущей таблицей README, получит несовпадение | Следует прецеденту Н13 (допустимо); при следующей ревизии политики перепиновать digest на актуальный коммит таблицы |
| minor | scripts/role_zone_policy.py:115 | Паттерн `pytest.ini` покрывает только корень; в проектах конфиг может лежать в `backend/pytest.ini` / `pyproject.toml` | В проекте автоматизатор не сможет зарезервировать вложенный конфиг (ZONE_OUTSIDE_POLICY) | Расширить при первом прецеденте проекта, не сейчас |

Блокеров и major нет.

## Проверено

- **Независимость ролей:** по всей `ROLE_ZONE_POLICY` (все роли, не только 5 из теста) каждый новый путь принадлежит ровно одной роли: `plugins/flow-enforcer/enforcer.py` → только dev, `.github/workflows/flow.yml` → только devops, `pytest.ini` → только qa_automation. Ревьюеры (code_reviewer, qa_case_reviewer) зон не получили — независимость автор/ревьюер не нарушена. Риск `pytest.ini` — см. minor выше.
- **POLICY_VERSION:** поправка дописана в `POLICY_AMENDMENT` (прецедент Н13). Эффект на in-flight: `flowctl.py:1297-1308` — резервация со старой `policy_version` на finish получит `ZONE_POLICY_MISMATCH`; это ожидаемо и задокументировано в плане (PLAN-zone-policy-pipeline-paths.md:19-20). Реестр `~/.hermes/state/active_sessions.json` на машине отсутствует — активных резерваций под старой версией нет. Литералов старой version-строки в тестах/скриптах нет: тесты используют `rzp.policy_version()`, `pm_bounds_check` версию не пинит (его `PROTECTED_PATHS`/`DEPLOY_PATHS` не затронуты), sidecar'ы хранят версию на момент записи — аудитная семантика.
- **README ↔ код:** строки таблицы зон (Разработчик + `plugins/**`, Автоматизатор + `pytest.ini`), секция dev «Смежная зона» и карточка devops (`.github/workflows/**`) согласованы с `ROLE_ZONE_POLICY`.
- **`decision_summary`:** покрывает все формы отказа prepare — top-level `reason` (J3, ZONE_OUTSIDE_POLICY, MISSING_INPUT, DUPLICATE_PAYLOAD, enforcing blocks_on), top-level `decision`, `record.decision` (enforcing/не-ALLOW ветки), `zone_violations`. Не-JSON и мусор после JSON → `""` без исключения (как `parse_decision_output`). Сырой хвост `out.strip()[-2000:]` в сообщении сохранен. Вызов внутри fail-closed `try`.
- Тесты: `tests/test_p03_zone_policy.py` + `tests/test_j43_flow_enforcer.py` — 55 passed (перепрогон); полный сьют по данным ПМ — 1110 passed, 2 skipped.

## Не проверено

- Полный сьют не перепрогонялся (только целевые файлы).
- Живой прогон энфорсера в Hermes (pre_tool_call) с реальным DENY не выполнялся.
- Проекты-клиенты (ekotov-wiki) на расположение `pytest.ini`/workflows не проверялись.
- `.md`-файлы плана и бэклога по существу не ревьюились (не код).
