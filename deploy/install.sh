#!/usr/bin/env bash
# Установка бота на чистый сервер Ubuntu (например, бесплатный Google Cloud e2-micro).
#
# Запуск одной командой в консоли сервера:
#   curl -fsSL https://raw.githubusercontent.com/sezimai0088-maker/sezimwork-1/main/deploy/install.sh | bash
#
# Скрипт можно запускать повторно: он обновит код и перезапустит бота, не трогая .env и базу.

set -euo pipefail

REPO_URL="https://github.com/sezimai0088-maker/sezimwork-1.git"
APP_DIR="${APP_DIR:-$HOME/sezimwork-1}"

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m!!  %s\033[0m\n' "$*"; }

ask() {
  # ask "Вопрос" "значение по умолчанию" → ответ (читаем с клавиатуры, даже если скрипт пришёл через curl | bash)
  local question="$1" default="${2:-}" answer
  if [ -n "$default" ]; then
    read -r -p "$question [$default]: " answer < /dev/tty || true
  else
    read -r -p "$question: " answer < /dev/tty || true
  fi
  printf '%s' "${answer:-$default}"
}

set_env() {
  # set_env КЛЮЧ ЗНАЧЕНИЕ — заменить строку КЛЮЧ=... в .env (или добавить)
  local key="$1" value="$2" file="$APP_DIR/.env"
  local escaped
  escaped=$(printf '%s' "$value" | sed -e 's/[\/&|]/\\&/g')
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

# ---------- 1. Подкачка памяти (на e2-micro всего 1 ГБ — без неё сборка может упасть) ----------
if ! swapon --show | grep -q .; then
  say "Добавляю 1 ГБ файла подкачки"
  sudo fallocate -l 1G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# ---------- 2. Docker и git ----------
if ! command -v docker >/dev/null 2>&1; then
  say "Устанавливаю Docker и git (1–3 минуты)"
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker.io git >/dev/null
  sudo apt-get install -y -qq docker-compose-v2 >/dev/null 2>&1 \
    || sudo apt-get install -y -qq docker-compose-plugin >/dev/null 2>&1 \
    || true
  sudo systemctl enable --now docker >/dev/null
fi
if ! sudo docker compose version >/dev/null 2>&1; then
  warn "Не найден docker compose. Попробуйте: sudo apt-get install -y docker-compose-v2"
  exit 1
fi

# ---------- 3. Код бота ----------
if [ -d "$APP_DIR/.git" ]; then
  say "Обновляю код"
  git -C "$APP_DIR" pull --ff-only
else
  say "Скачиваю код"
  git clone --depth 1 "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
mkdir -p data

# ---------- 4. Настройки ----------
if [ ! -f .env ]; then
  say "Первая настройка. Ответьте на несколько вопросов."
  cp .env.example .env
  echo "Токен вставляется правой кнопкой мыши или Ctrl+Shift+V. Его не видно на экране — это нормально."
  token=""
  while [ -z "$token" ]; do
    read -r -s -p "Токен бота от @BotFather: " token < /dev/tty || true
    echo
  done
  set_env BOT_TOKEN "$token"
  set_env OWNER_PHONE "$(ask 'Номер телефона владельца (например +996555123456)')"
  echo "Координаты офиса: в 2ГИС или Google Картах зажмите палец на здании и скопируйте два числа."
  set_env OFFICE_LAT "$(ask 'Широта офиса (первое число)' "$(grep '^OFFICE_LAT=' .env | cut -d= -f2)")"
  set_env OFFICE_LON "$(ask 'Долгота офиса (второе число)' "$(grep '^OFFICE_LON=' .env | cut -d= -f2)")"
  set_env WORK_START "$(ask 'Начало рабочего дня' '09:00')"
  set_env WORK_END "$(ask 'Конец рабочего дня' '18:00')"
  chmod 600 .env
else
  say "Файл настроек .env уже есть — оставляю как есть"
fi

# ---------- 5. Запуск ----------
say "Собираю и запускаю бота (первый раз 2–5 минут)"
sudo docker compose up -d --build

say "Проверяю запуск"
for _ in $(seq 1 30); do
  if sudo docker compose logs bot 2>/dev/null | grep -q "Бот запущен"; then
    say "Готово! Бот работает круглосуточно и сам перезапускается после перезагрузки сервера."
    echo "Посмотреть журнал:   cd $APP_DIR && sudo docker compose logs -f --tail 50"
    echo "Обновить бота:       bash $APP_DIR/deploy/update.sh"
    echo "Изменить настройки:  nano $APP_DIR/.env  затем  bash $APP_DIR/deploy/update.sh"
    exit 0
  fi
  sleep 3
done
warn "Бот пока не написал «Бот запущен». Последние строки журнала:"
sudo docker compose logs --tail 40 bot
exit 1
