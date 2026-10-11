## 任务：画布设置页（API 选项可见化）

**背景**：API Key 弹层被侧栏裁切（已单独修显示）；更根本的问题是大量调用侧选项（引擎、可控编辑策略、上游模型等）散落在 env / Studio / EngineSelect 中，画布用户不可见。需要一个统一设置入口，让常用选项可查看、可改、可持久化到会话。

**影响范围**：
- 新增：`frontend/src/settings/*`（设置浮层 / 分区组件 / 偏好 store）
- 修改：侧栏 header（齿轮入口）、`ChatPanel` / `EngineSelect`（与设置同步）、可选复用 `studio-turn-options`
- 后端（可选 Stage）：`GET /system/settings-schema` 暴露可读默认值与可选枚举（不写回 `.env`）
- 规划与会话状态：`.planning/`、`.cursor/task_plan.md`

**前置条件**：
- API Key / 环境状态弹层已改为 fixed 定位（本轮显示 bug 修复）
- `engine-preference`、`studio-turn-options`、`/system/capabilities` 已存在

### Stage 1: 设置浮层骨架 + 迁入已有项
- **目标**：侧栏增加「设置」入口；浮层分区展示并编辑：
  1. **访问凭证** — InfDrawing session API Key（迁入/复用现逻辑）
  2. **生图引擎** — auto / local / cloud + 云厂商（与 `EngineSelect` 双向同步）
  3. **环境状态** — capabilities 只读摘要 + 刷新
- **成功标准**：打开设置不被裁切；改引擎后 Composer 立即反映；刷新页面 session 偏好仍在
- **状态**：Complete

### Stage 2: 可控编辑与调用选项可见
- **目标**：设置中增加「可控编辑」分区，暴露当前对 API 有影响、用户应能选的项：
  - `prompt_style`：`preserve` / `target_only`（与 Studio 共用 session 存储）
  - `image_provider`：`dashscope` / `openai`（按 capabilities 过滤不可用项）
  - 只读展示：当前 vision / image model 名（来自 capabilities.models）
- **成功标准**：画布侧发起的 controllable edit 请求带上用户所选 style/provider；Studio 与设置页选项一致
- **状态**：Complete

### Stage 3（可选）: 高级 / 说明
- **目标**：折叠「高级」区，说明项而非全量 env 编辑：
  - 本地 ComfyUI URL 状态、GPU 摘要
  - lock_paste / feather 等若前端已有开关则迁入，否则仅文档式说明默认值
  - 「关于」：app 名、环境 tier、调试开关只读
- **成功标准**：无密钥输入框写入服务端 `.env`；敏感项只显示「已配置 / 未配置」
- **状态**：Not Started

---

## 设置页建议内容（产品清单）

### A. 必须有（demo 用户会改）

| 分区 | 内容 | 存储 |
|------|------|------|
| 访问凭证 | InfDrawing API Key；清除 | sessionStorage |
| 生图引擎 | 模式 auto/local/cloud；云厂商 openai/dashscope… | sessionStorage（现有） |
| 可控编辑 | 提示词策略、图像提供商 | sessionStorage（与 Studio 共用 key） |
| 环境 | GPU / ComfyUI / DeepSeek / Ollama 状态 | 实时 GET capabilities |

### B. 建议只读展示（避免误配）

- 当前意图模型 / 视觉模型 / 生图模型名称
- 上游密钥是否已在服务端配置（DeepSeek / OpenAI / DashScope）
- 环境 tier、debug、auth_required

### C. 暂不放进 UI（仍用 `.env`）

- 真实上游 API Key 明文编辑、数据库/Redis/S3、队列与限流、阈值阈值与内部阈值

### D. 交互形态

- **浮层 / 抽屉**挂在画布 shell（非独立路由），避免打断无限画布
- Header：`设置` 齿轮；API Key / 环境芯片可保留为快捷入口，或改为打开设置对应分区
- 分区用左侧导航或纵向 section，一屏内扫完核心项

---

**待确认事项**：
1. ~~交互形态~~ → 浮层抽屉
2. ~~Stage 范围~~ → Stage 1–2 先做；Stage 3 以后
3. ~~API Key 芯片~~ → 并入设置页，Header 不再单独放
4. Stage 2：画布对话栏 controllable edit 请求同步带上设置中的 style/provider

## 完成记录

- **完成时间**：2026-10-11
- **实际结果**：
  - Header `API Key` 芯片改为「设置」入口；`SettingsDrawer` 浮层含凭证 / 生图引擎 / 可控编辑 / 环境
  - 引擎与 `EngineSelect` 共用 ChatPanel state；cedit 选项经 `subscribeCeditOptions` 与 Studio 同步
  - `/studio` 页面 Header 同样挂设置入口
- **偏差**：Stage 3 高级项未做（按确认延后）
