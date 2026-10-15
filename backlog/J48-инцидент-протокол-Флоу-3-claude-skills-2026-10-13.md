# J48 — инцидент-протокол Флоу 3 (найдено в microобзоре claude-skills, Заказчик 2026-10-13)

**Флоу работы: 1** (полный — change-пакет меняет спеку конвейера и STAGE_TABLE).
Протокол касается **Флоу 3** (хотфикс) — не путать: цифра флоу работы и цифра
флоу, который усиливаем, — разные вещи (источник путаницы 2026-10-14). Источник: engineering-team/skills/
incident-commander + incident-response (obra-стиль, MIT) — «Battle-tested
SRE/DevOps practices: severity classification, initial response 0–15 min,
mitigation, post-incident review».

## Проблема

Флоу 3 (хотфикс прода) сегодня: emergency_stabilize + incident_ref обязателен
+ deploy_rollback — но протокол реагирования не формализован: severity
классификация нет, «кто/что в первые минуты» нет, post-incident review нет
(прецедент — инцидент 2026-10-05, J25, разобран ad hoc).

## Кандидаты взять из incident-commander/response

- **Severity-матрица** (S1 прод лежит / S2 деградация / S3 некритично) →
  определяет состав реакции (S1 = отката немедленно, S2 = хотфикс-PR,
  S3 = обычный Флоу 2);
- **Initial response 0–15 мин**: stabilize (откат/фичефлаг) → уведомление
  Заказчика (что/кто/ETA) → incident_ref фиксация → только потом разбор;
- **Post-incident review** (post-mortem): таймлайн, root cause, что изменим
  (воплощается в change-пакете/бэклоге), action items — без обвинений;
  append-only в `test-model/` или docs/incidents/;
- **Common pitfalls** (их список сверить с нашими уроками).

## Критерий закрытия

- Флоу 3 в openspec + STAGE_TABLE дополнен severity-классификацией
  (incident_ref = S1/S2/S3 + пост-мортем обязателен для S1/S2);
- Промпт devops/dev дополнен initial-response протоколом;
- flow_check: S1/S2 архивация без post-mortem = нарушение.
