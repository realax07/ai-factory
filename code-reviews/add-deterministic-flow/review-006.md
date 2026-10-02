# Review-006 — повторное ревью: закрытие B1/M1–M3 (фикс a704920)

- **Ревьюер:** тот же независимый code-reviewer (review-001…005 — мои)
- **Дата:** 2026-10-02
- **База:** ветка `deterministic-flow`, HEAD `a704920` («review-005: закрыт B1 + M1-M3 + m1-m2-m3»)
- **Диф ревью:** `f68d31d..a704920` — 4 файла, +359/−66 (scripts/gate_runner.py, scripts/flow_transition.py, tests/test_gate_runner.py, tests/test_provenance.py)
- **Метод:** чтение диф-а + полный прогон тестов + **собственные live-пробы** на клоне реального репо (/tmp/rev006, /tmp/cli006) и на scratch-фикстурах; реальное репо не мутировано (`git status` — только предсуществующий `?? .gate-logs/`)
- **История ревью:** append-only; шестая запись, review-001…005 не изменялись

---

## Вердикт: **APPROVE**

Все замечания review-005 закрыты по существу и подтверждены моими независимыми live-пробами (не только тестами автора): B1 воспроизводится больше не как exit 0 — конфигурационная ошибка обязательного gate дает ERROR/exit 2, легальный SKIPPED дает overall=SKIPPED/exit 1; чужой sidecar → DENY; sidecar без digest → UNKNOWN; record-review без digest → exit 2. Регрессий не найдено: **251 passed** (мой прогон, 2026-10-02, 25.5s; было 244, +7 негативных). Один новый minor (m4) — не блокирующий, можно долгом.

---

## 1. Проверка замечаний review-005 (каждое — моей пробой)

| № | Фикс | Подтверждение (live, независимое) |
|---|---|---|
| **B1** (blocker) | `run_gate` получил `applicable_by_rule`; skip без явного правила → **ERROR**; в `run_gates` любой SKIPPED → overall=**SKIPPED**, `exit_code_for` → **1** | Моя проба review-005 (M1) воспроизведена: `run --repo . --scope pre_accept --gates pm_bounds_check` без `--pm-mode` → **exit 2**, статус gate ERROR, диагностика «обязательный gate не выполнен и БЛОКИРУЕТ переход». Полный scope pre_accept без pm-mode → exit 2, overall ERROR. `pm_mode=commits` без `--pm-commits` → ERROR/exit 2 (тест автора я не принимал — проверено живьем). exit 0 на этой пробе больше недостижим ✓ |
| **M1** | `load_review_provenance` возвращает 4-е значение `foreign`; `_provenance_findings` дает финдинг без `unknown=True` → **DENY** «approve другой задачи» | Live на фикстуре: единственный sidecar tasks=[1.2] при действии по 1.1 → **DENY, allowed=False**, в деталях «task_ids ['1.2'] не покрывают задачу 1.1», и это НЕ legacy-ветка (нет «legacy evidence»). Регрессия: чужой sidecar + покрывающий рядом → **ALLOW** (покрывающий выигрывает, чужой не портит) ✓ |
| **M2** | `GateReport.executed` (True только у реально запущенных), `skipped_gates` в отчете, пометка «НЕ ВЫПОЛНЕНЫ» в human-выводе; SKIPPED никогда не PASS | Live `run --scope pre_merge` на клоне: `[SKIPPED] pr_validate executed=False`, в отчете блок `skipped_gates`, строка «НЕ ВЫПОЛНЕНЫ (SKIPPED, не считаются пройденными)». Чистый случай (тест): единственный SKIPPED → overall=SKIPPED, **exit 1** — «не считается пройденным» закреплено в overall, а не только в тексте ✓ |
| **M3** | digest обязателен с двух концов: record-review без `--diff-digest` → exit 2 (argparse + явная проверка); `provenance_findings` без digest → UNKNOWN/MISSING_INPUT | Live CLI: record-review без digest → **exit 2**, sidecar не создан. Live на фикстуре: sidecar с task/change/SHA/ролью, но без digest → accept_review **UNKNOWN**, merge_task **не ALLOW** (было ALLOW в пробе C2 review-005). Регрессия: полный sidecar → ALLOW ✓ |
| **m1** | `is_stale` переписан с явными скобками | Live: отчет без `repo_head` при валидном HEAD → **STALE=True** (было False — дыра закрыта); старый SHA → True; текущий → False ✓ |
| **m2** | record-review сверяет `parse_verdict(.md)` с `--verdict`; проверяет существование `--commit` при `--repo` | Live CLI на клоне: `.md`=approve + `--verdict return` → **exit 2**, «sidecar поверх человеческого вердикта не записывается»; несуществующий SHA → exit 2; согласованный набор → exit 0, sidecar записан, и end-to-end `check_action` по нему дает **ALLOW** ✓ |
| **m3** | ревизия парсится `_review_file_revision` через `flow_check.REVIEW_FILE_REV_FIRST/TASK_FIRST` — единый парсер, без второго regex | Частично — см. новый **m4** ниже |

