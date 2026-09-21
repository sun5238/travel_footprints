# 文本解析器选型调研：离线中文分词 / 日期解析 / 行政区划 / 参考解析器

> 调研日期：2026-09-20
> 适用场景：`travel_footprints` M2「文本导入管线」前期选型。全部结论经官方源（GitHub API / PyPI JSON API / raw 文件）核实，无法核实的统一标注「未能核实」，未编造 URL 或数据。
> 关联文档：[DESIGN.md](../DESIGN.md) 第 5.1 节解析管线、《[log-format.md](../docs/log-format.md)》预设格式、ADR-0004 规则解析决策。

---

## 0. 现状：本项目解析需求与现有约定格式

### 项目硬约束

- **本地优先、完全离线、无外发数据**：任何解析组件不得有默认网络行为（DESIGN.md 第 1、9 节）。
- **解析默认不用 LLM**（含本地模型），采用「规则层 + 学习词典 + 校正页」管线（ADR-0004，Status: accepted）。
- **预设格式优先、自由文本回退**：《log-format.md》定义「一行一事件」预设格式（`# 行程标题`、`时间：`、`@城市`、`## 日期小节`、`- 交通`、`- 店`、`- 轨迹`、`- 备注`）。
- **先展示后入库、绝不静默错认**：无法解析的原文整段保留、可全文搜索兜底（DESIGN.md 5.1 / log-format.md 解析优先级第 3 条）。
- **学习回灌**：每次人工校正写入 `correction` 标注库（原文 -> 标准 JSON），新词写入 `dictionary`，后续识别率递增（DESIGN.md 第 4、5.1 节）。
- 时间规则：所有实体时间以「本地挂钟时间 + IANA 时区」存储，派生 Unix 时间戳（DESIGN.md 第 4 节、ADR-0006）。

### 现有源码清单与解析器状态（backend/travel/）

`backend/travel/` 现有文件（11 个源文件）：

| 文件 | 职责 | 与解析管线关系 |
|---|---|---|
| `api.py` | FastAPI 路由 | 无 |
| `backup.py` | 导出/导入 zip | 无 |
| `config.py` | 配置（含 DEFAULT_TIMEZONE） | 解析器将使用 |
| `db.py` | SQLite 引擎/Session | 无 |
| `main.py` | 应用入口 | 无 |
| `media.py` | 媒体/缩略图 | 无 |
| `models.py` | SQLAlchemy 模型 | 无解析相关表 |
| `schemas.py` | Pydantic schema | 无 |
| `store.py` | 存储层（含 `_parse_tags` 标签切分） | 无 |
| `timeutil.py` | `parse_local` / `to_epoch` / `to_local_iso` | 解析结果将走这套时间约定 |

**结论：解析器尚未实现。** 对 `backend/travel/` 全量检索，`parse` 仅命中 `timeutil.parse_local`（ISO 本地时间解析）与 `store._parse_tags`（标签按逗号切分），无任何行程文本解析/分词/词典代码。同时 **`correction` 与 `dictionary` 两张表也尚未实现**——DESIGN.md 第 4 节是逻辑模型，`models.py` 目前只有 `Trip / City / Place / Visit / TransportLeg / Trail / StoredFile / Media` 八张表。M2 管线需从零实现解析模块（建议独立为 `backend/travel/parser/` 包）。

---

## Q1. 离线中文分词 / NER 库选型：jieba / HanLP / LTP / LAC

### 1.1 总览对比（每条均已核实）

