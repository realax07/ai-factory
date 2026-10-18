# BUG-023: само-исключение regress-артефакта из свежестной сверки

## Суть
Свежестная сверка check_regress_final считала «последнее касание измененных
файлов» ВКЛЮЧАЯ сам regress-final.md — артефакт всегда новее удостоверяемого
кода → REGRESS_FINAL_STALE навсегда (ворота самоубийственны). Воспроизведено:
ekotov-wiki PR 189.

## Статус

- 2026-10-18: исправлено (pipeline/fix-regress-self-fresh: артефакт и
  test-model/regress/** того же change исключены из множества свежести;
  тесты test_bug023_regress_final_self_fresh.py). CLOSED — после merge и
  синхрона зеркал.
