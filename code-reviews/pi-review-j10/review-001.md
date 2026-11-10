# Ревью J65.4b: ревью стадий Pi в J10 (pi-review-j10)

Commit: 3bdcb685f67574399548aebb8daa624670bbd9c8

Ветка chore/pi-review-j10 поверх origin/main, диф `git diff origin/main...HEAD`
(6 файлов: scripts/package_runner.py, scripts/pr_validate.py, два теста, план,
резолюция в бэклоге J65). Ревьюер — независимый сабагент (Claude Code), код не правил.

Итог: прием в pr_validate сделан корректно и fail-closed. Возврат из-за одного major:
штамп раннера ложно останавливает повтор стадии ревью. Если в review-файле остался штамп
прошлой попытки той же стадии, раннер считает это подменой (RunnerStop), и каждый
следующий resume падает так же.

## Проверено

- `pytest tests/unit/test_j65_pi_review_j10.py tests/unit/test_j65_review_verdict.py -q` — 31 passed.
- Воспроизведение major: штамп попытки 1 (`deleg-aaaa…`), ревьюер дописал итерацию
  в тот же файл, штамп попытки 2 (`deleg-bbbb…`). Результат — `STOP: … не совпадает с
  делегацией стадии … — подмена` (скрипт в scratchpad, `python -I`).
- Совпадение полей записи раннера с `runner_review_ok`. flowctl ставит
  `delegation_id = deleg-<cid[:16]>` (flowctl.py:571), как и `gate_new`
  (package_runner.py:1071); `scope.change` = `--change <package>` (flow_state.py:926-931);
  `actor_role` = `flow_role("code-reviewer")` = `code_reviewer`; статусы `accepted` и
  `provisional` (flowctl.py:1373-1387, 1442). Пометку `package_runner` ставит только
  `gate_close` для `kind=flowctl` (package_runner.py:1203-1228), и только после того,
  как раннер принял стадию: `returned`, превращенный в `provisional` при прочих
  FAIL-гейтах, отсекает `_only_pr_gate_pending`, и тогда нет ни коммита, ни пометки.
- Порядок в cmd_run: gate_end → zone_recheck → штамп → commit_stage → gate_close →
  check_verdict → record_review_provenance. На Commit:/STALE штамп не влияет:
  `REVIEW_COMMIT_RE` (flow_check.py:93-95) строку `Reviewer-Delegation` не матчит,
  `parse_verdict` смотрит только заголовки. Provenance-запись считает digest по
  base..reviewed_sha до стадии ревью, поэтому правка review-файла в него не входит.
- optional-стадия: если после штампа отказ (commit_stage), `_reject` отправляет
  изменения в stash (`shelve_attempt`), и штамп уходит вместе с попыткой. Корректно.
- gate:/hermes:-стадии с `verdict` штамп не получают, и у них нет записи цикла flowctl.
  Для них J10, как и раньше, засчитывает только Hermes-делегацию. Регрессии нет.
- CI: state.db нет, `sqlite3.connect(file:…?mode=ro)` бросает OperationalError,
  и срабатывает `_exists = _ok = True`, как до изменения. На машине фабрики при
  нечитаемом flowctl_state будет `_fstate = {}`, и ревью не засчитывается (fail-closed).
- Подделка. flowctl_state.json лежит вне git, в том же `AF_STATE_DIR`, что и реестр
  сессий. Уровень доверия тот же, что у state.db: правка обоих — локальная запись в
  ~/.hermes. Запись чужого change или роли не `code_reviewer` отсекается. Delegation id
  стадии ревью рождается при входе стадии, так что dev-стадия заранее его не знает, а
  писать в `code-reviews/` ей не дает зона.
- `_dev_delegs` по `scope.task`: у раннерных dev-стадий без `task_id` (Флоу 4) автор
  в множество не попадает. Это не дыра: `runner_review_ok` отдельно требует, чтобы у
  той же делегации было `actor_role == code_reviewer`, а у каждой стадии и попытки
  своя делегация. Флоу 4 ([chore]) вообще идет через `check_chore`, без блока
  SELF_REVIEW. Нормализация `-`/`_` согласована: `_dev_delegs` и `runner_review_ok`
  приводят id к `_`.
- Документы: в «Вне объема» плана (sidecar для accept_review не добавлен, в CI реестров
  нет, проверка действует в pre_merge) все верно: `pr_validate` входит в `pre_merge`
  (gate_runner.py:129).

## Замечания