**Семантика SKIPPED — оценил допустимость по ТЗ.** ТЗ 05: статус-набор PASS|FAIL|ERROR|SKIPPED; «SKIPPED разрешён только когда gate неприменим по явному правилу»; приемка «pr_validate … не считается пройденным» и «падающий, отсутствующий и зависший gate блокируют переход с разными кодами». Реализация: конфигурационная ошибка → ERROR/exit 2 (это «отсутствующий gate» — блокирует), легальный SKIPPED (только pr_validate без PR-контекста) → overall=SKIPPED/exit 1. Различение «не выполнен» от «провален» при гарантированном блокировании — допустимо и честно: зеленого прохождения при невыполненном gate не существует ни в одной ветке (`overall != PASS`, `exit >= 1` на полном наборе pre_accept проверено). Единственная шероховатость: exit-код SKIPPED (1) совпадает с FAIL — но коды для «падающий/отсутствующий/зависший» (1/2/2+overall) различимы по отчету, а ТЗ требует разные коды именно для этой тройки. Замечание не возвожу в defect.

## 2. Регрессии и границы

- **Тесты:** мой полный прогон — **251 passed** (25.54s). Новые негативные тесты без ручной подстановки overall: `test_pm_bounds_requires_explicit_mode` (теперь честный ERROR/exit 2 — маскировавшая строка `report["overall"] = STATUS_FAIL` удалена), `test_pre_accept_without_pm_mode_not_green` (полный набор фазы), `test_foreign_task_sidecar_denied_not_unknown`, `test_missing_diff_digest_unknown_not_allow` (+merge), CLI-негативы digest/вердикт.
- **Живые пробы на реальном контенте:** pre_merge на клоне реального репо — pm_bounds в явном режиме реально запускается (PASS), flow_check честно FAIL по J10 (15 задач без review — известно с review-005, это правда, не регрессия), pr_validate SKIPPED, общий exit 1.
- **Границы диф-а:** `git diff f68d31d..a704920 --name-only` — ровно 4 файла; contracts/, openspec/, docs/, code-reviews/, flow_check.py, pm_bounds_check.py, pr_validate.py, session_check.py, flow_state.py **не тронуты** ✓. Огр. 2 (00-README) соблюдено ✓.
- **Обратно-совместимое поведение подтверждено пробами:** полный sidecar → ALLOW (accept и merge-путь не деградировал: merge по-прежнему UNKNOWN только из-за EXTERNAL_ENFORCEMENT_UNKNOWN, как в review-005); легаси-ветка не расширена; STALE-механика работает (m1-пробы).

## 3. Новые замечания

| № | Место | Серьезность | Замечание и рекомендация |
|---|---|---|---|
| m4 | scripts/flow_transition.py:484–497 (`_review_file_revision`), 530, 535 | **minor** | **Единый парсер ревизии ни разу не срабатывает на реальных именах sidecar: rev всегда 0.** `_review_file_revision(pf.name)` получает имена вида `review-002-1.1.md.provenance.json`, а оба regex (`REVIEW_FILE_REV_FIRST`/`TASK_FIRST`) заанкорены на `\.md$` — на sidecar-именах не совпадают (моя проба: rev=0 для `review-001-…`, `review-002-…`, task-first). Следствие: (а) выбор «последнего» sidecar вырождается в лексикографический max имени; для rev-first имен с нулевым дополнением `%03d` это численно совпадает, но при смешении форматов (rev-first vs task-first) порядок не по ревизии; (б) трекинг «чужого» sidecar всегда берет первый по sorted(). Направление безопасное (fail-closed: невалидный выбранный sidecar дает DENY/STALE, а валидный сосед все равно дал бы ALLOW), поэтому minor, не major. Рекомендация: парсить ревизию из **внутреннего** имени .md — срезать `PROVENANCE_SIDECAR_SUFFIX` перед матчингом (например `_review_file_revision(pf.name[:-len(SUFFIX)] if pf.name.endswith(SUFFIX) else pf.name)`), либо матчить на `review_path` из payload sidecar. Можно долгом: на исходное замечание m3 («порядок не определен для task-first») фикс в текущем виде ответа не дает — оно нейтрализовано fail-closed-поведением, но заявленное в коммите «парсится единым парсером» фактически не выполняется ни для одного файла. |

## 4. Что проверено (сводка)

- B1-проба review-005 (pm_bounds без режима) — больше не exit 0: exit 2/ERROR живьем на клоне ✓
- Легальный SKIPPED → overall=SKIPPED, exit 1, executed=false, skipped_gates, «НЕ ВЫПОЛНЕНЫ» ✓
- M1: чужой sidecar → DENY (не legacy-UNKNOWN); с покрывающим рядом → ALLOW ✓
- M3: без digest → UNKNOWN на accept и merge; record-review без digest → exit 2 ✓
- m1/m2: STALE-скобки и сверка вердикта/SHA живьем через CLI ✓
- Регрессия: 251 passed (мой прогон); полные sidecar-пути ALLOW; merge UNKNOWN только из-за EXTERNAL_ENFORCEMENT_UNKNOWN (как было) ✓
- Семантика SKIPPED по ТЗ 05 — допустима (см. выше) ✓

## 5. Что НЕ проверено (честно)

- `openspec validate` реальным CLI — как и в review-005, CLI в среде нет; только fake-executable.
- Мультипроцессная гонка audit JSONL; diff-digest на merge-коммитах — вне зоны, перенесено из review-005 без изменений.
- Интеграция с оркестратором (поставка 06) — вне зоны.

## 6. Рекомендация

**APPROVE.** Задача может вливаться. m4 — долгом к поставке 06 (однострочный фикс среза суффикса + тест на выбор ревизии между rev-first и task-first sidecar); процессная рекомендация review-005 (именовать review-файлы с task-id, чтобы J10 не горел честно) остается в силе.