| 库 | pip 包 | 许可证 | 完全离线 | 安装体积量级 | 分词+粗粒度专名 | 用户自定义词典 | 维护状态 |
|---|---|---|---|---|---|---|---|
| **jieba** | `jieba` | MIT | 开箱即用（零网络） | 内置词典 4.84 MiB；sdist 18.3 MiB | 分词+词性（nr/ns/nt 等粗粒度专名标签） | 强：`load_userdict` / `add_word` | 2020.12 后无大版本（稳定） |
| **HanLP 2.x** | `hanlp` | 代码 Apache-2.0；**模型 CC BY-NC-SA 4.0（非商业）** | 首次需联网下载模型，之后可离线 | 模型 43.5–85.4 MiB 起；依赖 torch/transformers | 是（独立 NER 模型） | 分词层有 dict_combine/force；NER 无词典注入 | 活跃（2026-09 发布 2.1.5） |
| **HanLP 1.x** | `pyhanlp` | 代码 Apache-2.0；数据许可未声明 | 首次需联网 + **需 Java 运行时** | data 约 638 MiB | 是 | 强 | 1.x 于 2025-01 更新 |
| **LTP 4** | `ltp` | **无 OSI 许可，商用需付费** | 首次需联网下载模型（HuggingFace） | 模型 small 156.8 MiB / tiny 31.3 MiB / base 491.9 MiB | 是（seg/pos/ner/srl/dep 全套） | 未发现内置接口 | 2024-06 发布 4.2.14 |
| **LAC** | `LAC` | Apache-2.0 | 开箱即用（模型内置在包内） | sdist 61.8 MiB；**运行时需额外装 paddlepaddle** | 是（PER/LOC/ORG/TIME 四类） | 强：`load_customization` 支持多词长片段 | 2021-05 后停滞 |

### 1.2 分项详情

**jieba（0.42.1，推荐首选）**
- 完全离线：是。词典 `dict.txt`（约 4.84 MiB）与 idf.txt 全部内置于包内，无任何在线下载器。
  来源：https://pypi.org/pypi/jieba ；https://github.com/fxsjy/jieba
- pip：`pip install jieba`，零第三方依赖，模型随包自带。
- 许可证：MIT（GitHub LICENSE 字段 + PyPI license 均核实）。
- 分词 + 粗粒度专名：`jieba.posseg` 直接输出 `nr`(人名) / `ns`(地名) / `nt`(机构名) / `nz`(其他专名) 等标签（README 词性表）。这是「词典+词性」式粗粒度识别，非深度学习 NER——但本项目专名识别本质是「行政区划表 + 用户词典」驱动，不需要训练型 NER。
- 自定义词典：`jieba.load_userdict(file)` / `add_word` / `del_word`，词条可带「词频 + 词性」，正好承载店名/景点名的兜底策略。
- 维护：2020 年后无新版本，但库稳定、生态成熟。

**HanLP 2.x（`hanlp`，不推荐）**
- 首次需联网下载模型（缓存默认 `~/.hanlp`，可用 `HANLP_HOME` 改），但**若部署环境无网必须预置模型文件**。
  来源：https://pypi.org/pypi/hanlp ；https://github.com/hankcs/HanLP
- 模型体积（对官方模型服务器实测）：中文粗粒度分词 COARSE_ELECTRA_SMALL_ZH 约 43.5 MiB；MSRA NER 中文模型约 45.0 MiB；联合小模型约 85.4 MiB。
- **许可证陷阱**：代码 Apache-2.0，但**模型默认 CC BY-NC-SA 4.0（非商业）**。对"可分发的软件/商用"是硬伤。来源：README License 段。
- 依赖重（torch + transformers + sentencepiece），对"最小够用不超重"是牛刀。

**HanLP 1.x（`pyhanlp`，不推荐）**
- **必须装 Java**（经 JPype 调用），数据包 data-for-1.7.5.zip 实测约 638 MiB，远超"最小够用"。
  来源：https://pypi.org/pypi/pyhanlp ；https://github.com/hankcs/pyhanlp
- 数据/模型包正式许可未在 1.x README 单独声明（**未能核实**）。

**LTP 4（哈工大语言技术平台，`ltp`，不推荐）**
- **商用需付费**：README「开源协议」明确面向高校/中科院/个人研究者免费，商用联系 car@ir.hit.edu.cn。**不是 OSI 开源许可**（仓库根目录无 LICENSE 文件，GitHub license API 返回 None）。常见"各组件 MIT"说法未在官方仓库得到证实（**未能核实**）。
  来源：https://pypi.org/pypi/ltp ；https://github.com/HIT-SCIR/ltp ；文档 https://ltp.readthedocs.io/zh_CN/latest/
