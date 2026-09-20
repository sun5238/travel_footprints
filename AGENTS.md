# AGENTS.md

本仓库是**本地优先的个人旅行足迹软件**的设计与实现。权威设计见 [DESIGN.md](DESIGN.md)，技术调研见 [tech-comparison-report.md](tech-comparison-report.md) 与 [research-report.md](research-report.md)。

## 项目铁律（违反即设计偏差，改动前先看 DESIGN.md）

1. **无账号、无登录、无外发数据**。任何网络请求（在线地图瓦片、地理编码、LLM/API）默认禁止；如需引入，必须做成显式开关且默认关闭，并在 DESIGN.md 登记。
2. **数据自包含**：所有路径相对，禁止硬编码绝对路径；换机/迁移 = 拷贝数据根目录。
3. **schema 版本化**：SQLite 变更必须带迁移，不得静默改表。
4. **解析器风格**：规则 + 学习词典驱动，默认不用 LLM；解析结果先展示后入库；每次人工校正必须写入标注库（`correction`）并学习新词（`dictionary`）；不得静默修改或丢弃无法解析的原文。
5. **本地优先实现**：默认使用离线瓦片；导入沿“文本骨架 -> 媒体分组挂靠”两段式；接外部服务是例外而非默认。

## 技术栈

- 后端：Python FastAPI + SQLite（SQLAlchemy）。
- 前端：Vue 3 + MapLibre GL JS。
- 媒体：Pillow（缩略图）、ffmpeg（视频封面帧）。

## 目录约定

- 数据根目录结构见 DESIGN.md 第 3 节；代码中所有数据路径必须源自配置的数据根，禁止直接拼接绝对路径。
- 测试：后端 pytest 放 `tests/backend/`，前端 node:test 放 `tests/frontend/`；共享种子数据见 `tests/backend/seed.py`（测试自造临时 data_root，不依赖真实数据）。

## 测试范围界限（谁动谁跑，防过度测试）

入口：`./scripts/test.sh [backend|frontend|all]`。**commit 前必须通过本改动对应的测试**：

| 改动范围 | 必须通过的测试 |
|---|---|
| 后端 store / API / 数据模型 / schema 迁移 | `backend` 套件全绿；涉数据模型同步更新 DESIGN.md |
| 前端纯逻辑（frontend/logic.js 内函数） | `frontend` 套件（node --test）全绿 |
| 前端接口字段消费（app.js 增减读取字段） | `tests/backend/test_frontend_fields.py` 全绿 |
| 媒体 / 备份相关 | 后端 tests 全绿 |
| 仅文档 / 脚本，无行为改动 | 不强制，但 commit 说明须注明"无行为改动" |

- 测试数据：全部由 `build_seed` 在临时目录自造（64 条媒体、3 到访城市等），不入库、不碰真实数据；`.pylibs` 缺失时先跑 `./scripts/install.sh`。

## 开发约定

- 代码标识符用英文；注释/文档可用中文。
- 每完成一个模块补最小测试（解析、迁移、导入流程为重点）。
- 改动涉及数据模型时同步更新 DESIGN.md。
- 不要在没有与用户确认的情况下引入新依赖或外网服务。
