# ТЗ 06. Минимальный локальный Orchestrator

**Flow:** 4. **Зависимость:** 03–05. **Результат:** один управляемый цикл запуска агента с recovery.

## Граница MVP

Пользователь/ПМ явно выбирает проект, Flow, change/task и действие. `Orchestrator` строит snapshot, получает `Decision`, атомарно резервирует session, создаёт/проверяет worktree, собирает минимальный контекст по `templates/task_delegation.md`, запускает одну роль через сменный adapter, затем повторно читает факты, проверяет diff и gates и выдаёт `accepted/returned/blocked`. Он не планирует новую крупную фазу без подтверждения заказчика и не делает merge/deploy/push в первом MVP.

Первый adapter может быть `manual`: подготовить session/worktree/goal и ожидать внешнего исполнения `delegate_task`. Автоматический Hermes adapter делать только при проверенной возможности запуска с требуемым cwd, наблюдения процесса, timeout и остановки; отсутствие этой возможности не должно блокировать read-only контроль и manual MVP. Не выдавать подготовленный goal за факт запуска.

## Execution contract

- Вход: разрешённое действие с snapshot digest и explicit scope. Непосредственно перед стартом переснять Git/реестр и повторить preflight; несовпадение → `STALE_SNAPSHOT`.
- Runner принимает role, cwd, goal artifact path, timeout, environment allowlist, session ID; возвращает process/delegation ID, exit status и пути логов. Никаких секретов в goal/log.
- Timeout или crash не приводят к следующему шагу. Сессия остаётся доступной для разбора, Worktree не удаляется.
- После завершения агентский отчёт рассматривается как указатель на файлы. Сверить фактический Git diff, commit, разрешённую зону, выходные артефакты и gates. При возврате формировать структурированный список дефектов.
- Идемпотентность: повтор `run` с тем же action/correlation ID не создаёт вторую сессию и не повторяет LLM-вызов автоматически. Recovery через `status`/`reconcile` и явное действие ПМ.

## CLI

`flowctl inspect`, `check`, `next`, `prepare`, `run`, `status`, `reconcile`. `prepare --dry-run` показывает роль, входы, worktree, gates и human gate без side effects. `run` разрешён только после явного решения и реальной reservation. Выход `--json` стабилен для будущего WebUI/backend; версия schema обязательна. Для MVP достаточно CLI, HTTP и WebUI вне объёма.

## Приёмка

Провести один цикл `dev task → review request` на временном репозитории: подготовка, работа в Worktree, изменение в своей зоне, post-gates, корректный вердикт. Проверить отдельными прогонами запрет из-за human gate, падение агента, timeout, stale snapshot, gate failure и restart процесса без повторной делегации. Никакого автоматического продвижения к QA/release.
