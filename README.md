# 旅行足迹 Travel Footprints

本地优先的个人旅行足迹软件：记录去过的城市、景点、店铺、美食、交通和爬山轨迹，用地图点亮 + 时间轴 + 照片/视频回顾。

权威设计见 [DESIGN.md](DESIGN.md)，技术选型见 [tech-comparison-report.md](tech-comparison-report.md)，决策记录见 `docs/adr/`。

## 形态与原则

- 本机服务 + 浏览器：后端是本机启动的 FastAPI 服务，同一局域网内的手机浏览器也可查看看板、上传媒体。
- **无账号、无登录、无外发数据**：离线底图、零遥测；在线地图/地理编码/LLM 都默认关闭，未与用户确认不引入。
- 数据自包含：所有文件都在数据根目录（默认 `backend/travel_data/`），迁移 = 拷贝整个目录，或使用导出 zip 全量恢复。

## 快速开始（Linux）

环境：Python 3.10+、Node 18+、ffmpeg（可选，用于视频封面帧；缺失时视频缩略图自动跳过）。

```bash
# 1) 后端依赖（装入仓库内 .pylibs/，不污染系统环境）
python3 -m pip install --target .pylibs -r backend/requirements.txt

# 2) 前端依赖与本地 vendor（离线运行需要）
cd frontend
npm install
mkdir -p vendor/maplibre
cp node_modules/vue/dist/vue.global.prod.js vendor/
cp node_modules/maplibre-gl/dist/maplibre-gl.mjs vendor/maplibre/
cp node_modules/maplibre-gl/dist/maplibre-gl-shared.mjs vendor/maplibre/
cp node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs vendor/maplibre/
cp node_modules/maplibre-gl/dist/maplibre-gl.css vendor/maplibre/
cd ..

# 3) 启动
cd backend
PYTHONPATH=.:../.pylibs python3 -m uvicorn travel.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000>。手机访问：同一局域网内换成电脑的局域网 IP（例如 `--host 0.0.0.0`）。数据根目录可用环境变量覆盖：`TRAVEL_DATA_ROOT=/path/to/data`。

## 测试

```bash
PYTHONPATH=.:.pylibs python3 -m pytest backend/tests -q
PYTHONPATH=.:.pylibs python3 -m mypy backend/travel
```

## M1 已实现

- 数据模型：Trip / City / Place / Visit（含名称快照）/ TransportLeg / Trail / StoredFile / Media，SQLite schema 带版本号。
- 点亮地图：城市与地点按到访点亮（本地离线底图样式，仅背景，无瓦片请求）。
- 看板：统计卡、按城市/类型/年份/关键词/是否带媒体过滤，时间轴视图。
- 媒体：照片/视频原样存储 + SHA-256 去重 + 首次访问懒生成缩略图（视频封面帧需 ffmpeg），缩略图不导出。
- 备份：导出 zip（数据库 + 原媒体 + 清单），仅支持整体恢复。
- 地点/到访/媒体的增删查改，店铺可标注坐标或留空。

计划中的增量里程碑（文本导入解析、GPX、离线瓦片包等）见 [DESIGN.md](DESIGN.md) 第 9 节。
