## 任务：多轮可控生图（Controlled Multi-turn Edit）

**背景**：现有「指令改图」（`image_edit`）是单轮、无记忆的。用户多轮修改同一张图时，角色的脸、道具等关键元素会逐轮漂移，也无法回看历史。本功能做成一个独立模块（独立路由 + 独立 scope `controlled_edit`），便于后续做权限区分。它在语义层记住"哪些东西不能动"，再通过提示词控制、参考图锚定和 VLM 自动验收来约束模型，用修改树（版本 DAG）兜底，用户随时可以回退或分支。不使用像素级 mask。

**影响范围**：

后端（新增，均位于 `backend/app/controlled_edit/`）：
- `schemas.py`：实体、实体状态、版本节点、会话、意图、验收结果等 Pydantic 模型
- `repository.py`：会话 / 版本 / 实体状态仓储（Memory + SQL 双实现，沿用现有 `Memory*Repository` / `Sql*Repository` 模式）
- `scene_parser.py`：VLM 场景解析 → 实体树（名称、层级、粗略 bbox）
- `intent_parser.py`：LLM 解析用户指令 → target / operation
- `prompt_compiler.py`：根据实体状态和意图生成编辑 prompt（Change only / Preserve exactly / Do not modify），并组装参考图列表
- `anchors.py`：按 bbox 裁剪 LOCKED 实体的参考 crop，锚点取自该实体被锁定时的版本
- `verifier.py`：VLM 对比新旧图打分（目标是否生效、各 LOCKED 实体是否保持）
- `service.py`：一轮编辑的编排（解析 → 编译 → 生成 → 验收 → 失败重试 → 写入版本节点）
- `api.py`：`/api/v1/controlled-edit/*` 路由

后端（修改）：
- `app/pipeline/image_providers/openai_images.py`：新增多图输入的编辑方法；按原图比例选择 `1024x1024` / `1536x1024` / `1024x1536`，生成后还原到原尺寸。现有 `image_edit` / `inpaint` 行为不变
- `app/production/models.py`：新增 `edit_sessions`、`edit_versions` 表
- `app/production/jobs.py`、`app/worker.py`：新增 job 类型 `controlled_edit`
- `app/main.py`：挂载新路由，依赖 `require_scopes("controlled_edit")`
- `app/system/capabilities.py`、`app/system/schemas.py`：新增 feature `controlled_edit`（需要 OpenAI Key，因为 VLM 和生图都依赖 OpenAI）
- `app/config.py`：新增 `INFD_CEDIT_*` 配置（VLM 模型名、验收阈值、最大重试次数）

后端测试（新增，镜像结构）：`backend/tests/controlled_edit/test_*.py`

前端（新增，位置待确认，见文末）：
- 独立页面或面板：上传原图、实体面板（锁定 / 确认 / 可编辑三态切换）、指令输入、修改树、版本前后对比
- `src/lib/controlled-edit-api.ts`：API 客户端与类型

文档：`docs/controlled_edit.md`（英文）

**前置条件**：
- 已有 OpenAI Images edits 链路（`20261004_openai_image_edit.md`）
- 已有 artifact 存储、jobs/worker 异步体系、scope 鉴权
- `INFD_OPENAI_API_KEY` 已配置（VLM 用 `gpt-4o-mini` 一类的视觉模型；DeepSeek 不支持图像输入，所以本功能不走 DeepSeek）

---

### 核心设计

**实体状态（挂在每个版本节点上，不做全局单例）**

| 状态 | 在 prompt 中的作用 | 参考图锚定 | 验收 |
|---|---|---|---|
| LOCKED | 写入 "Preserve exactly / Do not modify" | 附带锁定时那一版的 crop | 必检，低于阈值判定失败 |
| APPROVED | 写入 "Keep unchanged unless asked" | 不附带 | 检查后只给警告 |
| EDITABLE | 不额外约束 | 不附带 | 不检查 |

- preserve 列表由程序根据 LOCKED / APPROVED 实体确定性生成，不交给 LLM 决定
- 指令的 target 命中 LOCKED 实体时，API 返回冲突，前端提示用户先解锁