- 首次需联网从 HuggingFace 下载模型；支持 `local_files_only=True` 预置后离线。
- 模型体积（官方 MODELS.md）：tiny 31.3 MiB / small 156.8 MiB / base 491.9 MiB。HuggingFace 端精确字节数本环境无法访问（**未能核实**）。
- **未发现 LTP 4 Python 包内置用户自定义词典接口**（源码与文档检索未命中，**未能核实到官方支持**）。

**LAC（百度 `LAC`，备选）**
- 模型内置在 pip 包内（setup.py 的 package_data 打入），**开箱即用完全离线**；但**运行时依赖 paddlepaddle**（models.py 走 paddle 推理），CPU 版也是上百 MiB 级。
  来源：https://pypi.org/pypi/LAC ；https://github.com/baidu/lac
- sdist 实测 61.8 MiB（含模型权重），README 另说明移动端超轻量模型约 2 MiB。
- 许可证：Apache-2.0（GitHub / PyPI / setup.py 三方一致）。底层训练语料来源与许可官方未披露（**未能核实**）。
- 联合模型直接输出 PER/LOC/ORG/TIME 四类专名；`load_customization` 支持**多词长片段**干预，最贴合"店名景点名用户词典兜底"。
- 注意 pip 陷阱：PyPI sdist 的 `requires_dist` 为空（构建机已装 paddle），**运行前需自行 `pip install paddlepaddle`**。
- 维护：2021-05 后停滞。

### 1.3 Q1 结论

**选 jieba 作为分词器，粗粒度专名识别完全交给「行政区划表 + 用户词典」驱动，不引入训练型 NER。**
- jieba 在四维上全部最优：体积（<10 MiB）、离线（零网络）、许可（MIT）、自定义词典（原生支持带词性的词条,`ns`/`nt` 标签给专名候选加分）。
- 如需"开箱即得到的专名实体标签"且能接受 paddle 体积，备选 LAC（Apache-2.0、模型内置、词库干预命中实体识别）。
- 明确排除：LTP（商用需付费 + 无内置用户词典 + torch）；HanLP 1.x（Java + 638 MiB）；HanLP 2.x 慎选（模型 CC BY-NC-SA 非商业 + torch 重依赖，自用可接受）。
- 任何涉及公开发布/商用的方案，先核对 LTP（需商业授权）与 HanLP 系列（模型 CC BY-NC-SA 4.0）许可。

---

## Q2. 中文日期 / 时间表达解析

### 2.1 库逐个实测结论（本机实测 2026-09-20）

**dateparser（1.4.3）——只覆盖"正式书面 + 相对说法"**
- 许可证 BSD-3-Clause；活跃维护（2026-09 发布）；离线（1.4.3 安装包零网络调用）。
  来源：https://pypi.org/project/dateparser/ ；https://github.com/scrapinghub/dateparser ；https://dateparser.readthedocs.io/
- 支持 zh / zh-Hans / zh-Hant 语言数据，但实测覆盖仅限：带年份书面日期（`2019年6月8日`✅）、相对词（`今天/昨天/下周/今年`✅）、星期（`周六/星期六`✅ 推"最近的过去周六"）。
- **实测失败（返回 None）**：`10月1号`、`1号`、`3号下午两点`、`下午两点`、`晚上8点`、`初五`、`农历正月初一`、`国庆`、`10月1号到7号`。无年份的 `10月1日` 在自动检测下给出错误年份（`2010-01-20`），强制 zh 为 None。
- **结论**：不作为中文主语路径；可作英文/ISO/多语言 fallback 层。

