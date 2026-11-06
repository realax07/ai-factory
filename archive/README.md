# Архив

Промежуточные артефакты, утратившие оперативную ценность (2026-10-10).

- `docs-data/` — машинные выжимки аудита ревьюеров (J20/J8): reviews*.json,
  review_metrics2/spans/delegs.json, flowctl_runs.json. Выводы вшиты в
  docs/audit-reviewers-tokens.md.
- `plans/` — планы влитых пакетов (`PLAN-<id>.md` переносятся сюда после merge).
- `docs/` — завершенные спайки/сценарии/планы: e12-speckit-spike (вердикт в
  README), shadow-r6-scenario, future_transform, plan-add-deterministic-flow.
- `pm-instruction-channel/` — архив мертвых каналов вотчдога делегаций
  (волна 4, АУД Н2/Н3, 2026-10-23): `watchdog_daily_digest.py` (суточный
  дайджест 23:00) и `pm_instruction_monitor.py` (change-detector крона
  pm-instruction-relay). Джобы отключены, скрипты ниоткуда не вызываются;
  живой канал ПМ — stdout delegate_watchdog (см. AGENTS.md правило 6).

Живые документы (guarantees, ci-gates, process-context, README-flow-control,
guides/pipeline-manifest) — в docs/; `docs/chatgpt-deterministic-flow/` —
историческое ТЗ J28 (реализовано), оставлено на месте ради ссылок из контракта. process-context возвращен из этого
архива в docs/ (читается при входе сессии).
