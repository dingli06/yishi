# API 契约与应用层开发说明

## 1. 当前状态与权威文件

**当前包只有离线 CLI、数据模型与纯推荐参考，没有运行中的 HTTP 服务。** `contracts/openapi.json` 是 P0 待开发接口草案，不表示以下 URL 已可访问。

当前 Schema：

- `schemas/recipe.schema.json`：内部统一菜谱数据，不能原样作为公开详情响应。
- `schemas/recommendation_request.schema.json`：CLI/领域层请求，含可注入的 context。
- `schemas/recommendation_response.schema.json`：领域推荐结果及当前公开推荐结果草案。
- `schemas/event.schema.json`：事件结构与部分条件约束。

OpenAPI 已定义 Options、PublicRecipe、会话推荐的并发版本入参和响应。event Schema 已定义明确的永久排除食材目标。token 签发、收藏读取和设置更新仍是后续应用任务；T01 对齐现有契约并补充这些流程后再冻结前后端接口。

## 2. CLI 与公开 API 的边界

| 内容 | CLI/领域层 | 小程序公开 API |
| --- | --- | --- |
| schema_version | 推荐请求要求 `1.0.0` | 创建会话当前只接 constraints/preferences；服务端构造领域请求版本 |
| context | 可注入 seen_dish_ids、recently_cooked_dish_ids、favorite_dish_ids | 客户端不能传；服务端从会话及当前主体历史读取 |
| mode | `--mode development` 或默认 production | 固定由服务端环境与权限决定；公开生产请求不能切换 |
| seed | `--seed 42` 用于可重复开发测试 | 不作为公开请求参数 |
| 身份 | 本地文件测试不代表登录 | 从可信 token 解析主体，不能信任正文里的 user_id |
| 数据资格 | 开发模式可看指定开发样板 | 生产路径仅允许 published，并检查所用字段资格 |

参考逻辑当前支持 tastes、cuisines、textures、priority_ingredients 和 novelty 的排序。没有精力/省事分值。当前种子的总时间、主动时间和人数未获得 verified 结果；严格时间/人数查询空结果是预期，不能以源文估计替代。当前 production 内容数为 0，基础查询也应返回 no_candidate。

## 3. 端点总览

| 方法和路径 | 鉴权 | 输入 | 当前草案输出 |
| --- | --- | --- | --- |
| `GET /v1/options` | 当前草案公开 | 无正文 | 200 Options，见第 8 节 |
| `POST /v1/sessions` | Bearer SessionToken | Idempotency-Key；constraints/preferences | 201 `{session_id, revision}`；422 非法条件；409 幂等冲突 |
| `POST /v1/sessions/{session_id}/recommendations` | Bearer SessionToken | session_id；Idempotency-Key；正文 expected_revision | 200 `{recommendation_id, session_revision, result}`；409 冲突；404 不存在或无权访问 |
| `GET /v1/recipes/{recipe_id}/versions/{recipe_version}` | 当前草案公开，只读公开版本 | 两个路径参数 | 200 PublicRecipe，见第 9 节；404 未发布/不存在；410 下架 |
| `POST /v1/events` | Bearer SessionToken | Idempotency-Key；event Schema 正文 | 200 `{event_id, applied}`；409 冲突；422 非法事件 |

所有变更状态的端点应在实现前补全 401、429 和服务错误响应。当前没有可用登录接口或已签发 token。T01 需定义匿名主体初始化、微信身份交换及 token 过期/撤销流程；匿名使用也必须由服务端签发绑定主体的凭证，不能使用客户端自行生成的 user_id 代替授权。

修改条件时，P0 可重新 `POST /v1/sessions` 创建新会话；旧会话及历史不被覆盖。若需要原地修改，另设计版本化更新接口并加入 OpenAPI。

## 4. 创建会话参数

### 4.1 constraints：硬条件

当前字段名与 Schema 一致。字段省略表示未提出相应限制，语义默认值必须在 T01 与服务实现中固定，不能让客户端和服务端各自猜测。