**zhdate（1.0）——公历/农历互转，纯离线纯 Python，但 GPLv3+**
- 许可证 **GPL-3.0-or-later（传染性）**；零第三方依赖；纯本地计算。
  来源：https://pypi.org/project/zhdate/ ；https://github.com/CutePandaSh/zhdate
- 实测 API：`ZhDate(2020,1,1).to_datetime()` 得到公历；`ZhDate.from_datetime()` 反查；`.chinese()` 输出中文农历串（含天干地支）。
- **局限**：只做「整数参数互转」，不做中文表达解析——得自己先把「初五」识别成 (月, 日) 再调用。
- 附带：PyPI 上的 sdist 是 macos 本地打出的 tarball（内含 `/opt/homebrew/...` 路径），非标准结构但可 pip 安装（实测可安装、纯 Python 无需编译）。
- **许可硬伤**：本项目若闭源/商业分发，引入 GPLv3 会被传染条款约束。

**lunarcalendar（PyPI 名 `LunarCalendar`，0.0.9）——MIT 但停更+重依赖**
- 许可证 MIT；**2018-06 上传后停更**；强依赖 C 扩展天文库 `ephem`（未装 ephem 时 import 直接报错，实测）。
  来源：https://pypi.org/project/lunarcalendar/ ；https://github.com/wolfhong/LunarCalendar
- 实测 API：`Converter.Solar2Lunar` / `Lunar2Solar` / `Lunar(2020,1,1).to_date()` 可用；但**无任何中文日期串输出**（Lunar 无 `to_chinese()`）。
- 结论：许可友好，但"停更 8 年 + C 扩展依赖 + 无中文输出"，不如 zhdate 干净；作为避开 GPL 的备选。

**cn2an（0.5.24）——中文数字↔阿拉伯数字归一化，MIT，活跃**
- 许可证 MIT；活跃维护（2026-04 发布）；纯 Python（依赖同为纯 Python 的 `proces`）。
  来源：https://pypi.org/project/cn2an/ ；https://github.com/Ailln/cn2an
- 实测 API：`cn2an.cn2an('二十六') → 26`；**`cn2an.transform('三月五号', 'cn2an') → '3月5号'`**（嵌入文本的中文数字原位归一化）；`transform('二〇二〇年') → '2020年'`；`transform('初五') → '初5'`（数词转换、农历前缀保留）。
- **价值点**：直接消解中文数字歧义（三十六/三六/三十、大写二〇二〇），正是自写正则最痛苦的部分；配合"先归一化、再套模式"的工作流。
- 唯一缺口：不处理"初X"前缀（需自写 1 行映射）。

**snownlp（0.12.3）——直接排除**
- 核心是情感分析/文本分类，**特征清单中没有任何日期/时间解析能力**（以官方 README 职能清单为据；本环境 37 MB 源码下载中断，未能本地实测）。
  来源：https://pypi.org/project/snownlp/ ；https://github.com/isnowfy/snownlp
- 停更多年（2015 后）且体积大（自带 37 MB 词典文件），与"日期精确解析"无关，不进入候选。

### 2.2 纯自写正则：可行性、局限与推荐

**可行性**：现有库对口语中文覆盖实测接近零，**自研规则层（约 300–500 行纯 Python）几乎是唯一主路径**。可拆解为：

1. **数字归一化** → 交给 `cn2an.transform(text, 'cn2an')`（十/十一/大写数字全部归一）。
2. **农历值** → 正则捕获 `(初|十|廿|廿X|三十)\d?` → 映射为 (月, 日) 整数 → 交农历转公历。
3. **时刻** → 词典 + 正则：`(上午|下午|晚上|凌晨)` + `([一二三四五六七八九十]|1[0-2])点(半|分…)?`。
4. **星期** → `周/星期/礼拜[一二三四五六日天]` → 以 `RELATIVE_BASE`（默认今天）推算最近的该日。
5. **节日** → 小词典优先：`国庆/春节/大年初一/元旦` 等（如 国庆 → 10-01~10-07），规则优先于日期模式。
6. **「10月1号到7号」区间** → 正则 `(?P<m>\d+)月(?P<d>\d+)(号|日)(到|至|-|~)(?P<d2>\d+)(号|日)?`：第二段缺月沿用第一段月份；两段缺年份沿用"今年"；产出 `(start, end_exclusive=下一日 00:00)`。

