#!/usr/bin/env bash
# 运行旅行足迹测试套件。
# 用法: ./scripts/test.sh [backend|frontend|all]   （缺省 all）
# 范围说明见 AGENTS.md「测试范围界限」：commit 前须通过本改动对应的套件。
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d backend/.pylibs ]; then
  echo "缺少 backend/.pylibs，请先运行 ./scripts/install.sh 安装依赖。"
  exit 1
fi

run_backend() {
  echo "==> 后端 pytest（tests/backend）"
  ( cd backend && PYTHONPATH=.:.pylibs python3 -m pytest ../tests/backend -q )
}

run_frontend() {
  echo "==> 前端 node --test（tests/frontend）"
  node --test tests/frontend/logic.test.js
}

SCOPE="${1:-all}"

case "$SCOPE" in
  backend) run_backend ;;
  frontend) run_frontend ;;
  all)
    run_backend
    run_frontend
    ;;
  *)
    echo "用法: $0 [backend|frontend|all]"
    exit 2
    ;;
esac

echo "测试通过 ✔"