## 任务：整图改模型框纳入 Qwen 2.1

**背景**：Qwen 2.1 整图改已用同步 multimodal 验证可跑通；Studio 模型框目前只暴露默认 `cedit_image_model`（多为 2.0）与 OpenAI，用户要可选 2.1。
**影响范围**：capabilities、schemas、service、qwen edit provider、controlled-edit-api、studio-turn-options、EditComposer、StudioWorkspace、VersionDetails、相关测试。
**前置条件**：`20261012_qwen21_fullframe_probe` 同步成功。
**整体状态**：Complete

### Stage 1: 能力列表与按轮模型
- 目标：`image_options` 增加 `dashscope|qwen-image-2.1-pro`；turn 接受并落盘 `image_model`；editor 按轮覆盖模型。
- 状态：Complete

### Stage 2: 前端按模型选择 + 2.1 走同步
- 目标：选择框以 `provider|model` 为值；偏好写入 sessionStorage；2.1 默认同步调用（不再强制异步）。
- 状态：Complete

### Stage 3: 测试
- 目标：相关 pytest / vitest / tsc / Ruff。
- 状态：Complete

## 完成记录
- 2026-10-12：Studio/设置页整图模型框可选默认 Qwen + `qwen-image-2.1-pro` + OpenAI；`image_model` 按轮落盘；2.1 Studio 路径改同步 multimodal。后端 41 + 前端相关测试通过。
