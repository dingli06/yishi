# 数据模型与维护规则

## 1. 三类文件与单向生成

`raw` 保存原始 bytes，`overlays` 保存可审阅的补充标注，`generated` 是两者和字典经过构建后的结果。来源文件只读；改正标注、字典或解析器，再生成新版本。`scripts/generate_contracts.py` 是当前 Schema/OpenAPI 的生成源，修改契约时同步脚本、生成文件、示例和文档。

全量 372 条规范记录不意味着已经完成 372 条配料标签。只有 30 条有当前 overlay，其余 342 条保留来源、章节与步骤并处于 draft。

## 2. 顶层字段

| 字段 | 含义与约束 |
| --- | --- |
| `schema_version` | 数据契约版本，与应用包版本、来源 commit 分开 |
| `recipe_id` | 来源条目的稳定身份；UUIDv5 派生，不使用数组位置 |
| `dish_id` | 菜品身份，用于同菜不同做法的聚合和去重 |
| `recipe_version` | 除版本自身以外完整有效记录的 canonical SHA256 摘要；记录变更产生新版本 |
| `source` | 来源 ID、原条目标识、修订、正文 SHA256、URL、原文路径、许可、adapter版本 |
| `publication` | draft/development/published/withdrawn，以及人工发布审核人和时间 |
| `source_category` | 保留来源目录分类；不是统一菜系或素食结论 |
| `content` | 原始介绍、完整二级章节、步骤块与原文图片引用；不是全部可直接公开的 DTO |
| `ingredients` | 标准食材引用、原名、用量原文、角色、必需性、替代组、证据 |
| `tags` | 口味、菜系、口感、餐食形态、是否独立成餐 |
| `equipment` | 必需 AND 条件、每组至少一个的 OR 条件、审核状态及证据 |
| `time` | 源文估计、已核验总时间、主动时间、前提和状态 |
| `servings` | 原份量说明、核验范围、缩放策略；未核验数字为 null |
| `nutrition`、`cost` | 1.0.0 暂为 unknown/null；有依据后升级契约 |
| `review` | agent 对照状态、材料完整性、待审问题、是否实烹 |
| `tag_evidence` | 标签字段、具体值、原文片段和章节 |
| `extensions` | 有命名空间的实验扩展；未经正式契约支持不参与硬筛选 |

`source.revision` 是不透明的来源版本字符串；`blob_sha` 允许 null，以支持非 Git 来源。HowToCook adapter 及语义校验仍要求完整 Git commit 和 Git blob 校验。不能让通用模型依赖某家供应商的字段。

## 3. 身份和版本

初始 `recipe_id` 以 `howtocook:<source_path>` 派生；初始 `dish_id` 按规范标题生成。多来源接入、改名或合并应使用 `data/identity/overrides.json`，不得根据模糊相似度自动合并。

来源移动路径时，`source_key_aliases` 的方向是 **新来源 key → 旧稳定 key**，使 recipe_id 延续。原文来源路径仍记录新位置，因此 recipe_version 正常变化。`dish_id_overrides` 将来源 key 指到人工确认的菜品身份，适合多来源同菜与标题更正。

反馈、收藏和推荐详情须保存 `recipe_id + recipe_version`。同一轮排重按 dish_id。当前 SQLite 只是一个可重建快照；未来生产库需要保留历史版本与下架状态，不能用每次重建抹去用户事件引用。

## 4. 配料与库存

角色 `main/seasoning/other` 和必需性 `required/optional/alternative/unknown` 相互独立。调料可以是必需材料。`alternative_group` 表示同一组至少使用一个已审核选项，组成员至少两项；不得在运行时随意发明替代。

食材字典保留状态：生米与熟饭、干货与鲜货分别建 ID；明确同义词才放 aliases。数量先保留原始表达式和单位文本，不把“适量”或每份公式伪解析为精确克数。

现有库存条件只有食材 ID，因此 only_owned 表示“必需食材种类匹配”。数量是否足够仍由用户核对。未来增加严格数量模式，必须补数值、单位换算、份量和不可比较值处理。

复合调料 `component_status=unknown` 时，不用于断言满足某食材排除。明确成分可通过 components 引用其他食材；推荐递归检查并防止循环引用。普通偏好不等于过敏安全承诺，当前没有医疗用途保证。

## 5. 时间、器具和缺失值

`source_estimate_minutes` 仅记录来源的估计及其原文。严格时间要求 `status=verified`、完整总时间区间、实烹记录标志和满足前提，使用区间上界比较。30 条样板尚未达到该条件，不能用源文数字冒充总时间。

器具表达为 `required_all` 全部满足，并对 `required_any` 中每一个组各满足至少一件。空数组在 `status=unknown/needs_review` 下不能解释为“无需器具”。开发模式可使用 agent_checked 候选，生产硬筛选要求 verified。

标签空数组表示没有可用标签证据，不表示已经证明无辣味或不属于所有菜系。布尔型未知用 null。所有严格条件需要的字段未知时，候选不通过。

## 6. 发布与预览

`agent_checked` 只说明代理对照了原文，不能推导为真人审核、试做或完整安全审查。`needs_review` 记录当前可解释冲突。开发预览始终显式开启，并返回开发提示。

生产推荐要求 published、approved 以及非代理的审核人/时间。用到配料、器具、时间或人数等硬条件时，再检查该用途字段的资格。当前包没有生产发布记录，默认生产返回空结果是预期行为。

字段检查和权限检查是不同问题。未来发布入口需要真实操作主体、权限、审计日志和版本更新，不能允许客户端自报审核状态。

## 7. 更新与迁移

更新 HowToCook 时指定完整 revision，先下载至新快照目录并校验，不覆盖旧 raw。旧 overlay 的 source_revision 或 source_sha256 不匹配会中止构建，保持之前生成文件；审核者应依据差异逐条确认后更新 overlay。不能仅替换哈希来绕过复核。

字段有破坏性变化时升级 Schema，提供旧数据到新数据的迁移、迁移前备份、回滚和契约测试。未知字段默认禁止，实验字段放 extensions；上线使用前转为正式字段并明确缺失值语义。

构建先在内存完成全批校验，再原子替换各文件，最后写 `build_report.json` 作为提交标记。JSON repository 校验文件哈希，不接受缺失标记或中断构建产生的不一致文件。未来高并发服务应以不可变快照目录加原子指针切换整个数据集。

## 8. 媒体与公开详情

没有下载来源图像。content.image_refs 是追溯线索，不能直接作为已授权展示图。后续采用自有或明确授权图片，独立记录权利和署名。API 的 PublicRecipe 只暴露审核后的展示字段；不能直接序列化整个 canonical record。

Markdown/HTML 视为不可信来源内容；页面渲染需要安全的展示转换。解析保留 HTML 注释便于审核，并不要求客户端执行或原样渲染它们。原文功效描述也需展示审核。
