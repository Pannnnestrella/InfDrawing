## 任务：Studio 提示词策略 + 生图模型选择框

**背景**：提示词已有 `preserve` / `target_only`；生图默认阿里 `qwen-image-edit-plus`、可切 OpenAI。用户希望在页面上用下拉框切换，不必改 `.env`。
**影响范围**：
- `EditTurnRequest`：可选 `prompt_style`、`image_provider`（`dashscope` | `openai`）
- `service`：本轮覆盖；缺省回落 `settings`
- `capabilities.controlled_edit.models`：暴露可选列表与当前默认
- `EditComposer` / `StudioWorkspace`：两个下拉框，`sessionStorage` 记住选择
- 前端 `FeatureCapability.models` 类型补齐
- 单测与文档
**前置条件**：双策略编译、DashScope/OpenAI 双编辑器已落地

### Stage 1: 后端按轮覆盖
- **目标**：
  - `prompt_style` ∈ `{preserve, target_only}`
  - `image_provider` ∈ `{dashscope, openai}`；选 dashscope 需已配阿里 key，否则 409/422
  - 未传字段用 settings 默认
  - capabilities 增加 `image_options`（如 `dashscope|qwen-image-edit-plus` / `openai|gpt-image-1`）与当前 `prompt_style` / `image_provider`
- **成功标准**：单测覆盖覆盖、回落、缺 key 拒绝
- **状态**：Complete

### Stage 2: 前端双下拉框
- **目标**：编辑区提供
  1. 提示词：`完整约束` / `仅描述目标`
  2. 生图模型：`通义 qwen-image-edit-plus` / `OpenAI gpt-image-1`（仅展示 capabilities 里可用的项）
  - 选择记入 sessionStorage；提交 turn 时带上
- **成功标准**：切换后下一轮使用对应策略与编辑器（版本详情可见 compiled_prompt；模型可从日志/provider 行为区分）
- **状态**：Complete

---

**待确认事项**：
- [x] UI 为编辑区下拉框
- [x] 提示词文案：`完整约束` / `仅描述目标`
- [x] 生图选项先只做这两档（阿里 plus / OpenAI gpt-image-1），不开放任意模型名输入

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：
  - 后端：`EditTurnRequest` / `EditVersion` 存本轮 `prompt_style`、`image_provider`；缺省回落 settings；未配置编辑器返回冲突/不可用；capabilities 暴露 `image_options`、`prompt_style`、`image_provider`
  - 前端：`EditComposer` 双下拉；`sessionStorage` 键 `infd.cedit.prompt-style` / `infd.cedit.image-provider`；版本详情展示策略与模型
  - 质量门禁：`tests/controlled_edit` 76 通过；前端 vitest / tsc / eslint 通过
- **偏差说明**：无