| 字段 | 当前类型/取值 | 语义和检查要求 |
| --- | --- | --- |
| max_total_minutes | 1—10080 的整数或 null | 严格总时间上限；null 不设时间上限；不是软偏好 |
| available_equipment | 器具 ID 数组或 null | null 表示未限定；空数组表示明确没有已确认器具，不能等同 null；检查必需 AND/OR 组合 |
| pantry_mode | any / only_owned / allow_missing | 不限制、仅已有食材种类、允许有限缺料；不代表库存数量足够 |
| owned_ingredients | 食材 ID 数组 | 用户已确认拥有的食材种类，未填写的调料不默认存在 |
| max_missing_ingredients | 非负整数或 null | allow_missing 的采购上限；建议要求该模式显式提供非 null 值，T01 补交叉字段校验 |
| required_ingredients | 食材 ID 数组 | 每个必须使用；区别于 priority_ingredients 的加分偏好 |
| excluded_ingredients | 食材 ID 数组 | 明确排除；复合调料成分未知不能判符合 |
| cuisines_only | 菜系 ID 数组 | 非空时只看这些菜系；未知菜系不能通过 |
| meal_forms | dish / staple / soup / breakfast / drink / dessert / condiment / semi_finished 数组 | 对应餐食形态，不能用原始目录名代替菜系 |
| standalone_meal | true / false / null | true 要求可独立成餐；false 明确要求非独立成餐；null 不设该条件 |
| servings | 1—20 的整数或 null | 严格人数条件；需要 verified 范围与适用规则；当前样板不支持可靠匹配 |
| confirmed_prerequisites | 非空字符串数组 | 当前原型以明确前提文本表达确认；不得由服务端自动全部勾选。后续建议迁移到稳定前提 ID |

格式正确但不存在的字典 ID 必须由语义校验拒绝，不能当成永远不命中的普通偏好。required 与 excluded 同时出现同一材料时，返回可定位的 422 条件冲突。未知值不能在序列化/默认值处理中变成已确认无限制。

### 4.2 preferences：软排序

| 字段 | 当前类型 | 作用 |
| --- | --- | --- |
| tastes | 味型 ID 数组 | 按已有口味标签加分 |
| cuisines | 菜系 ID 数组 | 按已标注菜系加分，不排除全部其他菜 |
| textures | 口感 ID 数组 | 按已有口感标签加分 |
| priority_ingredients | 食材 ID 数组 | 优先利用这些食材；不保证每项必须出现 |
| novelty | any / familiar / new | 使用服务端历史调整熟悉程度；新用户没有历史时不编造历史 |

当前没有 effort、energy、difficulty_preference 或软时间字段。客户端传入这些未定义字段应按 additionalProperties=false 拒绝。精力需求属于后续目标，需先扩充证据和数据再加参数。

### 4.3 当前有效的创建会话正文示例

下面是契约示例，不是已调用服务的结果：

```json
{
  "constraints": {
    "pantry_mode": "any",
    "max_total_minutes": null,
    "servings": null
  },
  "preferences": {
    "novelty": "any"
  }
}
```

HTTP 层需有 `Authorization: Bearer <服务端签发的 token>` 及 16—128 字符的 `Idempotency-Key`。占位 token 不能用于真实调用。创建成功返回的 revision 当前要求为大于等于 1 的整数。

## 5. 下一道推荐、并发与重试

请求的 session_id 必须归属于当前主体。服务端读取条件快照与历史，执行发布资格、硬筛选、软排序、随机和菜品去重，并原子地保存“已分配/曝光”与 recommendation_id。不能在推荐成功后因为事件写入失败而丢失去重状态。

当前 OpenAPI 要求正文为 `{ "expected_revision": 1 }`，expected_revision 为大于等于 1 的整数，且不能携带其他字段。新请求必须与当前会话 revision 一致。成功选菜时原子记录曝光并推进 revision，响应的 session_revision 返回已提交的版本。空结果不伪造曝光，recommendation_id 可为 null；其 revision 返回实际提交的会话状态。

处理顺序应为：先鉴权与幂等查找；同键同请求重放首次响应，包括相同 recommendation_id；未命中幂等记录时再校验 expected_revision 并执行事务。这样重试不会因会话已推进而跳到下一道。两个不同 key 同时操作同一 revision，应有一个成功、另一个明确冲突，客户端刷新状态后再决定是否发起新操作。

Idempotency-Key 的作用域为当前主体、路由及 key。草案要求至少保存 24 小时；同键不同请求体返回 409。并发冲突、幂等冲突使用不同 code，不能让客户端把所有 409 都当作成功重放。

## 6. 推荐结果解释

`result` 当前引用 recommendation_response Schema。主要字段为：

