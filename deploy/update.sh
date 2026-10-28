#!/usr/bin/env bash
# Обновить бота на сервере до последней версии из GitHub и перезапустить.
#   bash ~/sezimwork-1/deploy/update.sh
# Настройки (.env) и база (data/) не меняются.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Скачиваю обновления"
git pull --ff-only
echo "==> Пересобираю и перезапускаю"
sudo docker compose up -d --build
sleep 5
sudo docker compose logs --tail 15 bot
echo "==> Готово"
