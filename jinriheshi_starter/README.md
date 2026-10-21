# 今日何食：HowToCook 数据与 Agent 开发启动包

版本：0.1.0 · 数据 Schema：1.0.0

这是可运行的数据工程起点和微信小程序开发交接包。数据源已经确定为 HowToCook。先复现本包，再按 `docs/AGENT_TASKS.md` 开发应用服务和小程序。

## 已交付与当前能力

| 项目 | 本包实际内容 |
| --- | --- |
| 固定来源 | HowToCook commit `0e106eea348c734fe1586f781202994439cf98a5` |
| 原文 | 372 篇非模板菜谱 Markdown，另保留原始 LICENSE 和 README |
| 规范化记录 | 372 条 JSONL，保留章节、完整步骤块、来源、哈希、身份与版本 |
| 开发样板 | 30 条有配料、标签、器具候选和证据的记录；341 个配料关联 |
| 字典 | 115 个食材、28 个器具、16 个口味/菜系/口感标签 |
| 审核状态 | 18 条 `agent_checked`、12 条 `needs_review`；均未人工发布，未实烹 |
| 数据工具 | 来源校验、离线构建、Schema/证据验证、参考推荐、SQLite 导出 |
| 应用契约 | 4 份 JSON Schema、OpenAPI 3.1 契约、事件与请求样例 |
| 开发交接 | PRD、架构、数据字典、API 说明、T00—T09 任务与 56 项验收案例 |

372 是源文档数，其中包含饮料、调料、甜品及半成品；其余 342 条只有正文结构和来源元数据，尚未完成食材/推荐标签标注。30 条也是开发样板，不能说成 30 条已上线菜谱。

当前没有 HTTP 服务、微信页面、微信登录、线上数据库或真实发布。本地 Python 工具不替代微信开发者工具及真机验收。

## 五分钟运行

使用 Python 3.10 或以上。推荐先建立虚拟环境；也可在已有隔离开发环境中执行以下命令。

```bash
python -m pip install -r requirements-dev.txt
python scripts/fetch_howtocook.py --verify-only
python -m jinriheshi build
python -m jinriheshi validate
python -m unittest discover -s tests -v
python -m jinriheshi recommend --request examples/request_basic.json --mode development --seed 42
python -m jinriheshi export-sqlite --output data/generated/recipes.sqlite
```

首次安装依赖需要网络。包中已经包含锁定的全部原文，之后上述构建、验证、测试和预览均可离线执行。不要为了本地预览重新下载上游。

Windows CMD 可使用 `py -3 -m venv .venv`，然后把上面命令中的 `python` 替换为 `.venv\Scripts\python.exe`。macOS/Linux 可用 `python3 -m venv .venv` 后使用 `.venv/bin/python`。

默认生产模式故意只使用已发布记录；本包已发布数是 0：

```bash
python -m jinriheshi recommend --request examples/request_basic.json
```

预期返回 `status: no_candidate`，进程正常退出。这表明生产门槛生效。`--mode development` 是可信开发者使用的本地参数，不能做成小程序可随意传入的接口参数。

## 可复制的推荐场景

```bash
# 偏好咸鲜、想用掉鸡蛋：可返回开发候选
python -m jinriheshi recommend --request examples/request_basic.json --mode development --seed 42

# 已确认凉拌黄瓜所需食材种类：返回该真实样板
python -m jinriheshi recommend --request examples/request_pantry_cucumber.json --mode development --seed 42

# 严格15分钟：当前没有已核验总时间，预期无候选
python -m jinriheshi recommend --request examples/request_strict_time.json --mode development --seed 42
```

库存样例只核对食材种类，不能说明数量足够。原文时间保存在 `source_estimate_minutes`；`total_minutes` 和 `active_minutes` 仍为 null。严格人数也暂时没有已核验范围。精力、预算、营养的评分/筛选尚未实现，具体能力边界见 `config/options.json`。

## 文件入口

| 路径 | 用途 |
| --- | --- |
| `AGENTS.md` | 所有开发 agent 的工作约束 |
| `docs/AGENT_TASKS.md` | 按依赖执行的任务书，可直接交给 agent |
| `docs/PRD.md` | 页面、状态、业务规则和首版范围 |
| `docs/ARCHITECTURE.md` | 来源、领域逻辑、存储、接口和小程序的边界 |
| `docs/DATA_MODEL.md` | 字段口径、身份、证据、更新与扩展方法 |
| `docs/API.md`、`contracts/openapi.json` | 后续 HTTP 服务的契约，不代表接口已运行 |
| `docs/ACCEPTANCE.md` | 56 项目标验收案例，包含尚待开发的应用能力 |
| `docs/SEED_REVIEW.md` | 30 条真实样板的逐条待审点 |
| `docs/VERIFICATION.md` | 本次已执行的验证与适用范围 |
| `data/sources/howtocook.lock.json` | 固定来源与每份原文的双重哈希 |
| `data/raw/howtocook/<revision>/` | 不可就地修改的原文 |
| `data/overlays/howtocook_seed.json` | 对照来源整理的配料、标签和证据；可维护输入 |
| `data/dictionaries/` | 食材、器具和标签 ID 字典 |
| `data/generated/recipes.jsonl` | 372 条可重建记录，每行一个 JSON |
| `data/generated/seed_recipes.jsonl` | 30 条开发样板 |
| `data/generated/catalog.json` | 菜名、身份、来源路径、状态索引 |
| `data/generated/build_report.json` | 数量、质量状态及生成文件哈希 |
| `data/generated/recipes.sqlite` | 可重建的本地镜像，不存用户业务数据 |
| `schemas/` | 数据、请求、响应、事件的机器可读校验规则 |
| `jinriheshi/` | 纯数据处理、repository 与参考推荐逻辑 |
| `tests/` | 来源、解析、版本、筛选、数据/文件边界验证 |

## 怎样扩展

增加菜谱时补 overlay 和字典，再执行 build/validate；不要直接编辑 generated。更新 HowToCook 必须显式指定完整 commit，按来源差异复核 overlay 的 revision/sha256，旧标注不会静默套到新原文。加入其他来源时新增 `SourceAdapter`，输出同一模型；推荐逻辑不认识 HowToCook 的目录或 Markdown。

JSON 与 SQLite 已实现同一个 `RecipeRepository` 接口。后续可以在该接口后接 PostgreSQL、云数据库等，API 和页面继续使用统一领域对象。Python 是当前离线数据管线与规则参考，后续 TypeScript 应用服务可以复用数据契约并按相同场景移植规则，不要求小程序运行 Python。

相同输入重复构建必须字节一致。自动导入不会把 `development` 升级到 `published`。发布工具、人工审核记录及权限控制属于后续 T02/T06，不能靠改一个字符串完成生产发布。

## 开发顺序

先执行 T00 复现基线，再冻结 T01 契约。随后可并行开展内容管理 T02、应用存储 T03、前端 mock T07；之后进行推荐、反馈、HTTP 联调与真实环境验收。具体输入、输出、依赖、验收和可粘贴指令都在 `docs/AGENT_TASKS.md`。

HowToCook 原文及许可保存在包中，见 `THIRD_PARTY_NOTICES.md`。未打包任何来源图片；源文链接不代表已经获得图片展示许可。本项目新增代码尚未选择对外开源许可。