| 字段 | 含义 |
| --- | --- |
| schema_version / mode | 领域结果版本和服务端模式；公开生产固定 production |
| status | ok 或 no_candidate；正常空结果不是 HTTP 服务失败 |
| candidate_count | 硬条件及本轮规则后的候选计数，需与菜品去重口径保持一致 |
| selected | ok 时的选中公开投影；no_candidate 时为 null |
| exclusion_counts | 机器原因计数；不是互斥占比，界面不要简单求和当总数 |
| suggestions | 可选择的下一步提示；不自动改变用户条件 |
| notices | 数据资格、预览和其他必要说明 |

selected 包括 recipe_id、recipe_version、dish_id、title、publication_state、review_status、source_url、source_estimate_minutes、total_minutes、time_status、meal_form、standalone_meal、missing_ingredient_ids、selected_ingredient_ids、omitted_optional_ingredient_ids、pantry_match_scope、reasons、notices。

`pantry_match_scope=ingredient_types_only` 明确只校验种类；not_checked 不能显示食材齐全。`missing_ingredient_ids=null` 表示未检查，不能当空数组。source_estimate_minutes 与 total_minutes 分开显示；来源估计不加“已验证”标识。可选料省略与替代组选择形成推荐计划，详情显示时必须保留相应分支，不允许机械隐藏配料后留下要求使用该配料的不可理解步骤。

公开投影只保留用户需要的来源 URL、资格说明和匹配结果；不返回 raw 本地路径、完整 source manifest、overlay、reviewer、内部 issues 或未审核的图片 URL。exclusion_counts 的内部原因代码需要映射成公开允许的有限代码，不能携带内部文件名或异常堆栈。

## 7. 事件、永久拒绝与撤回版本

event Schema 当前要求：schema_version、event_id、session_id、recommendation_id、recipe_id、recipe_version、type、reason、occurred_at、scope、confirmed_permanent、permanent_excluded_ingredient_ids。

- type：shown、skip、accept、favorite、unfavorite、cooked、reject。
- reason：not_today、too_much_work、ingredients_inconvenient、recently_ate、always_dislike、just_browsing 或 null。
- scope：session、recent、permanent。
- permanent 要求 reject + always_dislike + confirmed_permanent=true，且 permanent_excluded_ingredient_ids 至少包含一个明确食材 ID。
- 非 permanent 作用域要求 confirmed_permanent=false，permanent_excluded_ingredient_ids 必须为空数组；该字段所有事件均需显式提供。
- 非 reject 事件要求 reason=null、confirmed_permanent=false；业务层还需校验合法的 type/scope 组合，不能只依靠当前 Schema 的部分条件约束。

服务器应验证推荐记录、精确版本、会话与主体的关联。occurred_at 保留用户发生时间，同时另记服务端接收时间；用户传入时间不能重排已确认的会话状态。

event_id 另设主体内唯一约束，同 ID 同正文最多应用一次；同 ID 不同正文返回 409。200 回执中的 applied 表示该逻辑事件是否已成功应用，不应被解释为“这次网络调用又应用一次”。同幂等键重试重放原响应，不重新写收藏或做过次数。

shown 需要区分服务端已分配曝光与客户端实际显示确认。服务端分配记录用于保证去重；客户端 shown 只能确认自己已获推荐，不能凭空提交其他菜谱清空或重写曝光历史。

**永久排除必须有具体目标：** permanent_excluded_ingredient_ids 只包含用户明确选择并确认的食材。服务端校验这些 ID 存在，再更新长期设置。不能把“永远不想吃这道菜”推导为永久排除该菜全部食材；没有选定具体目标时，仅记录本轮/近期拒绝。用户撤销长期排除通过后续设置接口完成，历史事件保持原样。

精确版本下架时，详情返回 410，不替换为另一版本。历史事件及收藏引用保留；展示为不可用并允许取消收藏。接受/做过等迟到事件若曾获得合法推荐，建议仍允许记录该精确历史版本，但不得重新将其加入候选；若采用拒收策略，必须在事件契约中明确。不存在或从未对用户公开的版本不能借历史接口暴露内容。

## 8. Options DTO

当前定义位于 OpenAPI `components.schemas.Options`，顶层及各层都限制额外字段。所有下列顶层字段必填：

