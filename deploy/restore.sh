#!/usr/bin/env bash
# Восстановить базу из ночного бэкапа, который бот присылает владельцу.
#   1. Загрузите файл backup_ГГГГ-ММ-ДД.db на сервер (в консоли SSH: значок ⚙ → Upload file).
#   2. bash ~/sezimwork-1/deploy/restore.sh ~/backup_2026-11-05.db
# Текущая база сохраняется рядом с именем bot.db.before-restore-<дата>.

set -euo pipefail
BACKUP="${1:-}"
if [ -z "$BACKUP" ] || [ ! -f "$BACKUP" ]; then
  echo "Укажите файл бэкапа: bash deploy/restore.sh ~/backup_2026-11-05.db"
  exit 1
fi
cd "$(dirname "$0")/.."

echo "==> Останавливаю бота"
sudo docker compose stop bot
if [ -f data/bot.db ]; then
  cp data/bot.db "data/bot.db.before-restore-$(date +%Y%m%d-%H%M%S)"
fi
rm -f data/bot.db-wal data/bot.db-shm
cp "$BACKUP" data/bot.db
echo "==> Запускаю бота"
sudo docker compose start bot
sleep 5
sudo docker compose logs --tail 10 bot
echo "==> База восстановлена из $BACKUP"
