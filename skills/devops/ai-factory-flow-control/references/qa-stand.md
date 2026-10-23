# QA-стенд ekotov-wiki: ручная сборка после ребута хоста

/tmp и docker-контейнеры не переживают reboot — стенд собирается вручную по этому
рецепту (проверен). Порядок: app → схему+seed → nginx → прогоны. Если внешний
стенд не окупается — автостенд (раздел в конце): он покрывает почти все web-тесты
и не ломается о специфичные nginx-настройки.

## 1. App (uvicorn :8080)

```bash
mkdir -p /tmp/qa-r8/verify/images /tmp/qa-r8/verify/avatars
cd <repo>/backend
env -i DB_PATH=/tmp/qa-r8/verify/app.db EKOTOV_WIKI_IMAGES_DIR=/tmp/qa-r8/verify/images \
  EKOTOV_WIKI_AVATARS_DIR=/tmp/qa-r8/verify/avatars SECRET_KEY=qa-stand HOME=/home/openclaw \
  setsid /home/openclaw/venvs/wiki/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8080 --log-level warning </dev/null > /tmp/qa-r8-app.log 2>&1 &
```

- `env -i` ОБЯЗАТЕЛЕН: без него PYTHONPATH окружения тянет hermes-python 3.14 и
  pydantic/fastapi импортируются из чужого venv (ModuleNotFoundError / не та версия).
- Схему создает первый uvicorn-старт; семя — conftest-хелпером или руками
  (bcrypt owner/wife + категории «Дом/Работа/Личное», INSERT OR IGNORE).
- Миграция gallery — отдельная, идемпотентная:
  `env -i … SECRET_KEY=… python -m app.migrate_gallery` (без нее web-тесты галереи
  падают `no such table: images` на setup).

## 2. nginx :18443 (HTTP, не TLS)

Исторические прогоны идут по **HTTP** — Secure-кука на 127.0.0.1 сохраняется
(trustworthy origin), а self-signed TLS валит Playwright `ERR_CERT_AUTHORITY_INVALID`.
Конфиг (обязательные куски, каждый = день отладки):

```nginx
worker_processes 1;
pid /tmp/qa-stand/nginx.pid;
error_log /tmp/qa-stand/error.log warn;
events { worker_connections 256; }
http {
    include /etc/nginx/mime.types;          # без этого .js отдается не-JS MIME,
    default_type application/octet-stream;  # module scripts не грузятся, 0 карточек
    client_body_temp_path /tmp/qa-stand/body;  # /var/lib/nginx/body не наша —
    proxy_temp_path /tmp/qa-stand/proxy;       # POST multipart дает 500
    server {
        listen 18443;
        location /static/ { alias <repo>/frontend/static/; expires 7d; }
        location /api/images  { proxy_pass http://127.0.0.1:8389; }
        location ^~ /api/images/ { proxy_pass http://127.0.0.1:8389; }
        location /images/  { alias /tmp/qa-stand/images-vol/; expires 7d; }
        location /         { proxy_pass http://127.0.0.1:8080; }
    }
}
```

Запуск: `setsid nginx -c /tmp/qa-stand/nginx.conf …`; гашение:
`nginx -c /tmp/qa-stand/nginx.conf -s stop`. Диагностика ошибок стенда —
`/tmp/qa-stand/error.log`, не тест-лог.

## 3. images-сервис (:8389 — НЕ трогать прод 8377–8379)

```bash
cd <repo>/services/images
setsid env -i HOME=/home/openclaw PYTHONPATH=<repo>/services/images \
  EKOTOV_WIKI_DB_PATH=/tmp/qa-r8/verify/app.db EKOTOV_WIKI_IMAGES_DIR=/tmp/qa-stand/images-vol \
  SECRET_KEY=qa-stand /home/openclaw/venvs/wiki/bin/python -m uvicorn app.main:app \
  --app-dir <repo>/services/images --host 127.0.0.1 --port 8389 --log-level warning …
```

