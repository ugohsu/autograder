#!/bin/bash
# 答案採点支援アプリを起動する。Mac (Terminal) でも、Windows の WSL2 (Ubuntu 等) でも同じスクリプトで動く。
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env が無かったので .env.example からコピーしました（必要なら中身を編集してください）。"
fi

mkdir -p ./data

docker compose up -d --build

echo "起動しました。ブラウザで以下のURLを開いてください:"
echo "  http://localhost:8000"

# 可能であれば自動でブラウザを開く（失敗しても無視してよい）
( command -v open >/dev/null && open http://localhost:8000 ) || \
( command -v xdg-open >/dev/null && xdg-open http://localhost:8000 ) || \
( command -v wslview >/dev/null && wslview http://localhost:8000 ) || true
