#!/usr/bin/env bash
# 一键安装旅行足迹全部依赖（Linux / macOS）
# 用法: ./scripts/install.sh
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少 $1，请先安装后重试。"
    exit 1
  fi
}

echo "==> 检查 Python"
require_cmd "$PY"
PY_VERSION="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "    Python $PY_VERSION"
MAJOR="$(printf '%s' "$PY_VERSION" | cut -d. -f1)"
MINOR="$(printf '%s' "$PY_VERSION" | cut -d. -f2)"
if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]; }; then
  echo "    需要 Python 3.10+，当前是 $PY_VERSION。"
  echo "    macOS: brew install python@3.12"
  echo "    Ubuntu 20.04: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12"
  echo "    装好后用 PYTHON=python3.12 ./scripts/install.sh 重新运行。"
  exit 1
fi

echo "==> 安装后端依赖到 .pylibs/"
"$PY" -m pip install --disable-pip-version-check --target .pylibs -r backend/requirements.txt

if command -v ffmpeg >/dev/null 2>&1; then
  echo "==> ffmpeg 已安装（视频封面帧可用）"
else
  echo "==> 未检测到 ffmpeg（可选）：视频缩略图会跳过。"
  echo "    macOS: brew install ffmpeg    Linux: apt install ffmpeg"
fi

echo "==> 安装前端依赖"
require_cmd npm
cd frontend
npm install --no-audit --no-fund
mkdir -p vendor/maplibre
cp -f node_modules/vue/dist/vue.global.prod.js vendor/
cp -f node_modules/maplibre-gl/dist/maplibre-gl.mjs vendor/maplibre/
cp -f node_modules/maplibre-gl/dist/maplibre-gl-shared.mjs vendor/maplibre/
cp -f node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs vendor/maplibre/
cp -f node_modules/maplibre-gl/dist/maplibre-gl.css vendor/maplibre/
cd ..

echo
echo "安装完成。启动："
echo "  ./scripts/run.sh"
echo "然后浏览器打开 http://127.0.0.1:8000"
