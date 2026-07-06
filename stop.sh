#!/bin/bash
# 答案採点支援アプリを停止する。
set -e
cd "$(dirname "$0")"
docker compose down
echo "停止しました。"
