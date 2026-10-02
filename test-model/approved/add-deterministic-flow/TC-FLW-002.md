# TC-FLW-002

- **Кейс:** Негативные регрессионные тесты на фиксы review-003 (M1–M5, m6–m9)
- **Change:** add-deterministic-flow
- **Источник:** code-reviews/add-deterministic-flow/review-004.md (вердикт APPROVE) — повторное ревью фикса ae7b30f: все пробы review-003 воспроизведены, 18 основных + 10 edge-проб
- **Статус:** approved (вердикт code-review APPROVE; автотесты green)

## Трассировка

- Источник требования: openspec/changes/add-deterministic-flow/specs/deterministic-flow/spec.md
- Чеклист: test-model/checklists/add-deterministic-flow.md (CHK-строки ниже)
- Реализация: tests/test_review003_fixes.py

[CHK-1] Проверка кейса TC-FLW-002 — автотесты в tests/test_review003_fixes.py green (прогон ревьюера review-004).

## Сценарий

1. Воспроизвести пробы ревьюера review-003 как регрессию: rename-эскейп (M1), миграция реестра v1→v2 без backup (M2), мертвый лок после crash (M3), zones_overlap FN/FP (M4), symlink за пределы зоны (M5), minors m6–m9.
2. Ожидание: каждый фикс адресен и покрыт негативным тестом; 27 тестов green. Подтверждено ревьюером review-004.
