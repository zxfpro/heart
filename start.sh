#!/usr/bin/env bash
# =====================================================================
#  heart 启动脚本：一次性拉起「思维服务」+「执行服务」两个进程
#  用法：./start.sh [事实文件夹路径]   （默认当前目录）
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

# 加载 .env（若存在）
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

# 优先用项目 venv 里的 python（否则用系统 python3）
PY="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then
  PY=".venv/bin/python"
fi

FOLDER="${1:-$PWD}"
mkdir -p "$FOLDER"

echo "❤️  heart 启动"
echo "   事实文件夹 : $FOLDER"
echo "   思维服务   : mind.py    （潜意识冒想法 + 判别 + 蒸馏）"
echo "   执行服务   : hermes.py  （处理 PASS 的想法）"
echo

"$PY" mind.py "$FOLDER" &
MIND_PID=$!
"$PY" hermes.py "$FOLDER" &
HERMES_PID=$!

trap 'kill "$MIND_PID" "$HERMES_PID" 2>/dev/null || true' EXIT INT TERM
wait
