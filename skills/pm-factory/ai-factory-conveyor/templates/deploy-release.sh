#!/usr/bin/env bash
# ============================================================
# Скелет деплой-скрипта релиза (копировать в ~/deploy-<релиз>.sh и править
# значения в блоке CONFIG). Проверенные на болях правила:
#   - пре-флайт ДО любой мутации;   - бэкап БД — всегда шаг 1;
#   - код: git pull, если прод-каталог — репозиторий, ИНАЧЕ rsync из клона
#     (exclude .git/.env/.venv/__pycache__) + chown служебному юзеру;
#   - `python -m pkg.mod` ТОЛЬКО из cwd родителя пакета (подшелл cd);
#   - всё под `sudo -u <юзер>` (скрипт запускает Заказчик из-под root);
#   - пост-рестарт смоук: health + HTML + JS + CSS через реальный URL.
# ============================================================
set -euo pipefail

# --- CONFIG (править под релиз) -------------------------------------------
APP_DIR="/opt/<приложение>"          # прод-каталог (может НЕ быть git-репо!)
SRC_DIR="/home/<юзер>/<проект>"      # локальный клон на целевом коммите
DB="/var/lib/<приложение>/app.db"
BACKUP_DIR="/var/backups/<приложение>"
BACKUP_FILE="${BACKUP_DIR}/pre-<релиз>-$(date +%F-%H%M).db"
SERVICE="<приложение>"               # systemd-юнит
SVC_USER="<служебный-юзер>"          # владелец кода/БД/venv
BASE_URL="http://127.0.0.1:<порт>"   # реальный URL деплоя
EXPECTED_COMMIT="<short-sha>"

log()  { echo -e "\n==> $*"; }
ok()   { echo "[OK] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }

# --- 0. Пре-флайт: факты ДО мутаций ----------------------------------------
log "0/7 Предусловия"
for tool in rsync sqlite3 curl git systemctl; do
  command -v "$tool" >/dev/null || fail "Нет утилиты: $tool"
done
id "$SVC_USER" >/dev/null 2>&1 || fail "Нет пользователя $SVC_USER"
[ -d "$APP_DIR" ] && [ -f "$DB" ] && [ -d "$SRC_DIR/.git" ] \
  || fail "Не хватает APP_DIR/SRC_DIR/DB"
[ -x "$APP_DIR/<пакет>/.venv/bin/python" ] || fail "Нет venv в прод-каталоге"
[ "$(git -C "$SRC_DIR" rev-parse --short HEAD)" = "$EXPECTED_COMMIT" ] \
  || fail "Клон не на целевом коммите $EXPECTED_COMMIT"
mkdir -p "$BACKUP_DIR" && chown "$SVC_USER:$SVC_USER" "$BACKUP_DIR"
ok "Предусловия"

# --- 1. Бэкап БД (всегда первым) -------------------------------------------
log "1/7 Бэкап БД → $BACKUP_FILE"
sudo -u "$SVC_USER" sqlite3 "$DB" ".backup ${BACKUP_FILE}" || fail "Бэкап не создан"
[ -s "$BACKUP_FILE" ] || fail "Бэкап пуст"
ok "Бэкап $(du -h "$BACKUP_FILE" | cut -f1)"

# --- 2. Код: pull ИЛИ rsync по факту наличия .git ---------------------------
log "2/7 Код"
if sudo git -C "$APP_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  sudo -u "$SVC_USER" git -C "$APP_DIR" pull --ff-only origin main
else
  echo "   Прод-каталог не git-репозиторий — rsync из клона"
  sudo rsync -a --delete \
    --exclude '.git/' --exclude '.env' --exclude '.venv/' \
    --exclude '__pycache__/' --exclude '*.pyc' --exclude '.pytest_cache/' \
    "$SRC_DIR/" "$APP_DIR/"
  sudo chown -R "$SVC_USER:$SVC_USER" "$APP_DIR"
fi
[ -f "$APP_DIR/.env" ] || fail ".env пропал — восстановить вручную"
ok "Код синхронизирован"

# --- 3. Зависимости (идемпотентно, всегда) ----------------------------------
log "3/7 Зависимости"
sudo -u "$SVC_USER" "$APP_DIR/<пакет>/.venv/bin/pip" install -q \
  -r "$APP_DIR/<пакет>/requirements.txt" || fail "pip install"
ok "Зависимости"

# --- 4. Схема БД (идемпотентно; пропуск если уже есть) ----------------------
log "4/7 Схема"
# (cd <родитель пакета> && sudo -u $SVC_USER .venv/bin/python -m pkg.db)
# ОБЯЗАТЕЛЬНО cwd родителя пакета — иначе ModuleNotFoundError.
ok "Схема"

# --- 5. Миграции данных ------------------------------------------------------
log "5/7 Миграция"
# Перед повтором на непустых данных — спросить подтверждение (read -p).
# (cd <родитель пакета> && sudo -u $SVC_USER .venv/bin/python -m pkg.migrate)
ok "Миграция"

# --- 6. Рестарт ---------------------------------------------------------------
log "6/7 Рестарт $SERVICE"
sudo systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" || fail "Сервис не поднялся: journalctl -u $SERVICE -n 50"
ok "Сервис активен"

# --- 7. Пост-деплойный смоук (НЕ сокращать!) ----------------------------------
log "7/7 Смоук"
curl -sf --max-time 5 "$BASE_URL/api/health" >/dev/null || fail "health"
for asset in "/<страница>.html" "/static/<app>.js" "/static/<app>.css"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BASE_URL$asset")
  [ "$code" = "200" ] || fail "Статика/страница $asset → $code"
done
ok "health + страница + JS + CSS — все 200"

log "ДЕПЛОЙ ЗАВЕРШЕН. Бэкап: $BACKUP_FILE"
# Команды отката печатать в финале: stop → restore БД из бэкапа → код из
# снапшота (rsync --delete из ~/snapshot-<предыдущий-релиз>/) → start.
