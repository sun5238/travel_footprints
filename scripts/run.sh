#!/usr/bin/env bash
# 启动旅行足迹本地服务（默认 127.0.0.1:8000）
# 局域网访问: HOST=0.0.0.0 ./scripts/run.sh
set -euo pipefail

cd "$(dirname "$0")/../backend"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

exec env PYTHONPATH=.:../.pylibs python3 -m uvicorn travel.main:app --host "$HOST" --port "$PORT"
