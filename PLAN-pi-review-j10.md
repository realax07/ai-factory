# PLAN-pi-review-j10: ревью стадий Pi в J10 (J65.4b)

**Флоу: 4** — обслуживание фабрики: прием ревью стадии `pi:code-reviewer`
пакетного раннера в проверке PR (J10, pr_validate).

## Решение Заказчика (2026-11-10)

«Давай все что можно сделать до 66» — J65.4b в списке.

## Проблема

pr_validate засчитывает approve в `code-reviews/<change>/` только при строке
`Reviewer-Delegation: <id>`, найденной в реестре делегаций Hermes
(`state.db → async_delegations`, completed, ≠ dev-делегация). У стадии Pi
раннера записи в Hermes нет — ее approve в финальном PR не засчитывался.

## Сделано

- раннер (`stamp_reviewer_delegation`): после приемки стадии ревью и до ее
  коммита ставит в review-файл штамп `Reviewer-Delegation: <делегация
  стадии>`; совпадающий штамп — без изменений, чужой — STOP (подмена);
- pr_validate (`runner_review_ok`): делегации нет в Hermes → доказательство по
  записи цикла flowctl раннера: роль `code_reviewer`, тот же change, статус
  accepted|provisional, пометка `package_runner` (стадия принята и
  закоммичена), ≠ dev-делегация;
- тесты TC-J65-PRV-001…004.

## Вне объема

Sidecar рядом с review-файлом для `flow_transition.provenance_findings`
(accept_review) не добавлен: раннер не проходит accept_review, а sidecar,
записанный раннером, ослаблял SELF_REVIEW (возврат J65.4, review-001) —
аудит-запись остается в `<план>.runner-reports/`. В CI (GitHub) реестров
Hermes и flowctl нет — проверка, как и раньше, действует на машине фабрики
(ворота pre_merge).

## Критерий закрытия

Сьют зеленый, ревью approve, CI зеленый; резолюция J65.4b в бэклоге.
