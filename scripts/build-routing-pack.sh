#!/usr/bin/env bash
# 构建区域路网包（M4 路书）：OSM PBF → JSON 包，放数据根 routing/pack.json。
# 用法（构建时可选在线，先自取 OSM PBF extract，例如 Geofabrik / BBBike）：
#   ./scripts/build-routing-pack.sh --pbf /path/to/region.osm.pbf [--out backend/routing/pack.json]
#
# pyrosm 是构建时依赖，第一次运行会自动装进 backend/.pylibs。
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
PBF=""
OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pbf) PBF="${2:-}"; shift 2 ;;
    --out) OUT="${2:-}"; shift 2 ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

if [[ -z "$PBF" ]]; then
  echo "需要 --pbf 指定 OSM PBF extract 路径。"
  echo "数据源（免费无账号）：Geofabrik download.geofabrik.de / BBBike extract.bbbike.org / Overpass"
  exit 1
fi
if [[ ! -f "$PBF" ]]; then
  echo "PBF 文件不存在: $PBF"
  exit 1
fi
OUT="${OUT:-routing/pack.json}"

if [ ! -d backend/.pylibs ]; then
  echo "缺少 backend/.pylibs，先运行 ./scripts/install.sh。"
  exit 1
fi

echo "==> 安装构建时依赖（pyrosm）"
"$PY" -m pip install --disable-pip-version-check --target backend/.pylibs -r backend/requirements-build.txt

echo "==> 构建区域路网包"
( cd backend && PYTHONPATH=.:.pylibs "$PY" -m travel.packbuild --pbf "$PBF" --out "$OUT" )

echo "完成。把包放到数据根 routing/pack.json 后，路书重算即用该路网。"