| # | Серьезность | Где | Что не так | Рекомендация |
|---|---|---|---|---|
| 1 | major | scripts/package_runner.py:617-625 (вызов 1697-1706) | Повтор стадии ревью дает ложный STOP «подмена». Каждая попытка получает новую делегацию (`gate_new`, новый cid), а worktree и файлы прошлой попытки сохраняются. После return/STALE (штамп закоммичен до check_verdict) или после сбоя commit_stage (штамп в дереве) ревьюер на resume дописывает итерацию в тот же `verdict.file` (append-only) или правит файл, не трогая шапку. Первый найденный `Reviewer-Delegation` — штамп попытки N, раннер видит его на попытке N+1 и бросает RunnerStop. Каждый следующий resume дает тот же STOP, пока ПМ не уберет строку руками. Штатный путь return → resume ломается. Воспроизведено (см. «Проверено»). Тестов на attempt>1 нет. | Своя делегация прошлых попыток этой стадии — не подмена. Нужно запоминать delegation_id прошлых попыток (`prev_gate` доступен в cmd_run, историю попыток держать в `flow_gates[stage]`) и такой штамп заменять. Либо раннер как авторитетный источник переписывает все строки `Reviewer-Delegation` в файле на делегацию стадии: pr_validate берет первое совпадение, поэтому старые строки оставлять нельзя. STOP оставить только для id, которого нет среди попыток стадии. Добавить тест: return → resume на том же файле → approve проходит, штамп один, с делегацией новой попытки. |
| 2 | minor | skills/pm-factory/pi/role-packs/code-reviewer/role-agents.md:49-52; agents/code_reviewer_agent.md («Машиночитаемый формат») | Роль-пак не говорит ревьюеру Pi, что строку `Reviewer-Delegation` ставит раннер. Полный промпт (пак называет его арбитром) требует писать `Reviewer-Delegation: deleg_<id>` первой метой. Ревьюер, который скопирует реальный id из соседних review-файлов `code-reviews/`, получит ложный STOP «подмена» уже на первой попытке. | В пак добавить строку: «`Reviewer-Delegation` не пиши — штамп ставит раннер (J65.4b); чужой id в файле = STOP». В промпте роли сделать оговорку для стадий `pi:`. Промпт и пак — зона ПМ или dev по реестру, решение ПМ. |
| 3 | minor | scripts/pr_validate.py:190-196 | Если делегации нет в Hermes и `runner_review_ok` отказал из-за совпадения с dev-делегацией или неверной роли, сообщение будет «не найдена в реестре делегаций», а не SELF_REVIEW. Ошибка в безопасную сторону, но диагностика вводит в заблуждение. | Различать «в реестре раннера нет записи» и «запись есть, но не ревью/не принята/≠ dev» (например, отдавать код причины из `runner_review_ok`). |
| 4 | minor | scripts/pr_validate.py:323-330; PLAN-pi-review-j10.md:22-24 | Формулировка «пометка package_runner — стадия принята и закоммичена» неточна. `gate_close` ставит пометку до вердикт-ворот, поэтому она есть и у стадии, которую раннер затем остановил на return/STALE. Еще она бывает с `commit: null` («без изменений»). Для независимости это неважно, вердикт J10 читает из файла, но STALE-approve, закоммиченный раннером перед STOP, J10 засчитает (STALE pr_validate не проверяет, это существовало и раньше). | Уточнить текст: «стадия прошла ворота выхода и закоммичена раннером», без «принята». По желанию — записывать итог вердикт-ворот в `package_runner` и требовать его в `runner_review_ok`. |
| 5 | minor | scripts/package_runner.py:1697-1706, 608-632 | Штамп пишет в `verdict.file` после `zone_recheck` без повторной сверки. Если файл вердикта существовал до стадии и лежит вне зоны ревьюера, правка вне зоны попадет в коммит стадии. Случай крайний, манифест так обычно не пишут. | Проверять, что `verdict.file` входит в зону резервации, до штампа, или сделать штамп до `zone_recheck`. |
| 6 | minor | tests/unit/test_j65_pi_review_j10.py:65-86 | TC-J65-PRV-002/003 проверяют `runner_review_ok` на синтетической записи. Сквозного теста «реальный gate_close раннера → `runner_review_ok` = True» нет: в test_j65_review_verdict `gate_close` и `gate_new` подменены, поэтому согласованность полей (delegation_id из cid, scope.change, пометка) сейчас держится только на ручной сверке выше. | Добавить real_flow_gates-тест, по образцу TC-PR-056 (test_package_runner.py:1855-1872): после cmd_run с review-стадией прочитать flowctl_state и проверить, что `runner_review_ok(<штамп из файла>, package, fstate, set())` возвращает True. |

## Не проверено

- Живой прогон раннера с Pi и реальным flowctl на стадии `pi:code-reviewer` (только юнит-тесты и чтение кода).
- Полный сьют: по заявлению автора 1333 passed, сам я гонял только два затронутых файла.

## Вердикт: return