| 字段 | 当前类型与内容 |
| --- | --- |
| schema_version | 固定为 `1.0.0` |
| published_recipe_count | 当前已发布集合的非负整数计数 |
| defaults | 包含 constraints、preferences；与创建会话字段一致 |
| groups | 分组数组，每组含 id、label、selection、options |
| groups[].selection | single 或 multiple |
| groups[].options[] | value、label、enabled；value 为相应稳定选项值 |
| capabilities | 以能力名为 key，每项必含 enabled、reviewed_candidate_count、reason；reason 可以为 null |

能力名称由 T01 统一成固定字典，例如 strict_time、servings、effort_preference、pantry、equipment。当前应反映：严格时间和人数因缺少 verified 数据不可用，精力因未实现不可用，published_recipe_count 为 0。不能因为 Schema 允许填写一个字段就把该能力标为可用。覆盖统计只基于当前服务环境允许的发布集合，不泄露开发库内部数量和备注。食材/器具选项可通过 groups 返回；若后续规模需要分页检索，再新增正式接口。

## 9. Recipe detail DTO

当前定义位于 OpenAPI `components.schemas.PublicRecipe`。不能返回 recipe.schema 的内部完整对象；公开 DTO 的字段如下，顶层字段均必填：

| 字段 | 当前内容 |
| --- | --- |
| recipe_id / recipe_version / dish_id / title | 精确身份与标题 |
| image | null 或 `{url, alt, attribution}`，attribution 可为 null，仅允许有展示资格的媒体 |
| source | name、url、license；不含本地路径与内部审核信息 |
| ingredients | ingredient_id、name、quantity_text、requirement、alternative_group；保留可选与替代关系 |
| steps | 每项 `{position, text}`，position 从 1 开始；有序受限渲染，不执行原始 HTML/脚本 |
| tags | tastes、cuisines、textures、meal_form、standalone_meal；不是直接放在顶层 |
| time | source_text、source_estimate_minutes、total_minutes、active_minutes、prerequisites、status；缺失数值为 null |
| servings | min、max、display_text，均可为 null；未确认范围不提供自动缩放承诺 |
| notices | 必要操作前提、数据口径、可选分支提示 |

器具信息可在正文和 notices 中表达；如未来需要独立的结构化器具展示，再版本化增加 DTO 字段，不能擅自返回契约外的 equipment。servings 没有独立审核状态字段，因此公开范围只能来自已经符合相应展示规则的数据，否则保留 null 并解释来源口径。

UI 必须同时使用推荐返回的 selected_ingredient_ids/omitted_optional_ingredient_ids 与详情中步骤的明确分支文案，或后续由后端提供绑定 recommendation_id 的具体执行计划。T01 确定应用层呈现方式并添加可选料/替代组端到端样例。当前 steps 的结构仅有 position/text，不能假装已经建模了可执行的条件步骤图。不能仅隐藏材料、保留冲突步骤。

## 10. 错误与补齐清单

当前统一错误对象为 `{code, message, request_id}`。建议固定公开 code 区分 validation_error、unknown_option、constraint_conflict、unauthorized、session_not_found、session_revision_conflict、idempotency_conflict、recipe_not_found、recipe_withdrawn、rate_limited、service_unavailable；这些名字属于待冻结的建议，不代表代码已实现。

正常无候选通过 200 result.status=no_candidate 表达，不用 404 或 500。404 可统一隐藏无权访问的会话；410 表示以前公开而现已下架的精确版本。错误响应不包含 token、SQL、raw 路径、内部审核备注或堆栈。

T01 与应用实现至少完成：

1. 按已有 Options/PublicRecipe 输出投影，验证公开推荐响应不泄露内部字段。
2. 实现已有 expected_revision/session_revision 语义、并发失败与幂等重放样例。
3. 匿名主体/微信身份 token 流程、过期与撤销语义。
4. 收藏列表读取、常用设置读取/修改/清空，落实 permanent_excluded_ingredient_ids 的确认与可撤销更新。
5. 事件合法 type/scope 组合、shown 与分配曝光的关系、下架版本迟到事件策略。
6. 字典 ID 存在性、互斥条件、allow_missing 上限与所有输入长度限制。
7. 精力和软时间继续保持未开放，直至数据、契约与规则一同实现。

完成后更新 OpenAPI 与 Schema、生成前后端类型、验证全部样例，并在 `AGENT_TASKS.md` 的 T01 记录真实完成结果。