**一轮编辑流程**
1. 意图解析：LLM 输入为指令 + 当前实体表，输出 target、operation（add / remove / replace / restyle / recolor）、改动描述
2. Prompt 编译：套用固定模板，参考图顺序为 [当前图, LOCKED crop 1, crop 2, ...]，并在 prompt 里写明 "the face must match reference image 2"
3. 生成：调用 OpenAI edits（无 mask、多图输入），先试 `input_fidelity="high"`，接口不支持就自动去掉该参数
4. 验收：VLM 对比新旧图，输出 `target_applied: bool`，以及每个 LOCKED 实体的 `preserved_score: 0-1`
5. 不通过时自动重试（默认最多 1 次，重试时 prompt 里补充失败原因）；仍不通过就照常落盘，但在节点上打警告标记
6. 增量重解析：VLM 更新实体表（例如多了 hat），继承上一版的实体状态，写入新版本节点

**修改树（版本 DAG）节点字段**
`id`、`parent_id`、`image_artifact_id`、`instruction`、`intent`、`compiled_prompt`、`reference_artifact_ids`、`entities`（含状态快照）、`verification`（分数 + 是否重试 + 警告）、`created_at`。
从任意节点继续编辑就会自然形成分支；"回退"只是切换当前节点，不删除任何历史。

---

### Stage 1: 领域模型与仓储
- **目标**：`schemas.py`、`repository.py`（Memory + SQL）、`edit_sessions` / `edit_versions` 表
- **成功标准**：单测覆盖会话创建、追加版本、分支、按会话取整棵树、实体状态继承
- **状态**：Complete

### Stage 2: VLM 场景解析 + 意图解析
- **目标**：`scene_parser.py`、`intent_parser.py`，输出结构化 JSON，并做 schema 校验
- **成功标准**：mock VLM 下单测通过；非法 JSON 或越界 bbox 能给出可定位的报错；用真实 key 跑 1 张样例图，人工检查实体树是否合理
- **状态**：Complete

### Stage 3: Prompt 编译 + 参考图锚定 + Provider 扩展
- **目标**：`prompt_compiler.py`、`anchors.py`；OpenAI provider 增加多图编辑和比例处理
- **成功标准**：单测断言 prompt 中包含所有 LOCKED 实体，参考图顺序正确；非方图输出尺寸与原图一致；现有 `image_edit` 测试不回归
- **状态**：Complete

### Stage 4: VLM 验收 + 编排 + 异步 job
- **目标**：`verifier.py`、`service.py`，接入 jobs/worker（job 类型 `controlled_edit`）
- **成功标准**：mock 下覆盖三条路径：验收通过、失败后重试成功、重试仍失败但打警告落盘；每轮产生一个新版本节点
- **状态**：Complete

### Stage 5: API、权限、能力探测
- **目标**：`api.py`（建会话并解析、提交一轮编辑、取版本树、修改实体状态、切换当前节点），scope `controlled_edit`，capabilities feature
- **成功标准**：缺少 scope 时返回 403；没有 OpenAI Key 时 capabilities 灰显并给出原因；接口在 `/docs` 可见
- **状态**：Complete

### Stage 6: 前端工作台
- **目标**：上传 → 实体面板 → 指令输入 → 修改树（点击预览、前后滑块对比、从此节点继续）→ 验收警告展示
- **成功标准**：在浏览器里完成至少 3 轮编辑，包含一次分支和一次回退；没有权限时入口隐藏或灰显
- **状态**：Complete

### Stage 7: 端到端验证与文档
- **目标**：用真实 key 跑一组样例（例如：戴巫师帽 → 背景换成万圣夜 → 加南瓜），记录每轮验收分数；撰写 `docs/controlled_edit.md`
- **成功标准**：实验记录写入 `data/logs/20261005_controlled_edit_e2e/`（配置、分数、截图路径）；后端测试和前端 lint 全部通过
- **状态**：Complete

---

