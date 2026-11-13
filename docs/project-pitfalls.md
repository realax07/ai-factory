# База граблей фабрики

Подводные камни, вынесенные из AGENTS.md 2026-11-13 (J64.15: AGENTS.md —
только ядро правил). Пополняет debug-агент (agents/debug_agent.md) и ПМ.
Полный прежний текст AGENTS.md — archive/agents-md/AGENTS-2026-11-13.md.

## Стенд API ekotov-wiki

Копия для проекта — в его docs/project-pitfalls.md (перенос — задача
проекта).

- `python -m app.seed_users` требует пароли (getpass; без tty читает stdin —
  дефолты conftest подавать пайпом по 2 раза на пользователя).
- После seed обязательно `python -m app.migrate_r4` (нужен SECRET_KEY) —
  иначе роль wife=NULL и падает test_get_profile_second_user_gets_own_data.
- Аватары: тесты ждут `EKOTOV_WIKI_AVATARS_DIR`, приложение — `AVATARS_DIR`
  (задавать оба).

## Спеки OpenSpec

- Блок MODIFIED обязан воспроизводить Requirement целиком: все сценарии
  мастера дословно + изменения. Пояснения в заголовок секции не писать —
  `## MODIFIED Requirements (дополнение …)` валидатор отбрасывает.
- «validate 11/11» в сообщении СА может не воспроизводиться — ворота гонять
  на своей машине перед влитием (прецедент 2026-09-30).

## Сессии Hermes

- Признаки «мертвой сессии»: заголовок `/sessions` — subagent, context 0,
  ответов нет. Не слать `/stop` в пустоту: проверить
  `~/.hermes/logs/gateway.log` (`response ready`, `session_switch`,
  `Pinned async-delegation`) и `state.db` (end_reason последней сессии).
- Отчеты делегаций, сброшенные при rollover, — в
  `state.db → async_delegations.result_json`.
- Диспатч ровно на границе ротации дает субагент-контаминацию (upstream
  #92859): роль сабагента въедается в новую chat-сессию, делегация —
  `delivery_state='dropped'`. Детектор — `session_watchdog.py` §2.8.
- Состояние конвейера восстановимо из git (PLAN/backlog/MAP/реестр) и
  незакоммиченных артефактов worktree.
- Ретроспектива 48 сессий (2026-09-26): частые ошибки — `app` вне
  cwd=backend, нет bcrypt/playwright в используемом python. Профилактика —
  проверка среды в начале сессии.
