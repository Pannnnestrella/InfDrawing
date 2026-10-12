## 任务：多轮编辑支持透明图（RGBA）

**背景**：画布已支持透明层；Qwen 擅长透明输出，但 cedit 整图 pad/restore 会剥 alpha。需端到端保留/产出 RGBA。
**影响范围**：sizing、alpha helpers、service、Qwen 提示词、Studio 预览、docs、测试
**前置条件**：create_session 已存 RGBA；inpaint_stitch 已支持 RGBA
**规划日期**：2026-10-12

### Stage 1: 尺寸与 helpers
- **目标**：`pad_to_supported` / `restore_original_frame` / `match_source_size` 与 `alpha.py` helpers
- **成功标准**：RGBA 父图 pad→restore 后区外 alpha 可重贴；单测通过
- **状态**：Complete

### Stage 2: service 接线
- **目标**：Qwen keep_alpha + 透明 clause；Wan/Wanx flatten + `reattach_alpha`
- **成功标准**：`service.py` 按编辑器分流；sent_images / warnings 标注
- **状态**：Complete

### Stage 3: Qwen 透明友好提示词
- **目标**：`qwen_mask_prompt.py` 可复用；脚本委托同一模板
- **成功标准**：默认允许透明；`allow_alpha=False` 仍可强制不透明
- **状态**：Complete

### Stage 4: UI / 测试 / 文档
- **目标**：棋盘格预览、测试、`docs/controlled_edit.md` 透明能力表
- **成功标准**：Studio 版本图与 sent thumbs 用 checkerboard；pytest 绿
- **状态**：Complete

**待确认事项**：批准时已确认（Qwen 可出透明；Wan/Wanx 保区外 alpha；抠图非全模型默认）

## 完成记录

- **完成时间**：2026-10-12
- **实际结果**：新增 `alpha.py` / `qwen_mask_prompt.py`；sizing 支持 `keep_alpha`；service 按 Qwen vs Wan/Wanx 分流；Studio 棋盘格预览；文档透明能力表；`test_alpha_sizing.py` 通过
- **偏差**：无
