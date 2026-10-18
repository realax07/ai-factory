# BUG-024: мета-файлы в свежестной сверке regress-final — ложный STALE

## Суть
Свежестная сверка check_regress_final считала «измененные файлы» включая
мета-файлы, не влияющие на поведение тестов: code-reviews/** (мета
Reviewer-Delegation), test-model/regress/** (сам артефакт и предыдущие
прогоны — BUG-023 исключал только каталог своего change),
test-model/reviews/** (ревью-мета). Любой мета-коммит после
regress-прогона → ложный REGRESS_FINAL_STALE → обязательный лишний
полный перегон. Третье проявление класса «свежестная сверка vs
артефактные/meta-файлы»: воспроизведено на ekotov-wiki PR 191.

## Статус

- 2026-10-18: исправлено (pipeline/fix-regress-meta-fresh): из множества
  «измененных файлов» при свежестной сверке (_regress_commit_problem)
  исключены мета-пути code-reviews/**, test-model/regress/**,
  test-model/reviews/**. Продуктовые и тестовые файлы (services/**,
  backend/**, frontend/**, tests/**, openspec/**) — как прежде: правка
  после прогона = STALE. Тесты: tests/test_bug024_regress_meta_fresh.py
  (TC-BUG-024-001..007); контрактный кейс BUG-023 TC-BUG-023-004
  переведен на новое ожидание (артефакт чужого change → PASS). OPEN —
  до merge и синхрона зеркал.
