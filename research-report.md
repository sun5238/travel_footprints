# 开源"本地旅行足迹"项目调研报告

> 调研日期：2026-09-08  
> 数据来源：GitHub API 实时搜索（已实际访问）、项目 README  
> 调研范围：旅行日记/地理日记类、GPS 轨迹/户外记录类、足迹点亮地图类、照片地理化类，共检索约 40+ 个仓库，筛选出 16 个候选项目

---

## 一、需求清单回顾

| 编号 | 需求 |
|------|------|
| R1 | 全局地图上"点亮"去过的城市 |
| R2 | 城市内具体 POI 可在地图上点亮，且可直接查看该地点的大量照片 |
| R3 | 小吃店等地点可标记、关联照片、记录个人评价文字 |
| R4 | 记录两地点之间的交通方式描述（如"从重庆坐高铁到成都"） |
| R5 | 记录爬山轨迹（开始/结束时间、轨迹线、海拔等） |
| R6 | 文本导入：把日记/流水账文本导入成结构化足迹 |
| R7 | 本地优先（数据存本地，不依赖云账号） |

---

## 二、候选项目清单

### 2.1 自托管旅行时间线/位置历史类（综合型，最相关）

#### 1. Dawarich
| 字段 | 内容 |
|------|------|
| **名称** | Dawarich |
| **仓库** | <https://github.com/Freika/dawarich> |
| **Star** | ~10,300 |
| **语言** | Ruby (Rails 后端) + 前端 |
| **平台** | Web（Docker 自托管）+ iOS/Android 配套 App |
| **许可证** | AGPL-3.0 |
| **最近活跃** | 活跃开发中（2026-09-07 最后一次 push），145 open issues |
| **简介** | 自托管 Google Timeline 替代品。支持实时位置追踪、历史轨迹可视化、旅程创建、照片集成（Immich/Photoprism）、统计洞察（国家/城市/距离）、家庭位置共享。支持导入 Google Takeout / OwnTracks / Strava / GPX / GeoJSON / EXIF。 |

#### 2. GeoPulse
| 字段 | 内容 |
|------|------|
| **名称** | GeoPulse |
| **仓库** | <https://github.com/tess1o/geopulse> |
| **Star** | ~1,400 |
| **语言** | Java (Quarkus 后端) + Vue 3 前端 |
| **平台** | Web（Docker 自托管） |
| **许可证** | BSL-1.1（非标准开源，商业使用有限制） |
| **最近活跃** | 活跃开发中（2026-09-07 最后一次 push），4 open issues |
| **简介** | 隐私优先的 Google Timeline 替代品。自动将 GPS 点转换为停留/出行/间隙检测，支持地图匹配（Valhalla）、Immich/Memos/天气集成、全景街景。轻量级（<100MB RAM）。 |

#### 3. OwnTracks 生态
| 字段 | 内容 |
|------|------|
| **名称** | OwnTracks（Android / Recorder / Frontend） |
| **仓库** | <https://github.com/owntracks/android> (~1,800 stars, Kotlin) / <https://github.com/owntracks/recorder> (~1,200 stars, C) / <https://github.com/owntracks/frontend> (~550 stars, JS) |
| **平台** | Android App + 自托管后端 + Web 前端 |
| **许可证** | 各组件不同（多为 MIT / 宽松许可证） |
| **最近活跃** | 持续维护（2026-09 仍有提交） |
| **简介** | 成熟的开源位置追踪生态。Android App 上报位置 → Recorder 存储 → Frontend 在 Web 地图上展示。纯位置追踪，无照片/评价/交通方式等旅行管理功能。 |

---

### 2.2 GPS 轨迹/户外记录类

#### 4. OpenTracks
| 字段 | 内容 |
|------|------|
| **名称** | OpenTracks |
| **仓库** | <https://github.com/OpenTracksApp/OpenTracks>（已迁移至 Codeberg） |
| **Star** | ~1,400（GitHub 存档） |
| **语言** | Java |
| **平台** | Android App |
| **许可证** | Apache-2.0 |
| **最近活跃** | 持续维护 |
| **简介** | 专注户外运动轨迹记录。记录 GPS 轨迹、速度、海拔、距离等。支持 GPX/KML 导出。纯运动追踪，无旅行管理功能。 |

