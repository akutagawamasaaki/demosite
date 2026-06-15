#!/bin/bash
# ダブルクリックでローカルサーバを起動し、ブラウザを開く（Mac用）
cd "$(dirname "$0")"

# Python3 の確認
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3 が見つかりません。"
  echo "ターミナルで  xcode-select --install  を実行してインストールしてから、もう一度このファイルを開いてください。"
  echo ""
  read -n 1 -s -r -p "何かキーを押すと閉じます…"
  exit 1
fi

URL="http://localhost:8765/"
echo "ゲーム最新アップデート確認ツールを起動します: $URL"
echo "（このウィンドウを閉じる／Ctrl+C で停止します）"
( sleep 1.5; open "$URL" ) &
python3 server.py