**真实局限（公开讨论公认 + 本报告实测佐证）**
1. 「3号」缺年份/月份：默认"今年/本月"可能取到未来没发生的日期 → 需约定 `PREFER_DATES_FROM='past'` 式回退（"之前的最近日"或"当前日"二选一）。
2. 「星期六」无法定位历史某周六：只能按基准推"最近的一个"——规则方案通性，需产品语义定死。
3. 农历没有查表就无法转公历：正则只能识别"这是农历表达"，转公历必须有 zhdate/lunarcalendar/自研常数表。
4. 「10月1号到7号」的边界语义需产品定：固定为 `[start, end_next_day)`（即 7 号整天包含）即可不必纠结。
5. 专门处理"中文日期间隔展开"的现成开源库未找到（**未能核实到存在**）。

### 2.3 Q2 结论

**主路径：自研"规则解析层"，唯一推荐第三方依赖是 cn2an（MIT）；农历转公历建议自研常数表（约 200 行）或 lunarcalendar，dateparser 作为可选英文/ISO fallback。**
- 现有库对需求清单（口语「号」、时段、农历、节日、区间）覆盖率实测接近零，没有任何库能直接产出 `(start, end)`。
- 中文数字歧义用 cn2an 原位归一化（MIT、活跃、纯 Python）；农历转公历用 zhdate（GPLv3 需评估传染性）或自研常数表；dateparser 只作第三层兜底，吸收英文/ISO/多语言相对时间（BSD-3、离线），不进中文主语路径。
- **语义约定（建议写进 ADR）**：区间统一 `(start, end_exclusive)`；缺年份默认当年；「周六晚上」推"最近一个周六"；「10月1号到7号」= `[次年…-10-01 00:00, …-10-08 00:00)`。
- 输出格式对齐 `timeutil.parse_local`：解析结果最终落成 `local ISO 字符串 + IANA 时区 + 派生 epoch`。

**未能核实**：snownlp 本地运行结果；dateparser 旧版本（≤0.7.x）在线翻译插件的具体行为与移除版本；中文日期间隔展开的现成开源库存在与否。

---

## Q3. 行政区划离线数据源

### 3.1 逐仓库核实

**A. `modood/Administrative-divisions-of-China`（主推，已深度核实）**
- 仓库：https://github.com/modood/Administrative-divisions-of-China
- 许可证：**WTFPL**（"Do What The Fuck You Want to Public License"，GitHub LICENSE 字段 + README 徽章核实）——几乎无任何使用限制。
- 数据体积（GitHub API 实测各文件字节数）：
  - `provinces.json` 1 KB（31 条，大陆省级）
  - `cities.json` 19 KB（342 条地级）
  - `areas.json` 228 KB（县级，约 2800 条）
  - `streets.json` 4.2 MB（乡镇级）、`villages.json` 84.9 MB（村级）
  - **`pcas-code.json` 1.9 MB（省市区三级联动、带行政区划代码）——旅行 App 最适用形态**
  - `data.sqlite` 59 MB（全量 SQLite）
- 字段：每条 `{"code", "name"}` + 父级编码（provinceCode/cityCode/areaCode）；联动文件为嵌套 children。**不含经纬度坐标**。
- 更新状态：README **明确声明"本项目数据不再更新"**，数据止于 2023 年统计用区划代码（截止 2023-06-30）；原因是国家统计局自 2024-10 起不再公开《统计用区划代码和城乡划分代码》明细。仓库后续 push 只是工程维护，数据内容已冻结。
- 离线内置结论：**非常适合**。WTFPL 无限制，`pcas-code.json` 约 1.9 MB 即可覆盖省市区三级；需要 2024/2025 变更可自行增量补充。

