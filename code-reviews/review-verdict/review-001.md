# Code review — review-verdict (J65.4 / J64.12), review-001

Ревьюер: code_reviewer (независимый сабагент Claude Code; автор диффа — другой исполнитель)
Commit: ffa22016c197107665f785cbb234123e2f64f5dc
Дата: 2026-11-06
Предмет: `git show ffa2201` — единый парсер вердикта (`flow_check.parse_verdict`),
`review_commit`, `review_sidecar_problem`, вердикт-ворота и provenance раннера,
pr_validate / pm_bounds_check, паки Pi, документы.

## Итог

Основа правильная: один парсер вместо подстроки, «Не одобрить» и шаблон —
return, last-wins согласуется с append-only историей, pm_bounds_check больше не
держит свою копию. Регрессий парсера на реальных файлах не нашел (см.
«Проверено»). Но у provenance-части два дефекта, которые ломают заявленное
поведение (ложный STALE на gate-стадии; sidecar раннера несовместим с
потребителем в flow_transition), а `review_sidecar_problem` ослабляет
SELF_REVIEW-защиту pr_validate: чтобы обойти сверку с реестром, хватает
написанного вручную JSON.

## Замечания

| # | Серьезность | Место | Сценарий | Рекомендация |
|---|---|---|---|---|
| 1 | major | scripts/package_runner.py:1447-1448 (gate-стадия), check_verdict :580-584 | Вердикт стоит на gate-стадии после pi-ревьюера (поддерживаемый вариант, TC-PR-033). Ревьюер по паку пишет `Commit: <HEAD до ревью>`. Gate-стадия сверяет его с `_git_head(worktree)`, то есть с HEAD уже **после** коммита стадии ревью. Итог — STALE и STOP всегда. Воспроизведено: review-файл с `Commit: <HEAD до ревью>` и `verdict:` на `gate:true` после стадии `pi:code-reviewer` → rc=2, «STALE … выдан на коммит 9aa0ae4…, а проверялся 3a24c64…». | На gate-стадии сравнивать с `base_sha` той pi-стадии, которая последней меняла файл вердикта (или с родителем коммита, внесшего файл), либо не делать STALE-сверку на gate-стадии. Добавить тест: gate-стадия + строка Commit. |
| 2 | major | scripts/flow_check.py:228-255 (`review_sidecar_problem`); scripts/pr_validate.py:175-184; tests/test_j65_review_verdict.py:249-266 (TC-J65-VRD-009) | Валидный sidecar полностью **заменяет** сверку `Reviewer-Delegation` с `async_delegations` (exists + completed + не dev). Проверяется только, что `reviewer_delegation`/`author_delegation` не пустые, различны, не входят в dev-делегации и что вердикт совпадает. Любой, кто пишет в `code-reviews/<change>/`, кладет рядом `review-001.md` и `{"reviewer_delegation":"a","author_delegation":"b","verdict":"approve"}` — J10 (`approved_review_tasks`) и SELF_REVIEW pr_validate засчитаны. Раньше на машине фабрики выдуманный `deleg_x` отклонялся реестром. Не проверяются `schema_version`, `reviewed_commit_sha`, `diff_digest`, `change`. TC-009 закрепляет минимальный JSON без SHA и digest как валидный. | Сверять `reviewer_delegation` с реестром, в котором есть делегации раннера (flowctl state / session registry: запись с ролью-ревьюером, закрытая, в этом change), а `author_delegation` — с dev-записью. Как минимум требовать `schema_version == review-provenance/1`, непустые `reviewed_commit_sha`, `diff_digest` и `change == change_id`. В TC-009 добавить негатив «sidecar без SHA/digest/schema → дефект». Если машинная сверка вне фабрики (CI) невозможна, записать в docs/guarantees.md, что sidecar в CI — заявление, а не доказательство. |
| 3 | major | scripts/package_runner.py:589-621 (`record_review_provenance`) против scripts/flow_transition.py:1110-1185 (`provenance_findings`) | Sidecar раннера пишется по схеме `review-provenance/1`, но смысл полей расходится с потребителем: `reviewed_commit_sha` = HEAD **до** ревью, а после него раннер делает еще два коммита (ревью и sidecar); `diff_digest` = `base(первая стадия)..reviewed`, а flow_transition сверяет его с `HEAD^..HEAD`. Проверка: sidecar из TC-004 через `provenance_findings` на HEAD пакета дает 2× STALE_EVIDENCE (SHA и digest). Кроме того, `task_ids=[package]`, если `task_id` не задан: при `accept_review`/`merge_task --task N` sidecar становится «чужим» → DENY «approve другой задачи». Раньше было легаси-UNKNOWN. Дыры не открывает (оба исхода не ALLOW), но заявленная совместимость с flow_transition не выполняется, и merge_task по пакету раннера получает DENY с ложной причиной. | Свести семантику: либо reviewed/digest — в терминах flow_transition (и документировать, на каком HEAD их проверять), либо отдельный маркер источника (`source: package_runner`), который flow_transition проверяет по своим правилам (reviewed — предок HEAD, после него только коммиты review/sidecar). Минимум — описать ограничение в guide/guarantees и вынести в бэклог. |
| 4 | minor | docs/guarantees.md:73-77 | Пишет «Остается: J10 в pr_validate сверяет Reviewer-Delegation с реестром Hermes — ревью стадии Pi там не найдется». После этого коммита pr_validate принимает sidecar вместо Reviewer-Delegation, то есть текст противоречит коду. | Переформулировать: ревью стадии Pi засчитывается по sidecar; ограничение — из замечания 2 (sidecar без машинной сверки делегаций). |
| 5 | minor | scripts/flow_check.py:89-91 (`REVIEW_COMMIT_RE`), package_runner.py:579 | Строка Commit необязательна: без нее STALE-сверки нет. Строки `**Commit:** abc1234` и `- Commit: abc1234` (типичный markdown модели) не распознаются (проверено → None), и сверка молча отключается. Приемка ТЗ J65.4 («STOP … на commit ≠ HEAD») при этом поля commit как такового не требует; отклонение в плане не описано. | Либо разрешать в регэкспе `**`/маркер списка, либо выдавать WARNING раннера «Commit: не найден — STALE не проверен». Опциональность описать в PLAN как отклонение от ТЗ. |
| 6 | minor | scripts/package_runner.py:1654-1667, 1641-1650 | (а) Коммит sidecar падает (RunnerStop) → STOP, но `<review>.provenance.json` остается незакоммиченным в worktree. При resume стадия ревью переисполняется, и session_check (`zone_holds` — точный glob `…/review-001.md`) видит sidecar вне зоны → снова STOP. Пока ПМ не удалит файл руками, resume не пройдет. (б) Стадия помечается `done` и state пишется до provenance: если процесс прервать между ними, после resume стадия пропускается, а sidecar так и не появляется (fail-closed в pr_validate, но молча). | (а) При ошибке provenance удалять/сбрасывать sidecar или включать его путь в зону стадии; (б) записывать `done` после provenance или делать на resume досоздание sidecar для done-стадии с verdict без sidecar. |
| 7 | minor | scripts/package_runner.py:598-604 | Автор — «последняя предыдущая pi-стадия другой роли с коммитом». Если dev-стадия ничего не закоммитила (commit None) или между dev и ревью стоит другая pi-стадия (design-validator, qa-*), автором записывается чужая делегация. Если pi-стадий нет вовсе — `package:<имя>`, не делегация. На независимость это не влияет (≠ ревьюеру), но атрибуция ложная. | Брать автора по роли (dev/qa_automation — по типу ревьюера) или из явного поля манифеста (`reviews: <stage-id>`). |
| 8 | minor | PLAN-review-verdict.md:30-31, коммит-сообщение, backlog J65 резолюция | «На 316 файлах вердикт не изменился». Скрипт verdict_compare.py импортирует уже новый `flow_check` (sys.path `scripts`) — старая логика в нем не воспроизводится, поэтому сравнение вырождено. Мое сравнение со старым `flow_check` из `ffa2201~1` на 384 файлах (фабрика + 3 клона, включая `review-architecture.md` в `openspec/changes/archive/`) дало 2 изменения: ekotov-wiki `2026-10-31-p23-fastline/review-architecture.md` и `2026-10-31-weather-service/review-architecture.md`, return → approve. Оба изменения верны (повторное ревью дописано в конец), но затрагивают `architecture_review_verdict` во flow_transition. | Поправить формулировку («2 изменения, оба — корректный last-wins по повторной проверке»), скрипт сравнения грузить со старой копией модуля. |
| 9 | minor | scripts/flow_check.py:79-80 (`VERDICT_LINE_RE`, существовало до коммита) | `\s*` после «Вердикт» захватывает переводы строк: `### Вердикт\n\n**RETURN.**` читается как вердикт (на этом и держатся 2 файла из п.8). С last-wins цитата/история вида `### Вердикт: approve (review-001)` ниже действующего return даст ложный approve; в обратную сторону (`approve — доработки не требуются` → return) ошибка безопасная. | Вне объема J65.4 — завести в бэклог: `[ \t]*` вместо `\s*` и игнорировать fenced/цитатные блоки. |

