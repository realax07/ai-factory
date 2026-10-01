# ТЗ 05. Provenance и единый запуск существующих Gates

**Flow:** 4. **Зависимость:** 02–04. **Результат:** `gate_runner.py`, структурированный отчёт и связывание review с конкретной версией работы.

## Gate Runner

Для каждого действия задавать список обязательных проверок и точку запуска (`preflight`, `post_agent`, `pre_accept`, `pre_merge`, `ci`). Адаптеры вызывают существующие CLI с явными repo/cwd и timeout: `openspec validate --all --strict`, `flow_check.py`, `pr_validate.py` там, где есть PR-контекст, `pm_bounds_check.py` в применимых режимах, тесты и специализированные проверки. Не запускать `pm_bounds_check.py --all-projects` как доказательство проверки выбранного repo без подтверждения его охвата.

GateReport: `gate_id`, `scope`, `command/adapter_version`, `input_head`, `input_digest`, `started_at`, `duration`, `exit_code`, `status PASS|FAIL|ERROR|SKIPPED`, `log_path`, краткая диагностика. `SKIPPED` разрешён только когда gate неприменим по явному правилу; timeout, missing executable и parse error дают `ERROR` и блокируют. Повторная проверка после изменения входного SHA обязательна.

## Provenance review

Для нового review записывать в машинно читаемом блоке/sidecar: `schema_version`, project, change, task IDs, author delegation, reviewer delegation, reviewed commit SHA либо diff digest, verdict, timestamp и путь review. Существующий человекочитаемый `.md` сохраняется. Принимать approve только для соответствующих task/change/diff и независимой роли. Изменение кода, tasks или другого утверждённого входа инвалидирует релевантный approve. Проверку времени оставить дополнительной, а не основной: один календарный день не доказывает порядок событий или идентичность diff.

Старые review-файлы не переписывать. Для них ввести явно ограниченный compatibility mode: показать `legacy evidence` и не давать нового автоматического merge без дополнительной проверки. Не объявлять старые исторические merge незаконными задним числом.

## Audit trail

Вести append-only JSONL событий `request`, `decision`, `reservation`, `agent_started`, `agent_finished`, `gate_report`, `accepted/returned`, `recovery` с correlation ID, scope, SHA/digest и путями evidence. Секреты и полный stdout агента в JSONL не копировать; логи хранить отдельно с ограничением размера. JSONL помогает разбору, но источник фактического состояния остаётся в Git/файлах/реестре. Лог нельзя использовать как единственное доказательство успешного шага.

## Приёмка

- Ложный `approve` для другого SHA/task отклоняется; после нового commit прежний approve устаревает.
- Падающий, отсутствующий и зависший gate блокируют переход с разными кодами.
- `pr_validate` не запускается без PR-контекста и не считается пройденным.
- Отчёт показывает, какие gates реально выполнены и на каком input digest.