**B. `uiwjs/province-city-china`（民政部源，格式最全）**
- 仓库：https://github.com/uiwjs/province-city-china
- 许可证：**MIT**。
- 数据体积（实测 dist/）：`province.json` 2.7 KB（34 条，含港澳台）、`city.json` 33 KB（337 条）、`area.json` 376 KB（3285 条）、`town.json` 5.7 MB（乡镇级），并有 `data.sql` 2.3 MB 及 CSV；共约 40 个 JSON/CSV/SQL 数据文件。
- 字段：`{"code", "name", "province", "city", "area"}`（6 位代码 + 各级父码，乡镇级为 9 位码）。**不含经纬度**。
- 更新状态：README-zh 标注 **"数据更新时间：2021/03/22（民政部）"**（静态数据时间是 2021 年）；仓库本身活跃（3041 stars）。
- 离线内置结论：适合。MIT + 现成三格式；注意数据偏旧（2021）且**不含村级**。

**C. `pluwen/china-cities-dataset`（轻量、更新较新）**
- 仓库：https://github.com/pluwen/china-cities-dataset
- 许可证：**GPL-3.0**。
- 粒度：仅**县级以上（省/市/县三级）**，XML 格式（简体/繁体各约 150 KB），不含乡镇/村级。
- 更新状态：README 标注"更新到 2026 年 5 月"，数据源国家统计局 + 维基百科 + QQ——是上述仓库中时间最新者。

### 3.2 Q3 结论

| 仓库 | 许可 | 到县级规模 | 数据时间 | 乡镇/村级 | 坐标 |
|---|---|---|---|---|---|
| modood/… | WTFPL | ~0.2 MB / ~3000 条 | 2023（已停更，README 声明） | 有（村达 85 MB） | 无 |
| uiwjs/… | MIT | ~0.4 MB / 3285 条 | 2021（README 标注） | 有乡镇，无村 | 无 |
| pluwen/… | GPL-3.0 | ~0.15 MB | 2026-05 | 无 | 无 |

**推荐：`modood/Administrative-divisions-of-China` 的 `pcas-code.json`（1.9 MB，WTFPL）作为主内置数据**，一次打包、完全离线；若想以更宽松的 MIT 全量格式为准，选 `uiwjs/province-city-china`。
- **重要提醒**：以上数据源**均不含经纬度坐标**。本项目 `City` 表有 lat/lng 字段、地图需点亮坐标——城市中心坐标需另行自备（如按省/市手动维护一份城市中心点坐标表，或用离线 GeoJSON/行政区划边界数据），或留空由用户在校正页手动拖点，与 DESIGN.md「坐标可选、留空"无坐标"态」一致。
- 字段利用方式：`code` 做去重/标准名，`name` 做城市名词典（配合 jieba `load_userdict` 加入行政区划全名/别名），层级关系用于「@成都」归属推导。

---

## Q4. 可参考的开源「日记文本 → 结构化时间线」解析器

### 4.1 `novoid/Memacs`（核心参考，已读源码）

- 仓库：https://github.com/novoid/Memacs　许可证：GPL-3.0，1112 stars，活跃。
- 定位："把各类个人数据源聚合成 org-mode 时间线"（结构化来源 → 时间线），**不是自由散文日记 → 事件提取**，但架构蓝图很有借鉴价值。
- **规则引擎/解析器组织方式**（实测源码树）：
  - 框架层 `memacs/lib/`：`memacs.py`（基类：统一参数解析、日志、异常捕获、org 写出器装配）、`orgwriter.py`（OrgOutputWriter）、`orgproperty.py`（`:ID:` 哈希去重）、`reader.py` 等。
  - **每个数据源一个模块** `memacs/<source>.py`（whatsapp.py / gpx.py / csv.py / ical.py…20 余个），各自在 `_main()` 内用**正则或专用解析**提取「(时间戳, 标题, 属性)」三元组，再调 `_writer.write_org_subitem()` 写 org heading。
  - 最贴近"文本→时间线"的是 `memacs/csv.py`：用 `--timestamp-field` + `--timestamp-format`（strftime）+ `--output-format` 模板，逐行把 CSV 转成带时间戳的条目。
