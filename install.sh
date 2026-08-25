#!/usr/bin/env bash
# =====================================================================
#  heart 一键配置脚本 —— 把一个「有心跳的角色」装配起来
#
#  用法：
#    ./install.sh                         交互式问答配置并启动
#    ./install.sh --check                 只校验两个端点连通性
#    ./install.sh --no-start              只生成 .env，不启动
#    ./install.sh --persona ./xiaolu \
#        --think-url https://api.xxx/v1 --think-key sk-xxx \
#        --executor hermes \
#        --executor-url http://127.0.0.1:8642 --executor-key xxx
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

PERSONA="${PERSONA:-}"
THINK_URL="${THINK_URL:-}"
THINK_KEY="${THINK_KEY:-}"
EXECUTOR="${EXECUTOR:-hermes}"
EXECUTOR_URL="${EXECUTOR_URL:-}"
EXECUTOR_KEY="${EXECUTOR_KEY:-}"
DO_START=1
DO_CHECK=0

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --persona|-p)     PERSONA="$2";       shift 2 ;;
    --think-url)      THINK_URL="$2";     shift 2 ;;
    --think-key)      THINK_KEY="$2";     shift 2 ;;
    --executor)       EXECUTOR="$2";      shift 2 ;;
    --executor-url)   EXECUTOR_URL="$2";  shift 2 ;;
    --executor-key)   EXECUTOR_KEY="$2";  shift 2 ;;
    --no-start)       DO_START=0;         shift ;;
    --check)          DO_CHECK=1;         shift ;;
    --help|-h)        usage ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# 已有 .env 里的值作为默认（可被传参覆盖）
if [[ -f .env ]]; then set -a; . ./.env; set +a; fi

# 交互式补齐缺的参数
prompt() { # $1=提示  $2=当前值
  local ans=""
  if [[ -n "${2:-}" ]]; then
    read -r -p "$1 [当前: $2]（回车保留）: " ans
  else
    read -r -p "$1: " ans
  fi
  echo "$ans"
}

if [[ -z "$PERSONA" ]]; then
  if [[ -f AGENTS.md ]]; then
    PERSONA="$PWD"
  else
    ans=$(prompt "角色文件夹路径（含 AGENTS.md）" ""); PERSONA="$ans"
  fi
fi

if [[ -z "$THINK_URL" ]]; then
  ans=$(prompt "「想」LLM 端点 HEART_BASE_URL" "$THINK_URL"); [[ -n "$ans" ]] && THINK_URL="$ans"
fi
if [[ -z "$THINK_KEY" ]]; then
  ans=$(prompt "「想」LLM 密钥 HEART_API_KEY" ""); [[ -n "$ans" ]] && THINK_KEY="$ans"
fi

if [[ "$EXECUTOR" == "opencode" ]]; then
  EXECUTOR_URL=""; EXECUTOR_KEY=""
  echo "（执行层 = opencode，无需 Hermes 端点；请先装 opencode CLI）"
else
  EXECUTOR="hermes"
  if [[ -z "$EXECUTOR_URL" ]]; then
    ans=$(prompt "执行层 Hermes API Server 端点 HERMES_BASE_URL" "$EXECUTOR_URL"); [[ -n "$ans" ]] && EXECUTOR_URL="$ans"
  fi
  if [[ -z "$EXECUTOR_KEY" ]]; then
    ans=$(prompt "执行层密钥 HERMES_API_KEY" ""); [[ -n "$ans" ]] && EXECUTOR_KEY="$ans"
  fi
fi

# 生成 .env
cat > .env <<EOF
# heart 配置（由 install.sh 生成）—— .env 已被 .gitignore 忽略
HEART_BASE_URL="$THINK_URL"
HEART_API_KEY="$THINK_KEY"
HERMES_BASE_URL="$EXECUTOR_URL"
HERMES_API_KEY="$EXECUTOR_KEY"
EOF
echo "✓ 已生成 .env（执行层 executor=$EXECUTOR）"

# 校验连通性（OpenAI 协议探活 /models 或 /v1/models）
check_url() {
  local url="$1" name="$2" base="${1%/}" code=""
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$base/models" 2>/dev/null || echo "000")
  [[ "$code" == "000" ]] && code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$base/v1/models" 2>/dev/null || echo "000")
  if [[ "$code" == "000" ]]; then
    echo "✗ $name 不可达: $base"
  elif [[ "$code" == "401" || "$code" == "403" ]]; then
    echo "✓ $name 可达（HTTP $code，端点对，key 需正确）: $base"
  else
    echo "✓ $name 可达（HTTP $code）: $base"
  fi
}

if [[ -n "$THINK_URL" ]];   then check_url "$THINK_URL"   "想 LLM"; fi
if [[ -n "$EXECUTOR_URL" ]]; then check_url "$EXECUTOR_URL" "执行层"; fi

[[ "$DO_CHECK" == "1" ]] && { echo "（--check 模式，仅校验，不启动）"; exit 0; }

if [[ "$DO_START" == "1" ]]; then
  echo ""
  echo "❤️  启动 heart：思维服务(mind) + 执行服务(hermes)"
  exec ./start.sh "${PERSONA:-.}"
else
  echo "（--no-start，未启动）"
  echo "手动启动：./start.sh ${PERSONA:-.}"
fi
