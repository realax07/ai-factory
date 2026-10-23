# Флоу 4 — обслуживание ([chore])

- change-id ровно `chore` (regex ^chore$); минимальные ворота: flow_check + pm_bounds_check.
- Примеры: чистка веток, архивация артефактов закрытых релизов, переезд REPORT-файлов, обновления ядра конвейера ([pipeline] внутри фабрики).
- Self-referential flow_check FAIL на активном change — норма, снимается архивацией, не правкой ворот.