- **解析失败兜底**（docs/FAQs_and_Best_Practices.org "Error Handling" 章）：模块报错时错误**追加写入 `error.org`**，条目带 `+1d` 重复时间戳、持续出现在议程直到用户**手动删除**——失败不静默丢弃、不强依赖无人工；日志记 logging.error 并 sys.exit(1)。
- **渐进式/增量**：**无"学习回灌"**。但有 append-mode + `:ID:`（properties 的 key+value 做 sha1）**幂等去重**——重复运行不重复生成条目（增量/幂等），但没有"用户校正回灌、二次学习"机制。

### 4.2 `jrnl-org/jrnl`（自由文本 → 结构化条目）

- 仓库：https://github.com/jrnl-org/jrnl　许可证：GPL-3.0，7321 stars，非常活跃。
- 解析器组织：CLI 日记 App，对命令行输入的**自由文本实时解析**出日期时间（可交互补问）、`#tag` 标签与正文，落盘为带时间戳的结构化条目（text/JSON），支持导出；纯规则 + 日期解析，不依赖大模型。
- 兜底：解析不出日期时以当前时间/交互询问代替，**不丢失原文**。
- 增量/渐进：无回灌式学习。粒度是"一条日记"，非"一条日记内多个行程事件"。

### 4.3 `karlicoss/orgparse`（时间线文件解析层参考）

- 仓库：https://github.com/karlicoss/orgparse　许可证：BSD-2-Clause，424 stars。
- 纯 Python 把 org-mode 文件解析为 `OrgNode` 树（标题、tags、属性、SCHEDULED/DEADLINE、时间戳），是"把带时间戳的文本解析成结构化时间线树"的现成解析层，适合作为自制解析器底层参考。

### 4.4 Q4 结论

搜索范围内（GitHub 检索 diary parser / itinerary parser / org-mode parser 等）**未找到**专门做「自由文本旅行/行程日记 → 结构化时间线 + 渐进式学习回灌」的成熟开源项目；零星小项目（如 `ExCoder999/Travel-Itinerary-Parser`，1 star）未成型，不建议采用。
**建议**：以 **Memacs** 为设计蓝本（规则模块组织 + 失败写 error、不静默丢弃 + `:ID:` sha1 幂等增量），借鉴 **jrnl** 的"解析不出日期以当前时间/交互询问兜底、不丢原文"，结合本项目 `correction`/`dictionary` 设计**自研"用户校正回灌"机制**（这是现有开源项目普遍缺失的一环，也是 DESIGN.md 的核心差异点）。

---

## 5. 给本项目的最终选型建议

### 推荐组合（最小够用、全部符合"默认离线"）