**待确认事项**：
- [x] 前端入口：独立页面 `/studio`（推荐，权限隔离最清楚，修改树有足够空间），还是在现有画布里加一个独立模式或浮动面板？→ 独立页面 `/studio`
- [x] 验收失败时的自动重试次数：默认 1 次是否合适？每次重试都会多花一次生图费用 → 1 次
- [x] VLM 模型：沿用 `INFD_OPENAI_MODEL`（当前是 `gpt-4o-mini`），还是为本功能单独配一个更强的视觉模型（如 `gpt-4o`）来提高验收准确度？→ 单独配置 `INFD_CEDIT_VISION_MODEL`，默认 `gpt-4o`
- [x] 本期不做：像素级 mask、bbox 贴回、DashScope / ComfyUI 作为本功能的 provider（接口会预留）

## 执行决策（2026-10-05，用户回复 go 后）

- **执行方式调整**：一轮编辑改为在 API 进程内以后台任务运行（与现有 `/generate` 的开发路径一致），前端轮询版本节点状态（pending → running → succeeded / failed）。原因：arq 的 jobs/worker 依赖 Redis，本地开发环境没有 Redis。编排逻辑 `run_turn` 写成独立函数，后续接 worker 只需加一层 handler。因此 Stage 4 不修改 `app/production/jobs.py` 和 `app/worker.py`。
- **意图解析放在提交接口里同步执行**：这样锁定冲突可以立刻以 409 返回，无需等后台任务。
- **前端修改树不引入新依赖**：用纯 SVG/CSS 实现树布局，不安装 React Flow。
- **比例处理**：provider 只负责按给定尺寸调用；pad 到支持比例、再裁回原尺寸的逻辑放在 `app/controlled_edit/sizing.py`。
- **测试目录**：`backend/tests/controlled_edit/`，文件名统一加前缀 `test_cedit_*`，避免与现有平铺测试重名。

## 完成记录

**完成时间**：2026-10-05

**实际结果**：
- 后端：`backend/app/controlled_edit/` 下共 12 个模块（schemas、repository、entities、vision、scene_parser、intent_parser、sizing、anchors、prompt_compiler、verifier、service、api）；新增迁移 `0002_controlled_edit`；`openai_images.py` 新增 `multi_image_edit`；路由挂在 `require_scopes("controlled_edit")` 下；capabilities 新增 `controlled_edit`。
- 前端：`/studio` 页面，包括上传与历史会话、实体三态面板、指令输入（锁定冲突时可一键解锁重试）、SVG 修改树、前后滑块对比、验收详情（构图和各实体分数、参考图、实际发送的提示词）；画布侧栏在有权限时显示 Studio 入口。
- 测试：后端 140 项全部通过（新增 48 项），Ruff 通过；前端 tsc、ESLint 通过，vitest 48 项通过。
- 端到端：`scripts/cedit_e2e.py`，记录在 `data/logs/20261005_controlled_edit_e2e/`（第一次运行、`run2/`、`run3/`），三轮均通过验收，每轮约 60–70 s。
- 浏览器：在 `/studio` 打开会话 → 回退到 v2 → 从 v2 分支生成 v5（加黑猫），修改树正确显示分支。
- 文档：`docs/controlled_edit.md`

**偏差说明**：
- 执行方式：未接 arq worker，一轮编辑在 API 进程内后台运行（见上方「执行决策」）。
- 场景 bbox 改用 `box_2d`（0–1000 网格，`[x_min, y_min, x_max, y_max]`）。第一次运行时 gpt-4o 给出的 xywh 框过粗，而且没有列出 face。
- 验收在原方案基础上新增两项：一是构图评分（阈值 0.75），二是锁定实体同时与锁定时的锚点 crop 比对，有效分取两者中的较小值。原因是 run2 出现镜头推近、腿被裁掉、表情改变，验收仍全给 1.0。
- 新增传输层重试：第一次运行时 OpenAI 偶发 `ReadError`，导致一轮直接失败。
- 锚点 crop 的 padding 从 0.08 调到 0.15。

**遗留问题**：
- gpt-4o 验收偏宽松：run3 的 v2 有明显推近，构图仍给 1.0；多轮后画面纹理会出现噪点式退化，验收也未识别。后续可以考虑用重解析得到的主体 bbox 做确定性构图检查，或换更强的验收模型。
- 没有数据库时，会话只保存在内存里，重启后端会丢失。