#### 5. GPXSee
| 字段 | 内容 |
|------|------|
| **名称** | GPXSee |
| **仓库** | <https://github.com/tumic0/GPXSee> |
| **Star** | ~1,200 |
| **语言** | C++ |
| **平台** | 桌面（Windows/macOS/Linux） |
| **许可证** | GPL-3.0 |
| **最近活跃** | 持续维护（2026-09-06） |
| **简介** | GPS 日志文件查看器和分析器。支持 GPX、TCX、KML、FIT 等多种格式。显示轨迹线、海拔剖面图、速度图表。纯查看工具，不支持标记/照片。 |

#### 6. MTL Explorer
| 字段 | 内容 |
|------|------|
| **名称** | MTL Explorer |
| **仓库** | <https://github.com/mindalyze-com/mtl-explorer> |
| **Star** | ~40 |
| **语言** | Java (Spring Boot) + Vue 3 |
| **平台** | Web（Docker 自托管） |
| **许可证** | AGPL-3.0 |
| **最近活跃** | 活跃开发（2026-09-07） |
| **简介** | 自托管 GPS 轨迹浏览器。导入 Garmin/GPX/FIT，地图展示，轨迹统计，3D 回放，路线规划（BRouter）。有照片关联功能。专注户外轨迹，无城市 POI 标记。 |

---

### 2.3 照片地理化类

#### 7. chronoframe
| 字段 | 内容 |
|------|------|
| **名称** | chronoframe |
| **仓库** | <https://github.com/HoshinoSuzumi/chronoframe> |
| **Star** | ~1,900 |
| **语言** | Vue |
| **平台** | Web（Docker 自托管） |
| **许可证** | MIT |
| **最近活跃** | 活跃开发（2026-09-08） |
| **简介** | 自托管个人图库，支持 Live/Motion Photos、EXIF 解析、地理位置识别。在线照片管理+相册，但不提供旅行足迹管理和 POI 标记。 |

#### 8. PythonPhoto2Location
| 字段 | 内容 |
|------|------|
| **名称** | PythonPhoto2Location |
| **仓库** | <https://github.com/JozefJarosciak/PythonPhoto2Location> |
| **Star** | ~53 |
| **语言** | Python |
| **平台** | 桌面脚本 |
| **许可证** | 未标注 |
| **最近活跃** | 2026-01 更新 |
| **简介** | 将照片 EXIF 中的 GPS 数据转换为 Google Maps / Excel 格式的旅行日志。一次性转换工具，非交互式应用。 |

#### 9. pixTrail
| 字段 | 内容 |
|------|------|
| **名称** | pixTrail |
| **仓库** | <https://github.com/sukitsubaki/pixTrail> |
| **Star** | ~7 |
| **语言** | JavaScript（Web 界面）+ Python |
| **平台** | Web |
| **许可证** | 未标注 |
| **最近活跃** | 2026-01 更新 |
| **简介** | 从照片提取 GPS 数据，生成 GPX 文件，在地图上可视化旅行路线。功能单一。 |

#### 10. mappics
| 字段 | 内容 |
|------|------|
| **名称** | mappics |
| **仓库** | <https://github.com/antodippo/mappics> |
| **Star** | ~21 |
| **语言** | PHP |
| **平台** | Web |
| **许可证** | 未标注 |
| **最近活跃** | 2026-08 更新 |
| **简介** | 基于地图的旅行照片画廊，自动添加地点和天气描述。偏展示而非管理。 |

---

### 2.4 旅行足迹/地图标记类（小型项目）

#### 11. TravelMap (thisispivi)
| 字段 | 内容 |
|------|------|
| **名称** | TravelMap |
| **仓库** | <https://github.com/thisispivi/TravelMap> |
| **Star** | ~5 |
| **语言** | TypeScript |
| **平台** | Web（自托管） |
| **许可证** | 未标注 |
| **最近活跃** | 2026-09-04 |
| **简介** | 自托管旅行存档和发布应用。交互地图、可视化行程编辑器、旅行路线、地点标记。比较接近需求但项目很新很小。 |

