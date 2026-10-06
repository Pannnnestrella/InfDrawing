## 任务：OpenAI 指令改图

**背景**：用户选中画布图片后用自然语言描述局部修改，将原图+描述交给 OpenAI Images edits（无需 Mask）。
**影响范围**：后端 intent/API/provider/capabilities；前端侧栏模式与 flow；文档
**前置条件**：已有 OpenAI Images inpaint 与云端引擎；`INFD_OPENAI_API_KEY` 可配置

### Stage 1: 后端
- **目标**：`image_edit` 意图、`/generate/image-edit`、OpenAI edits（无 mask）
- **成功标准**：mock 下可返回图；无 Key 时 capabilities 灰显
- **状态**：Complete

### Stage 2: 前端
- **目标**：侧栏「指令改图」模式 + 选图校验 + 回贴
- **成功标准**：选图→描述→发送→画布出现结果
- **状态**：Complete

### Stage 3: 测试与文档
- **状态**：Complete

**待确认事项**：已确认 — 独立模式；固定 OpenAI；无需 Mask

## 完成记录

- **完成时间**：2026-10-04
- **实际结果**：新增 `image_edit` 全链路；OpenAI edits 无 mask；侧栏「指令改图」

