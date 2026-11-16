# Ревью core-ready (J65.6 «ядро готово») — review-002

- Пакет: PLAN-core-ready.md (Флоу 4), ветка `chore/core-ready`
- Коммит правок: 2f32fcb (`git diff faf659c..2f32fcb`), полный дифф `git diff origin/main...HEAD`
- Ревьюер: code_reviewer (независимый сабагент Claude Code, автор диффа — другая сессия). Только статика и пробы
  вызовом функций. pytest в окружении нет. Тесты запущены вызовом функций с заглушкой `pytest`:
  `test_core_boundary_no_hermes_outside_adapter`, `test_boundary_detector_catches_violation` и все 5 тестов
  `test_j65_gates_changelog.py` — PASS.

## Вердикт: return

Blocker и major из review-001 закрыты. Возврат из-за двух регрессий, которые внесли сами правки раунда.
(1) m6: `scope_matches` теперь засчитывает стадию ревью чужого change. Это ослабляет ворота независимости, ради
которых сделан пакет. (2) m1: детектор границы перестал видеть канонический путь `~/.hermes/state.db`. Он
единственный страж критерия «граница». Обе правки — несколько строк.

## Закрытие находок review-001

| Находка | Статус | Чем подтверждено |
|---|---|---|
| B1 | закрыта | `pr_validate.py:514-523`: `<агент>:<id>` в CI — SKIPPED, вне CI — отказ. Проба вне CI без реестров по sidecar: `x:a/x:b`, `deleg_b`, `DELEG_B`, `delegx:b`, `deleg:abc` — везде DENY. В CI — PASS и 1 SKIPPED. Формы `X:b`, ` x:b`, `x:b\n`, `b` — DENY и в CI. Пути засчитать ревью вне CI без реестров не нашел. Решение «Provenance-файл ревью (Рекомендую)» с вопросом внесено в PLAN-core-ready.md:9-11. |
| M1 | закрыта | PLAN-core-ready.md:12-13: ответ «Исключение: утилита Hermes (Рекомендую)», 2026-11-17. Формулировка в CHANGELOG:26-28, в тесте :53-56 и в backlog соответствует коду. `session_watchdog.py:78-80` и `:145-158` только читают `async_delegations` и сигналят, пишут лишь в `gateway_routing` и `sessions`. |
| m1 | частично, регрессия | Алиас `hermes_home`, `errors.log`, `cache/delegation/live` теперь ловятся. Новая дыра — см. m8. `task-0.log` и путь `Path.home() / ".hermes" / …` по-прежнему не видны. |
| m2 | закрыта | Итоговая строка `PR-VALIDATE OK …; независимость ревью: SKIPPED (N, …)` (`:1415-1417`). |
| m3 | закрыта | Однословные коды, только строки таблиц, `COPY_FILES`. `BYPASS` внесен вручную, ограничение f-строк записано в докстринге теста. |
| m4 | закрыта | `session_archive.py:65-72`: WARN и `[]`. |
| m5 | закрыта | `PLAIN_REVIEW_RE`. Тест TC-J65-CORE-008 проверяет смесь форм. |
| m6 | частично, регрессия | Регистр и slug сравниваются в раннере и `dev_delegations`. Ложное совпадение — m7. Sidecar сравнивает scope по-старому — m9. |
| m7 | закрыта | Условие `--pr-id` описано в ci-gates, guarantees, CHANGELOG и скилле. |

`SKIPPED_REVIEW_CHECKS` (модульный список): `main()` вызывается раз на процесс. gate_runner запускает
pr_validate подпроцессом (`gate_runner.py:441-444`). Тесты `main()` в процессе не зовут, а тест sidecar очищает
список до и после. Накопление на итог не влияет, замечаний нет.

## Находки

### m7 (minor): `scope_matches` засчитывает чужой change, если change-id начинается с `bug-`

`scripts/pr_validate.py:332-334`. Правило slug применяется к любому scope с префиксом `bug-`, а не только к Флоу 2.
`CHANGE_ID_PATTERN` (`flow_ids.py:33`) допускает change-id Флоу 1 `bug-tracker` и `bug-tracker-v2`.
Проба: `runner_review_ok("deleg_rev1", "bug-tracker", state)`, где стадия code_reviewer с
`scope.change = "bug-tracker-v2"`, дает `True`. Ревью другого пакета засчитывается как независимое ревью этого PR.
Это fail-open в воротах независимости.
Ложного совпадения `BUG-042` и `BUG-0420` нет: проба дает `False`.

Что сделать: включать slug-правило, только если scope PR — ID бага (`^bug-(?:[a-z0-9]+-)*\d{3}$` в нижнем
регистре), или передавать флоу явно. Добавить в TC-J65-CORE-008 отрицательный случай `bug-tracker-v2` против
`bug-tracker`.

### m8 (minor): детектор границы не видит `"~/.hermes/state.db"`

