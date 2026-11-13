# RUNBOOK: аварийный merge при сломанном CI (J64.9)

Ruleset ветки `main` — **bypass никому**: merge только через PR с зелеными
`test-flow-control` и `flow`. Если сломан сам CI (упал OpenSpec CLI, Actions,
GitHub-раннер, внешняя зависимость), починка CI не может пройти собственные
проверки — merge невозможен. Эта процедура — единственный легальный выход.

**Кто выполняет:** только админ репозитория (Заказчик). Агенты и ПМ ruleset
не трогают: у них нет прав, и это правило (AGENTS.md п.4).

**Когда применять:** CI красный по причине вне кода PR, и это доказано
(лог шага, тот же отказ на `main`), а обычный PR починки не может стать
зеленым. Красный CI из-за кода — не авария: чинится обычным PR.

## Процедура

Ниже `R=realax07/ai-factory` (для проекта — его репозиторий).

1. **Снимок до.** Проверить и сохранить текущий ruleset:

   ```bash
   python3 scripts/ruleset_check.py --repo $R     # exit 0 до начала
   ID=$(gh api repos/$R/rulesets --jq '.[] | select(.name=="main") | .id')
   SNAP=~/ruleset-main-$(date +%Y%m%d-%H%M%S).json
   gh api repos/$R/rulesets/$ID \
     --jq '{name, target, enforcement, bypass_actors, conditions, rules}' > $SNAP
   ```

   Снимок — в домашнем каталоге (не `/tmp`), только поля, которые принимает
   PUT: им же ruleset восстанавливается целиком (шаг 5).

2. **PR починки** открыт, ревью есть (независимое, как обычно), красный
   только аварийный шаг CI. В описании PR — маркер `[emergency]` и ссылка
   на лог упавшего шага.

3. **Выключить ruleset** (админ):

   ```bash
   gh api -X PUT repos/$R/rulesets/$ID -f enforcement=disabled
   ```

4. **Влить PR починки** — обычным merge, ничего другого:

   ```bash
   gh pr merge <N> --merge
   ```

5. **Включить ruleset сразу:**

   ```bash
   gh api -X PUT repos/$R/rulesets/$ID -f enforcement=active
   python3 scripts/ruleset_check.py --repo $R    # exit 0 = боевое состояние
   ```

   `ruleset_check` сверяет цель (ветка main), enforcement, пустой bypass,
   правила PR-only и non-fast-forward и обязательные проверки. Exit 1 —
   восстановить ruleset целиком из снимка шага 1 и проверить снова:

   ```bash
   gh api -X PUT repos/$R/rulesets/$ID --input $SNAP
   python3 scripts/ruleset_check.py --repo $R
   ```

   Exit 2 (UNKNOWN) — у токена нет права видеть bypass ruleset: проверь
   под учеткой админа.

6. **Запись в incident-лог** —
   `test-model/incidents/<YYYY-MM-DD>-S2-emergency-merge-<slug>.md` (`<slug>` —
   что сломалось, например `openspec-cli`; формат post-mortem Флоу 3, J48)
   с обязательными разделами:

   ```markdown
   # S2-emergency-merge-<slug> — <дата>

   ## Таймлайн
   - <время> ruleset выключен (кто); <время> merge PR #<N> (SHA); <время> ruleset включен

   ## Root cause
   <почему CI красный вне кода PR + ссылка на лог шага>

   ## Action items
   - <что сделать, чтобы не повторилось>; вывод ruleset_check после включения: OK
   ```

   Запись — обычным PR, CI уже зеленый.

7. **Проверка CI на main** — следующий PR (или перезапуск на `main`)
   должен пройти обе проверки.

## Чего нельзя

- Вливать что-либо, кроме PR починки, пока ruleset выключен.
- Оставлять ruleset выключенным дольше шага 4 «на всякий случай».
- Добавлять bypass-исключения вместо выключения: исключение остается
  навсегда, выключение — видимый эпизод с записью.

## Репетиция

Приемка J64.9 — один прогон процедуры Заказчиком на безопасном PR (например,
правка документа с искусственно красным шагом не нужна: достаточно пройти
шаги 1, 3, 5 и 6 — выключить, сразу включить, `ruleset_check` = OK, запись в
incident-лог с пометкой «репетиция»). На репетиции пройти и восстановление из
снимка (`PUT --input $SNAP` при включенном ruleset): примет ли PUT все поля
параметров правил из снимка, без реального вызова не проверить. Отметка о репетиции — в резолюции J64.9
бэклога.