## Проверено

- Парсер: 16 пограничных строк (пояснения после вердикта, нумерованные заголовки, `**APPROVE**`, «returned», «Не одобрить», шаблон, last-wins в обе стороны, вердикт в code-fence и цитате, проза без `##`) — поведение fail-closed, кроме п.9. `review_commit`: последний матч, регистр, backticks; `**Commit:**` и `- Commit:` не распознаются (п.5).
- Регресс парсера: старый `flow_check.parse_verdict` (из `ffa2201~1`) против нового на 384 review-файлах фабрики, ai-factory main и клонов auto-school/child_bot/ekotov-wiki — 2 изменения (п.8), остальные совпали.
- Раннер: порядок done → verdict → provenance → STOP; return коммитит sidecar и STOP; STALE и «нет вердикта» — без sidecar; optional + return → skipped (sidecar остается); resume после return переисполняет стадию и перезаписывает sidecar следующим коммитом.
- Ложный STALE на gate-стадии (п.1) воспроизведен тестом в scratchpad: rc=2 STALE.
- Sidecar раннера через `flow_transition.provenance_findings` (п.3): 2× STALE_EVIDENCE, `task_ids=['vrd-pkg']`, `review_path` — абсолютный путь worktree в закоммиченном JSON.
- Подделка sidecar (п.2): по коду `review_sidecar_problem` и TC-009. Pi zone-guard префиксный и пропускает `review-001.md.provenance.json`, но session_check (точный glob) поймает его на выходе стадии, а раннер все равно перезаписывает sidecar. Путь подделки — не Pi-ревьюер, а любой автор с записью в `code-reviews/`.
- Копии в проекты: `flow_check`, `pr_validate`, `pm_bounds_check` в `factory_init.COPY_FILES`. Новых внешних импортов нет: `flow_check` — stdlib + json, `pm_bounds_check` импортирует `flow_check` из того же каталога.
- Тесты: `tests/test_j65_review_verdict.py tests/test_package_runner.py` — 122 passed (HOME=vps-home, python3.14). Адаптации TC-PR-032/034 корректны (`[test-adapted]` проставлены). Пробелы: нет теста gate-стадия + Commit (п.1), нет теста совместимости с flow_transition (п.3), TC-009 закрепляет слабый sidecar (п.2).
- Документы и паки: формат вердикта и `contains` описаны согласованно; противоречие — п.4.

