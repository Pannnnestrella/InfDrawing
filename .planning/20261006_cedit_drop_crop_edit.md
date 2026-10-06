## 任务：取消生成侧 crop-edit-paste，统一整图 + 参考图 + 区域提示

**背景**：局部裁块改完再贴回容易出矩形残影、构图漂移；用户希望改为始终送完整当前图，再附局部参考图，并在 prompt 里标明要改的区域。截图中左侧「上一版」矩形更可能是对比滑块，但生成路径仍应去掉 crop。
**影响范围**：
- `backend/app/controlled_edit/service.py`：去掉 `uses_local_crop` / `paste_edited_crop` 分支
- `backend/app/controlled_edit/region_ops.py`：可保留 `bbox_prompt_lines` / framing；`uses_local_crop`/`paste_edited_crop` 删除或标废弃
- `backend/app/controlled_edit/prompt_compiler.py`：强化「整图 + 目标框 + 参考图」说明（如需要）
- 相关单测与 `docs/controlled_edit.md`
**前置条件**：硬贴回已默认关；锁定锚点仍作为参考图；bbox 行已写入 prompt

### Stage 1: 生成始终整图
- **目标**：`_execute_turn` 只对完整 `parent_bytes` 做 pad → `multi_image_edit` → restore；不再 crop 目标框
- **成功标准**：单测中编辑器收到的主图尺寸等于整帧（非剑/盾小图）；`uses_local_crop` 不再被 service 调用
- **状态**：Complete

### Stage 2: 参考图与区域提示保持
- **目标**：锁定实体的锚点 crop 仍作参考图；目标实体的归一化框继续写进 prompt；文档写明「完整当前图 + 局部参考 + 改哪里」
- **成功标准**：文档与 prompt 单测仍覆盖 bbox 行与 primary_last 参考图编号
- **状态**：Complete

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：生成路径始终整图；删除 `uses_local_crop` / `paste_edited_crop`；锁定锚点仍作参考图；目标框写进 prompt。`tests/controlled_edit` 72 通过。
- **偏差说明**：无额外新单测断言主图像素数；构图漂移阈值未改。

---

**待确认事项**：
- [x] 彻底取消生成侧裁剪改贴回
- [x] 锁定时裁的锚点参考图是否保留？（建议保留——这是「局部参考图」，不是把编辑结果贴回）
- [x] 构图漂移阈值是否一并放宽？（本任务可不改，另议）
