# BUG-022: check_regress_final в CI — ложный REGRESS_FINAL_STALE; попутно: гонка лока реестра session_check

## Суть

Ворота regress-final (`pr_validate.check_regress_final`) в CI-клоне давали
ложный REGRESS_FINAL_STALE — блокировали merge живого релиза. Воспроизведение:
ekotov-wiki PR 189. Две причины в CI-клоне:

1. worktree из артефакта — локальный путь машины прогона, в CI-клоне нечитаем
   → трактовался как STALE;
2. shallow-клон: merge-base не может верифицировать предка → UNKNOWN трактовался
   как STALE.

Возврат-фикс по CI этого же PR вскрыл вторую, независимую ошибку в
`scripts/session_check.py`: гонка `_acquire_lock` — pid-файл лока, созданный
но еще не записанный (окно между `mkdir()` и `write_text`), читался как
пустой → `pid_alive("")` возвращала False → лок ЖИВОГО владельца снимался
мгновенно → два конкурентных reserve входили в критическую секцию одновременно
(CI test-flow-control: `test_concurrent_reserve_intersecting_exactly_one_wins`
— ожидалось `[LOSE, WIN]`, получено `['WIN', 'WIN']`; редкий флак — окно
микросекундное, на загруженном CI-раннере растягивается планировщиком).

## Статус

- 2026-10-18: исправлено (pipeline/fix-regress-final-ci, PR #132).
  (1) нечитаемый worktree — неблокирующий FLOW-WARNING, STALE только при
  читаемом дереве с HEAD ≠ commit; shallow-клон — тихий
  `git fetch --unshallow` (refspec всех веток, таймаут 120с), при неудаче —
  ancestry через GitHub API compare, иначе явный FAIL UNKNOWN_ANCESTRY.
  Тесты TC-BUG-022-001..008 + TC-R3-008 на новый контракт.
  (2) `_acquire_lock`: пустой/нечитаемый pid лока больше не считается
  мертвым владельцем — ждет как живой, съем только по полному таймауту;
  мертвый владелец снимается как прежде. Регресс-тесты TC-SCH-002
  (test_lock_with_empty_pid_file_is_not_stolen,
  test_lock_of_dead_owner_is_stolen_live_is_not).
  CLOSED — после merge и синхронизации зеркал (ekotov-wiki PR 189 — живое
  воспроизведение, перепроверить ворота regress-final на зеркале после
  синхрона).