#### 12. travelmap (hongwu122)
| 字段 | 内容 |
|------|------|
| **名称** | travelmap（世界旅行足迹地图） |
| **仓库** | <https://github.com/hongwu122/travelmap> |
| **Star** | ~2 |
| **语言** | HTML/JS |
| **平台** | Web |
| **许可证** | 未明确 |
| **最近活跃** | 2026-09-05（新项目） |
| **简介** | 管理旅行路线、城市和相册，生成高清足迹地图、海报和动态路线视频。描述接近需求，但项目极新，代码量和成熟度待验证。 |

#### 13. Stamped
| 字段 | 内容 |
|------|------|
| **名称** | Stamped |
| **仓库** | <https://github.com/MarvinLeRouge/Stamped> |
| **Star** | ~0 |
| **语言** | Python (FastAPI) + Vue 3 |
| **平台** | Web（本地优先） |
| **许可证** | MIT |
| **最近活跃** | 2026-09-07 |
| **简介** | Local-first web app，导入照片和 GPX 轨迹，自动检测旅程，在私有地图上浏览。理念与需求高度吻合（本地优先+照片+轨迹），但项目刚起步。 |

#### 14. TravelGlobe
| 字段 | 内容 |
|------|------|
| **名称** | TravelGlobe |
| **仓库** | <https://github.com/TomasNilsson/TravelGlobe> |
| **Star** | ~3 |
| **语言** | JavaScript |
| **平台** | Web |
| **许可证** | 未标注 |
| **最近活跃** | 2024-05 |
| **简介** | 基于地图的旅行概览，包含照片和每次旅行的信息。已停止更新。 |

#### 15. trippy-track
| 字段 | 内容 |
|------|------|
| **名称** | trippy-track |
| **仓库** | <https://github.com/pinpox/trippy-track> |
| **Star** | ~4 |
| **语言** | Go |
| **平台** | Web（自托管） |
| **许可证** | 未标注 |
| **最近活跃** | 2026-05 |
| **简介** | 自托管旅行日记，支持实时 GPS 追踪、照片时间线和地图分享。 |

#### 16. visited-countries-map
| 字段 | 内容 |
|------|------|
| **名称** | visited-countries-map |
| **仓库** | <https://github.com/tomi5/visited-countries-map> |
| **Star** | ~13 |
| **语言** | TypeScript (React) |
| **平台** | Web |
| **许可证** | 未标注 |
| **最近活跃** | 2026-08 |
| **简介** | 交互式"去过哪些国家"地图，React + Leaflet。仅国家级别标记，无城市/POI/照片。 |

---

## 三、需求覆盖矩阵

| 项目 | R1 城市点亮 | R2 POI+照片 | R3 小吃店评价 | R4 交通方式 | R5 爬山轨迹 | R6 文本导入 | R7 本地优先 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **Dawarich** | ✅ | ⚠️ 部分 | ❌ | ⚠️ 部分 | ⚠️ 部分 | ❌ | ✅ |
| **GeoPulse** | ✅ | ⚠️ 部分 | ❌ | ❌ | ⚠️ 部分 | ❌ | ✅ |
| OwnTracks 生态 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| OpenTracks | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| GPXSee | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| MTL Explorer | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| chronoframe | ❌ | ⚠️ 部分 | ❌ | ❌ | ❌ | ❌ | ✅ |
| PythonPhoto2Location | ⚠️ 部分 | ⚠️ 部分 | ❌ | ❌ | ❌ | ❌ | ✅ |
| pixTrail | ❌ | ⚠️ 部分 | ❌ | ❌ | ⚠️ 部分 | ❌ | ✅ |
| mappics | ⚠️ 部分 | ⚠️ 部分 | ❌ | ❌ | ❌ | ❌ | ❌ |
| TravelMap (thisispivi) | ✅ | ⚠️ 部分 | ❌ | ⚠️ 部分 | ❌ | ❌ | ✅ |
| travelmap (hongwu122) | ✅ | ⚠️ 部分 | ❌ | ⚠️ 部分 | ❌ | ❌ | ⚠️ 部分 |
| Stamped | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ |
| TravelGlobe | ✅ | ⚠️ 部分 | ❌ | ❌ | ❌ | ❌ | ⚠️ 部分 |
| trippy-track | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| visited-countries-map | ⚠️ 国家级 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