`tests/unit/test_j65_core_ready.py:64, 92`. `val = node.value.replace("~/.hermes/state", "")` превращает
`"~/.hermes/state.db"` в `".db"`, и ни один запрет не срабатывает. Проба: файл `P = "~/.hermes/state.db"` дает
`hits == []`. Это самая типичная форма обращения к базе Hermes, ее и должен ловить страж критерия. До правки
она ловилась по `state.db`.

Не ловятся и формы из review-001: `Path.home() / ".hermes" / "logs" / "task-0.log"` (`hits == []`) и
`"~/.hermes/statefoo"`.

Что сделать: исключать только `~/.hermes/state`, за которым идет `/` или конец строки, например
`re.sub(r"~/\.hermes/state(?=/|$)", "", val)`. Добавить в BANNED_EXACT `".hermes"`, в BANNED_SUBSTR —
`"task-0.log"`. В пробу детектора добавить `"~/.hermes/state.db"`.

### m9 (minor): sidecar сравнивает scope без slug, хотя раннер и `bug_review_dir` slug принимают

`scripts/pr_validate.py:489`. `data["change"].lower() != scope_id.lower()` — точное сравнение. Если каталог
`code-reviews/BUG-042-fix/` (его принимает `bug_review_dir`), а sidecar записан
`gate_runner record-review --change BUG-042-fix` (scope Флоу 2 со slug по грамматике `flow_ids`), то получаем
отказ `change 'BUG-042-fix' ≠ BUG-042` (проба в CI). Ошибка в безопасную сторону: ложный отказ, а не пропуск.
Но правка m6 сделана не везде.

Что сделать: использовать `scope_matches` (после исправления m7).

### m10 (minor): смыслы `STALE` и `SKIP` в «Статусах ворот» не совпадают с кодом

`docs/CHANGELOG-gates.md:64`. `STALE` описан как «резервация или стадия устарела (истек срок, нет живого
процесса)». В ядре основной смысл другой:
- gate-отчет устарел, потому что HEAD изменился после отчета (`gate_runner.py:25, 571, 593`; дефект `STALE` в
  `flowctl.py:1358-1360`);
- вердикт выдан на другой коммит (`package_runner.py:643`).

Смысл «нет живого процесса» — это `stale` session_check (`:345`, `:842`), а константа `STALE` там (`:75`) нигде
не используется.

`docs/CHANGELOG-gates.md:60`. `SKIP` описан как «проверка к PR неприменима». Но `flow_scope_check.py:173` и
`flow_preflight.py:151` отдают SKIP и тогда, когда не определен merge-base, то есть когда проверку не удалось
выполнить.

Остальные статусы сверены с кодом, они верны: ALLOW, DENY, UNKNOWN (`flow_mode.BLOCKING_STATUSES`), PASS, FAIL,
SKIPPED (gate_runner, package_runner, pr_validate), ERROR, WARN, WARNING (уровень лога enforcer и gates_stats),
STOP (`package_runner._stop`), BYPASS.

Что сделать: `STALE` — «доказательство устарело: HEAD изменился после gate-отчета или вердикт выдан на другой
коммит». `SKIP` — «проверка неприменима или не определен merge-base; не прохождение».

### n1 (nit): хвост итоговой строки для ревьюера внешнего агента

`scripts/pr_validate.py:1416`. Текст «проверка — pre_merge ПМ с реестрами» не подходит к ревьюеру `<агент>:<id>`:
pre_merge его всегда отклонит, а подтверждает такое ревью Заказчик. Хвост лучше сделать нейтральным:
«…SKIPPED (N): см. stderr».

### n2 (nit): порядок трассировки и дата решения

- `tests/unit/test_j65_core_ready.py:23-25`: TC-J65-CORE-008 стоит перед 007.
- `PLAN-core-ready.md:9-11`: у ответа «Provenance-файл ревью» нет даты, а код и гайд ссылаются на 2026-11-16.

## Проверено, замечаний нет

- B1: правило для `<агент>:<id>` симметрично правилу для `deleg_…` без реестров. Структурные проверки sidecar
  (schema, change, вердикт, автор ≠ ревьюер, SHA, digest) идут до классификации ревьюера. Строка
  `Reviewer-Delegation` в .md имеет приоритет над sidecar, и для нее работает та же схема fail-closed.
- Доки: ci-gates, guarantees, README-flow-control, гайд внешнего оркестратора, скилл executor-swap и backlog J65
  согласованы с кодом, включая «вне CI (pre_merge) — отказ» для внешнего агента. backlog дописан, review-001
  не изменен.
- Сканер CHANGELOG: `SCANNED` включает `.py` из `COPY_FILES` без `factory_paths`. `DOC_CODE_RE` засчитывает только
  строки таблиц. Записи `NOT_CODES` живые. Порог `len >= 4` отсекает только служебные слова.
