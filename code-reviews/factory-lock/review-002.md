Commit: 735eb3a6fe64a01ca2f93aee23904c29f5d59a33

Повторное ревью J65.7 (часть фабрики) после возврата review-001: диф
`e8ebd61..735eb3a`. Ревьюер — независимый сабагент (Claude Code), код не правил.

Итог: все три major из review-001 закрыты, проверено воспроизведением.
Minor 4, 9 и 10 исправлены. Minor 5, 6, 7, 8 и 11 записаны в резолюцию J65.7
бэклога как открытые кандидаты. Для части фабрики это приемлемо: они касаются
перевода проектов и снятия копий, которые вне объема этого PLAN. Остались
только minor.

## Проверка исправлений review-001

| # review-001 | Статус | Факт |
|---|---|---|
| 1 major (init и тесты зависят от git-состояния фабрики) | закрыт | factory_init.py:688-695: `install_factory_lock` не влияет на `ok`. Мой репро с фейковым `openspec` в PATH на HEAD 735eb3a, который не влит в main: `test_installers.py`, `test_j65_factory_lock.py`, `test_j54_tiers.py`, `test_j53_glossary.py`, `test_gate_harness.py` дают 45 passed (было 1 failed). |
| 2 major (два парсера, repo не проверяется в CI) | закрыт | Шаг CI (flow.yml:61-72) и `read_lock` (factory_lock.py:37,50-63) используют одну грамматику. Прогон шага bash'ем (`-e -o pipefail`) и `read_lock` на 15 входах: `repo=evil;rm`, две строки `repo=`, два `sha=`, `repo = a/b`, отступ, отступ перед `#`, лишний ключ, пустой файл, верхний регистр sha, `repo=a/b/c`, `repo=ab`, хвостовой пробел. Shell и python отвергают одни и те же входы. Корректные lock с пустыми строками и строками из одних пробелов оба принимают. Одно расхождение — CRLF, см. п.1 ниже. |
| 3 major (`published_head` = любая remote-ветка) | закрыт | factory_lock.py:89-101: `merge-base --is-ancestor HEAD origin/main` по локальной ссылке, без сети. Факт: на 735eb3a (не влит) — LockError «не влит в origin/main». На detached `origin/main~1` новая функция вернула a4f2618…, то есть ОК. |
| 4 minor (`persist-credentials`) | закрыт | flow.yml:88, есть ассерт в TC-004. |
| 9 minor (тесты `AI_FACTORY_HOME` и `if:`) | закрыт | test_j65_factory_lock.py:98, 111-112. |
| 10 minor (update не чинит битый lock) | закрыт | factory_lock.py:121-126, тест на `garbage` → update rc 0. |
| 5, 6, 7, 8, 11 minor | записаны в бэклог | Резолюция J65.7: перевод проектов не через `factory_init --force` вслепую, а точечными правками `flow.yml` и `factory_lock.py update`. Там же записаны копии `scripts/` в pytest проектов, `impact_rules.json`, allow-list `repo=`, текст предупреждения о промптах и локальный запуск ворот по lock. Это приемлемо, все пять относятся к следующему этапу (перевод проектов). |

## Замечания

| # | Серьезность | Где | Что не так | Рекомендация |
|---|---|---|---|---|
| 1 | minor | .github/workflows/flow.yml:64 против scripts/factory_lock.py:53 | CRLF-файл (`repo=a/b\r\nsha=…\r\n`): python (`read_text` с универсальными переводами строк) принимает, шаг CI отвергает (`\r` не входит в класс символов). Отказ безопасный, с понятной ошибкой в CI, но `factory_lock.py show` говорит ОК, а CI красный. | Либо `tr -d '\r'` перед grep в шаге, либо python читает с `newline=""` и отвергает `\r`. Добавить кейс в TC-003. |
| 2 | minor | PLAN-factory-lock.md:33 | «Вне объема» по-прежнему говорит: перевод проектов через `factory_init --force`. Это противоречит новой резолюции бэклога («не `--force` вслепую»). | Привести строку к резолюции. |
| 3 | minor | README.md:195; docs/README-flow-control.md:288; scripts/factory_init.py:513; scripts/factory_lock.py:20 | Формулировки отстали от кода. Пишется «опубликованный HEAD», а теперь требуется «HEAD, влитый в origin/main». Docstring factory_lock: exit 1 при «битом lock», но update теперь битый lock перезаписывает (exit 1 остался только у `show`). | Обновить формулировки. |
| 4 | minor | scripts/factory_lock.py:95-101 | Если ссылки `origin/main` нет (клон без origin, другое имя remote), `merge-base` дает 128, а сообщение говорит «не влит в origin/main». Отказ безопасный, но диагноз неточный. | Различать «нет ссылки origin/main» и «не предок». |

## Вердикт: approve