- env-переменная именно `EKOTOV_WIKI_DB_PATH` (не DB_PATH) — иначе
  `unable to open database file` на каждый запрос.
- Порт 8389, потому что 8377–8379 на host-network — прод-контейнеры uid 10001
  (kill → Operation not permitted; это маркер контейнера, не баг).

## 4. Прогоны на стенде

```bash
cd <repo> && env -u DB_PATH EKOTOV_WIKI_BASE_URL=http://127.0.0.1:18443 \
  EKOTOV_WIKI_DB_PATH=/tmp/qa-r8/verify/app.db EKOTOV_WIKI_IMAGES_DIR=/tmp/qa-r8/verify/images \
  EKOTOV_WIKI_AVATARS_DIR=/tmp/qa-r8/verify/avatars PYTHONPATH=<repo> \
  /home/openclaw/venvs/wiki/bin/python -m pytest tests/web/<файл> -q --tb=line
```

- `PYTHONPATH=<repo>` нужен тестам с `from tests.web.conftest import …` (иначе
  collection error `No module named 'tests.web'`). То же правило для uvicorn и
  любых python-запусков через subprocess-обертки: hermes-оболочка подмешивает
  свой PYTHONPATH 3.14 — если модуль резолвится из чужого venv, запускай через
  `env -i` (чистое окружение), а не `env -u` точечно.
- Тесты с внешним BASE_URL + DB_PATH не skip'аются, а требуют чистую БД: хвосты
  QAGAL-фикстур прошлого прогона дают лишние карточки (11 != 10). Чистить БД до
  прогона, не после. Мусорные записи, попавшие в стенд-БД руками (проверка API),
  удалять прямым sqlite DELETE по связанным таблицам (FK-порядок: дочерние
  image_tags/reactions/comments → images) — DELETE по HTTP может быть не
  реализован (405).
- CURL-проверка логина — `POST /api/auth/login` (не /api/login; 401 на неверном
  пути мимикрирует под битый seed).
- Автостенд conftest ломается о hermes-PYTHONPATH так же, как ручные запуски:
  symptom «Тест-стенд не готов за 60s (connection refused)» на свободном порту.
  Гасить точечным `env -u PYTHONPATH` НЕ всегда достаточно (дробные -u оставляют
  прочие отравленные переменные) — для внешне-похожих сбоев автостенда гоняй
  pytest с `env -u DB_PATH -u EKOTOV_WIKI_BASE_URL -u PYTHONPATH` (все три
  минуса вместе).
- Зомби-uvicorn от убитого сабагента (ss показывает :8378/:8379 LISTEN, процессы
  без родителя) краснят чужие прогоны — гаси `pkill -f 'port 8378'`-паттерном
  перед стартом своего стенда.
- Флейк в новом e2e-тесте (1 failed / 2 passed на одном коммите) с
  `getComputedStyle(null)`/`TypeError: parameter 1 is not of type 'Element'` —
  ассерт выполняется до завершения асинхронного GET-рендера карточки. Харнесс,
  не продукт: перед evaluate жди появления корневого узла рендера
  (`expect(locator('.attr-grid'))`-класс), потом снимай styles.

## Альтернатива: автостенд

Если стенд не нужен как долгоживущий — conftest автостенд (`env -u DB_PATH -u
EKOTOV_WIKI_BASE_URL`) поднимает все сам; после влития фикса search-семейства в
conftest он покрывает и suggestions. Внешний стенд — только для тестов, жестко
требующих BASE_URL+DB_PATH (QAGAL-teardown через БД).

## CPU-конкуренция при параллельных прогонах

Прогон web-сьютов = pytest + playwright-node + до 8 chrome-headless; на слабом
хосте это насыщает CPU и роняет и прогоны, и родительскую сессию (stall →
dropped). Пока сабагент гоняет тесты: свои uvicorn-стенды понизить `renice +10
-p <pid>` (свои — только openclaw-процессы; «Operation not permitted» на kill —
признак прод-контейнера, не трогать); сабагентам в ТЗ — дробить прогоны по
файлу и длинные гонять terminal background.