| 模块 | 选型 | 许可 | 理由 | 风险 |
|---|---|---|---|---|
| 分词 + 粗粒度专名 | **jieba 0.42.1** | MIT | 纯 Python 零依赖、词典仅约 5 MiB、零网络；`load_userdict` 加载行政区划表+店名/景点词典；`posseg` 的 ns/nt 标签给专名候选加分 | 2020 后无新版本（功能稳定）；无训练型 NER（本项目不需要） |
| 中文数字归一化 | **cn2an 0.5.x** | MIT | `transform(..., 'cn2an')` 原位归一化中文数字，消解"三十六/三六/三十"歧义；活跃、纯 Python | 不处理"初X"前缀（自写 1 行映射） |
| 农历 → 公历 | **自研常数表（约 200 行）** 或 **lunarcalendar（MIT，但停更+依赖 ephem）**；若许可允许再说 zhdate（GPLv3） | MIT / GPLv3 | 本需求仅需"初五/正月初一"级别的农历↔公历，常数表足矣；zhdate 功能理想但 GPLv3 传染性需评估 | 自研表需校验闰月正确性 |
| 日期/时间规则层 | **自研正则分派层（约 300–500 行）** | 自有代码 | 现有库对口语中文覆盖率近零，规则层是唯一主路径；按 Q2.2 拆解（数字归一→农历→时刻→星期→节日→区间） | 「3号」缺年月、「周六」定位历史日的歧义需语义约定；见 Q2.3 建议的 ADR |
| 日期 fallback（可选） | **dateparser 1.4.3** | BSD-3 | 吸收 ISO / 英文 / 多语言相对时间输入；完全离线 | 中文口语覆盖差，只作第三层 |
| 行政区划内置数据 | **modood `pcas-code.json`（1.9 MB）** | WTFPL | 省市区三级带代码、体积小、许可无限制；一次打包内置 | 数据止于 2023（停更，因统计局不再公开明细）；不含经纬度 |
| 架构参考 | **Memacs 模式**（模块化规则 + 失败写入不静默 + 幂等增量）+ **jrnl 兜底**（解析不出不丢原文） | 借鉴设计（代码自研） | 与"先展示后入库、未识别保留原文"原则天然对齐 | 开源项目普遍缺"校正回灌"，需自研 |

### 落地要点（对齐 DESIGN.md / log-format.md / ADR-0004）

1. **新解析模块**建议独立 `backend/travel/parser/` 包：`rules.py`（日期/交通/动词/城市规则）、`admin_repo.py`（行政区划 + dictionary 查询）、`correction.py`（标注库读写）、`skeleton.py`（生成行程骨架候选）。
2. **分词器只做辅助**：预设格式行（`# / 时间：/@ / ## / - ` 标记开头）应**优先**按 log-format 切分；只有无法命中标记的行才进 jieba + 规则回退，符合"预设格式优先、自由文本回退"。
3. **专名识别流程**：行政区划全名/别名与用户词典先 `load_userdict` 打底 → posseg 输出 ns/nt 给候选 → 城市归属参考"最近一次 `@城市` 行"；店名/景点名解析不出就留 `place_name_snapshot` 原文，交给校正页。
4. **永不静默丢弃**：任何规则层无法解析的行 → 整段原文进"待精分/未解析"桶，可全文搜索（与 DESIGN.md 5.1、log-format 解析优先级第 3 条一致）。
5. **校正回灌**：人工校正写入 `correction`（原文 → 标准 JSON），新词回填 `dictionary` 表并即时 `jieba.add_word` 刷新会话内词典；为将来 Ollama/Qwen 本地模型复用 `correction` 数据预留开关位（ADR-0004 可逆决策）。

### 许可证兼容性小结

本项目仓库根目录暂无 LICENSE 文件；若将来希望**任意分发/商用**，推荐组合（jieba MIT、cn2an MIT、modood WTFPL、dateparser BSD-3、自研代码）全部为宽松许可、**无任何冲突**。需规避的传染/受限项：**zhdate（GPLv3+，用则需合规）**、**LTP（商用需付费）**、**HanLP 2.x 模型（CC BY-NC-SA 非商业）**、**pluwen 行政区划数据（GPL-3.0）**。

### 明确不推荐项汇总

- **LTP 4**：商用付费许可 + 无内置用户词典接口 + torch 重依赖。排除。
- **HanLP 1.x pyhanlp**：需 Java + data 约 638 MiB。超重。排除。
- **HanLP 2.x**：模型 CC BY-NC-SA 非商业 + torch/transformers 重依赖，功能对"最小够用"是牛刀。默认排除，若未来确需训练型 NER 且仅个人自用可再评估。
- **snownlp**：情感分类库、无日期解析能力、2015 停更、37 MB 大包。排除。
- **LAC**：Apache-2.0 + PER/LOC/ORG/TIME 功能对口，但需背 paddlepaddle（上百 MiB）且 2021 后停滞。**次选**，若出现"jieba 词性标签不够用"的具体场景再引入。