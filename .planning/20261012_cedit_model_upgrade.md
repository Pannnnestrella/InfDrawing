## 任务：多轮编辑拥抱新模型（保留现有流程）

**背景**：官方将 `wanx2.1-imageedit` 标为 Legacy；整图主推 Qwen 3.0 / Wan 2.7。需在不拆现有三条流程的前提下换引擎并扩大选择框。
**影响范围**：config、capabilities、service 路由、Wan 2.7 adapter、Studio 选择框/文案、docs、测试
**前置条件**：现有 crop/fullframe Mask、自动小物件路由、Qwen 多图编辑
**规划日期**：2026-10-12

### Stage 1: 契约与选择框
- **目标**：默认 `qwen-image-3.0-pro`；`image_options` 完整列表；前端分组标签
- **状态**：Complete

### Stage 2: Wan 2.7 适配器
- **目标**：整图编辑 + `bbox_list`；mock 测试 + 付费探针
- **状态**：Complete

### Stage 3: service 路由
- **目标**：自动局部默认 `wan27_bbox`；显式 Mask 仍 wanx2.1；文案与 sent_images
- **状态**：Complete

### Stage 4: 文档与 Review
- **目标**：controlled_edit.md；Review Gate
- **状态**：Complete

**待确认事项**：用户已批准规划（含付费探针）。

## 完成记录

- **完成时间**：2026-10-12
- **实际结果**：默认整图 `qwen-image-3.0-pro`；自动局部 `wan2.7-image-pro`+bbox；显式 Mask 仍 Legacy wanx2.1；选择框含 Qwen 3.0/2.x 与 Wan 2.7；探针 `qwen30_full` 15s、`wan27_bbox` 20s 均成功
- **Review**：正确性——三条路径分流清晰；规范——type hints/测试；测试——wan27 mock + 原有 local 测试通过；风险——Wan 2.7 输出缩放后 LANCZOS 对齐、账号未开通时自动局部会失败需回退 `wanx21_mask`