## Не проверено

- Полный сьют, `ci_local`, flow_check репо — не повторял (данные ПМ: 1246 passed / 2 skipped, flow_check OK).
- Реальный прогон Pi/flowctl (`gate_begin`/`gate_end` с настоящим реестром), а также поведение `delegation_id` раннера в flowctl state (`_dev_delegs` pr_validate).
- `gate_runner record-review` вручную (код не менялся, парсер общий).
- Мутационные прогоны ПМ не перепроверял.

## Вердикт: return

## Исправления по возврату (ПМ)

- **Major 1** ложный STALE на gate-стадии: STALE сверяется только на pi-стадии (HEAD до ревью известен); gate-стадия — без сверки (TC-J65-VRD-009).
- **Major 2** sidecar ослаблял SELF_REVIEW: прием sidecar в J10 (`approved_review_tasks`) и pr_validate откачен полностью (`pr_validate.py` = origin/main); прием ревью стадий Pi в J10 через реестр раннера — отдельная задача J65.4b в бэклоге.
- **Major 3** несовместимость с `flow_transition.provenance_findings`: sidecar рядом с review-файлом больше не кладется и не коммитится; provenance раннера — аудит-запись `<план>.runner-reports/<stage>-<попытка>.provenance.json` (scope `runner-audit`), воротами не читается (TC-J65-VRD-004 проверяет отсутствие файла рядом с review).
- №4 guarantees.md приведен к коду (риск J65.4b назван).
- №5 `Commit:` — варианты `**Commit:**`, `- Commit:` (TC-J65-VRD-003); опциональность строки описана в гайде и плане.
- №6 resume: записи вне worktree и без коммита — повтор не встает на файле вне зоны; вердикт и запись — до отметки стадии done.
- №7 авторы — все pi-стадии других ролей с коммитом после предыдущей review-стадии (список `authors`).
- №8 регресс: сравнение со старым парсером из origin/main (не degenerate) на 344 файлах — 2 изменения, оба верные (архивные review-architecture.md с дописанным APPROVE).
- №9 сужение «Вердикт» до одной строки опробовано и откачено: ломало 19 реальных файлов (формат «## Вердикт» + значение следующей строкой); зафиксировано тестом TC-J65-VRD-010 и комментарием у регэкспа.

## Повторная проверка (e42591b)

Ревьюер: code_reviewer (независимый сабагент, тот же, что review-001 выше)
Commit: e42591b
Дата: 2026-11-06
Предмет: `git diff ffa2201 e42591b`

### Major из review-001

| # | Статус | Чем подтверждено |
|---|---|---|
| 1 ложный STALE на gate-стадии | закрыт | `package_runner.py` (gate-ветка): `check_verdict` вызывается без `reviewed_sha`, STALE сверяется только на pi-стадии против `gate["base_sha"]`. Мой repro из review-001 (gate-стадия + `Commit: <HEAD до ревью>`) теперь проходит без STOP (assert на STALE падает — так и должно быть). TC-J65-VRD-009 тоже это покрывает. |
| 2 sidecar ослаблял SELF_REVIEW | закрыт | `review_sidecar_problem` удален; `git diff origin/main e42591b -- scripts/pr_validate.py` пуст; в `approved_review_tasks` снова `meta = REVIEWER_META_RE`. Ссылок на sidecar в scripts/docs/паках нет. Остаток (прием ревью Pi в J10) честно назван: J65.4b в бэклоге, guarantees.md, guide. |
| 3 несовместимость с flow_transition | закрыт | Рядом с review-файлом sidecar больше не пишется и не коммитится. Запись лежит в `<план>.runner-reports/<stage>-<попытка>.provenance.json` (`scope: runner-audit`), и `load_review_provenance` (глоб `code-reviews/<change>/review-*.provenance.json`) ее не видит. TC-004 проверяет, что рядом с review файла нет. |

Минорные пункты review-001: №4 (guarantees.md) приведен к коду; №5 `**Commit:**` / `- Commit:` распознаются (TC-003); №6 — запись вне worktree (resume больше не встает на файле вне зоны), вердикт и запись делаются до `done`; №7 — список `authors` со сбросом на предыдущем ревью; №8 — пересчитано. №9: откат принимаю. Довод с 19 реальными файлами «## Вердикт» + значение следующей строкой весомый, TC-010 и комментарий у регэкспа фиксируют решение.

### Новые замечания

| # | Серьезность | Место | Суть | Рекомендация |
|---|---|---|---|---|
| R1 | minor | PLAN-review-verdict.md:27-28 | По-прежнему написано «Проверено на 316 review-файлах … вердикт не изменился ни у одного». Это противоречит строке 50 того же плана (344 файла, 2 изменения). | Исправить строку 27-28 или сослаться на раздел пересмотра. |
| R2 | minor | scripts/flow_check.py:94-95 | Форма `**Commit**: abc1234` (двоеточие вне жирного) не распознается, и STALE молча не проверяется. Пак инструктирует `Commit: <sha>`, так что это граничный случай. | По желанию: `(?:\*\*)?Commit(?:\*\*)?:(?:\*\*)?`. Не блокирует. |

Нового дефекта в порядке раннера не нашел. Return: запись → `state_write` → `_fail` → `stopped`; resume переисполняет стадию с attempt+1 и новым файлом записи. Optional + return → skipped. Если запись не удалась → STOP: коммит стадии уже сделан, а файл записи вне worktree зону не засоряет. Gate-стадии в цикле авторов пропускаются (`kind != pi`).

### Проверено

- Дифф `ffa2201..e42591b`: scripts, tests, документы, паки.
- `tests/test_j65_review_verdict.py` + `tests/test_package_runner.py`: 122 passed (HOME=vps-home, python3.14).
- `python3 scripts/flow_check.py .`: OK.
- Старый парсер (`ffa2201~1`) против нового на 385 файлах (worktree, ai-factory main, auto-school, child_bot, ekotov-wiki): 2 изменения, те же архивные `review-architecture.md` ekotov-wiki, return → approve, оба верные.
- `pr_validate.py` совпадает с origin/main; `review_sidecar_problem` нигде больше не упоминается.

### Не проверено

- Полный сьют и ci_local (данные ПМ: 1246 passed).
- Реальный прогон Pi/flowctl.
- J65.4b — вне объема.

## Вердикт: approve
- R1 (316 vs 344 в плане), R2 (`**Commit**:`) — исправлены (ПМ).
