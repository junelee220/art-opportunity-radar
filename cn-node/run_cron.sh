#!/usr/bin/env bash
# 国内节点定时任务:拉最新代码 → 跑 cn 源管道 → 提交数据回 GitHub
set -uo pipefail

REPO_DIR="$HOME/art-opportunity-radar"
LOG="$HOME/radar-cn.log"

ts() { date "+%Y-%m-%d %H:%M:%S"; }

{
  echo "[$(ts)] 开始运行"

  if ! command -v python3 >/dev/null 2>&1; then
    echo "[$(ts)] 错误:未找到 python3"
    exit 0
  fi

  cd "$REPO_DIR" || { echo "[$(ts)] 错误:仓库目录不存在 $REPO_DIR"; exit 0; }

  # 环境变量放在 ~/radar-env(TELEGRAM_BOT_TOKEN 等,含可选的 TELEGRAM_PROXY)
  [ -f "$HOME/radar-env" ] && . "$HOME/radar-env"

  git pull --rebase --quiet || echo "[$(ts)] 警告:git pull 失败,使用本地版本"

  if python3 src/main.py --region cn; then
    if ! git diff --quiet data/ 2>/dev/null; then
      git add data/
      git commit -m "cn-radar: $(date '+%Y-%m-%d %H:%M')" --quiet
      git push --quiet || echo "[$(ts)] 警告:git push 失败,数据保留在本地,下次重试"
    else
      echo "[$(ts)] 无新数据"
    fi
  else
    echo "[$(ts)] 管道运行失败"
  fi
} >> "$LOG" 2>&1

exit 0