图例：✅ 覆盖 / ⚠️ 部分覆盖（有但不完善或需搭配其他工具） / ❌ 无覆盖

---

## 四、需求缺口分析

### 完全缺失的需求

**R6 —— 文本导入（日记/流水账 → 结构化足迹）**：在检索到的所有项目中，**没有任何一个**实现了"输入一段自然语言游记文本，自动解析为结构化足迹"的功能。这是整个开源生态中最大的空白。最接近的能力是 Dawarich 的"Trips notes"（手动写备注），以及 GeoPulse 的 Memos 集成（将备忘录关联到时间线），但都不涉及 NLP 解析。

### 严重不足的需求

**R3 —— 小吃店等地点标记 + 关联照片 + 个人评价**：没有任何项目提供"标记一个具体店铺、上传照片、写评价"这一完整闭环。Dawarich 的"Visits (Beta)"可以自动建议访问过的地点并确认，但缺乏手动 POI 创建、照片关联和评价功能。chronoframe 可以在地图上展示照片但没有评价功能。

**R4 —— 记录交通方式描述**：Dawarich 支持创建 Trip 并添加 notes（可以手动写"从重庆坐高铁到成都"），GeoPulse 有自动旅行模式分类（步行/骑行/驾车），但都不支持**结构化的、可查询的**交通方式记录。

### 部分满足但需改进的需求

**R2 —— POI 在地图上点亮 + 大量照片**：Dawarich + Immich/Photoprism 集成是该方向最好的组合：Immich/Photoprism 管理照片（含地图视图），Dawarich 管理时间线并在同一地图上显示。但这需要部署两个重型服务，且 POI 粒度以"自动检测的停留点"为准，不能手动创建精细标记。

**R5 —— 爬山轨迹**：OpenTracks 和 GPXSee 都做得很专业（轨迹、海拔、速度、导出），但它们独立于旅行管理工具。需要"先在其他 App 记录轨迹→导出 GPX→导入 Dawarich/GeoPulse"的流程，体验割裂。

---

## 五、组合方案可行性分析

存在一种"组合拳"思路来尽量覆盖需求：

| 工具组合 | 覆盖的需求 | 问题 |
|----------|-----------|------|
| Dawarich + Immich + OpenTracks | R1 R2(部分) R5 R7 | 三套系统独立部署，数据不互通，无 R3 R4 R6 |
| GeoPulse + OpenTracks + chronoframe | R1 R2(部分) R5 R7 | 同上，且 GeoPulse 许可证为 BSL-1.1 |

**结论：即使组合多个工具，也无法覆盖 R3（POI+评价）和 R6（文本导入），且运维复杂度成倍增加。**

---

## 六、结论

### 是否存在"开箱即用、几乎完全满足"的现成开源软件？

**不存在。**

### 最接近的是哪个？

**Dawarich**（<https://github.com/Freika/dawarich>，~10.3k stars，AGPL-3.0）是目前最接近的开源项目。它在 R1（城市点亮）、R7（本地优先/自托管）方面表现优秀，在 R2（照片集成）、R4（手动备注交通方式）、R5（GPX 导入）方面有部分支持。但它是一个**位置历史时间线工具**而非**旅行足迹管理工具**——它的核心是"记录你去过哪里"，而不是"记录你对去过的地方的感受和评价"。

### 差距在哪？

与用户需求的本质差异在于：Dawarich/GeoPulse 等工具面向的是**"自动追踪你去过哪里"**（被动记录 GPS 轨迹），而用户需求描述的是一个**"主动标记和管理旅行记忆"**的工具——手动点亮城市、标记具体的小吃店、写评价、记录交通方式、导入游记文本。二者的用户行为模式和数据模型根本不同。

