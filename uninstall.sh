#!/bin/bash
# 答案採点支援アプリを完全にアンインストールする（コンテナ・イメージを削除）。
# ./stop.sh は「一時停止」（次回すぐ再開できるようイメージ・データを残す）だが、
# こちらはDockerの痕跡を残さず消し去りたい場合に使う。
set -e
cd "$(dirname "$0")"

docker compose down --rmi all
echo "コンテナとDockerイメージを削除しました。"
echo

read -p "採点データ（./data の中身）も削除しますか？元に戻せません。 [y/N]: " confirm
if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
  # ./data ディレクトリ自体は残し、中身だけ削除する（.gitignore 等の管理ファイルは無視して残る）
  rm -rf ./data/*
  echo "./data の中身を削除しました。"
else
  echo "./data は残しています（次回インストール時にも読み込まれます）。"
fi