具体差距：
1. **无 POI 级的富文本+照片评价**（R3）——数据模型完全不支持
2. **无结构化交通方式**（R4）——只有 Trip notes 自由文本
3. **无文本→结构化导入**（R6）——无 NLP 能力
4. **爬山轨迹依赖外部工具**（R5）——需导入 GPX，非原生支持

### "自己造"是否合理？

**合理，且有实际价值。** 理由如下：

1. **需求组合独特**：没有任何一个开源项目将这 7 条需求作为整体来设计，尤其是 R3（小吃店评价）和 R6（文本导入）在开源生态中完全空白。
2. **数据模型差异大**：以 Dawarich 为代表的时间线类工具的数据模型（GPS 点→停留→出行）与"旅行足迹"的数据模型（城市/POI/照片/评价/交通/轨迹）存在根本性差异，通过 fork 改造的成本可能高于新起炉灶。
3. **参考生态丰富**：虽然不存在开箱即用的方案，但每个子领域都有成熟的参考实现——地图可视化（Leaflet/MapLibre）、GPS 轨迹解析（GPX 库）、照片 EXIF 处理、本地存储（SQLite）——可以直接借用，不需要从零发明所有轮子。
4. **文本导入是差异化亮点**：利用当前 LLM 能力（如本地小模型或 API）将游记文本自动解析为结构化足迹，是一个在开源生态中尚无先例的功能方向，可能成为该工具的核心特色。

### 建议的开发策略

以"本地优先 Web 应用"（如 Electron/Tauri 桌面端或 PWA + 本地 SQLite）为载体，自建数据模型，在以下方面直接借鉴成熟开源项目：

- 地图渲染 → 借鉴 Dawarich 的 Leaflet/MapLibre 方案
- GPS/GPX 轨迹 → 借鉴 OpenTracks/GPXSee 的解析逻辑
- 照片地理化 → 借鉴 pixTrail/chronoframe 的 EXIF 处理方式
- 文本导入 → 自研（调用 LLM）

---

## 七、实际访问来源

```
https://api.github.com/search/repositories?q=travel+map+mark+visited+places&sort=stars
https://api.github.com/search/repositories?q=places+I+have+been+map+self+hosted&sort=stars
https://api.github.com/search/repositories?q=visited+cities+map+open+source&sort=stars
https://api.github.com/search/repositories?q=photo+map+travel+self+hosted&sort=stars
https://api.github.com/search/repositories?q=OpenTracks+OR+FitoTrack+OR+GPX+viewer&sort=stars
https://api.github.com/search/repositories?q=exif+geotag+photo+map+viewer&sort=stars
https://api.github.com/search/repositories?q=dawarich+OR+tripcards+OR+travelmapper&sort=stars
https://api.github.com/search/repositories?q=GPXSee&sort=stars
https://api.github.com/search/repositories?q=owntracks&sort=stars
https://api.github.com/search/repositories?q=geojournal+OR+travel+journal+photo+map+geotag&sort=stars
https://api.github.com/search/repositories?q=visited+countries+map+tracker&sort=stars
https://api.github.com/search/repositories?q=trip+journal+self-hosted+map+photo&sort=stars

https://github.com/Freika/dawarich (readme via API)
https://github.com/tess1o/geopulse (readme via API)
https://github.com/mindalyze-com/mtl-explorer (readme via API)
https://github.com/thisispivi/TravelMap (repo info via API)
https://github.com/hongwu122/travelmap (repo info via API)
https://github.com/MarvinLeRouge/Stamped (repo info via API)
https://github.com/HoshinoSuzumi/chronoframe (repo info via API)
https://github.com/tumic0/GPXSee (repo info via API)
https://github.com/owntracks/android (repo info via API)
https://github.com/owntracks/recorder (repo info via API)
https://github.com/JozefJarosciak/PythonPhoto2Location (repo info via API)
```

*注：所有项目信息均通过 GitHub REST API 实时获取并核验（2026-09-08）。Star 数为近似值，取搜索返回时的 `stargazers_count` 字段。未找到符合"文本导入旅行日记"和"交通方式结构化记录"需求的开源项目。*
