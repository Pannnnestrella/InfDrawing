## 任务：新增 target-only 精简提示词策略（默认保留原策略）

**背景**：长篇「勿改非目标」可能干扰编辑模型；用户要求保留现有 preserve 策略，并增加只描述修改区域的新策略。
**影响范围**：
- `backend/app/config.py`：`INFD_CEDIT_PROMPT_STYLE` = `preserve` | `target_only`（默认 `preserve`）
- `backend/app/controlled_edit/prompt_compiler.py`
- `backend/app/controlled_edit/service.py`：传入配置
- 单测、`docs/controlled_edit.md`、capabilities 可选暴露
**前置条件**：prompt 编译与参考图编号已稳定

### Stage 1: 双策略编译
- **目标**：`preserve` 保持现状；`target_only` 只写改动描述/目标/框 + 有锚点参考图的短句 + 勿粘贴参考图说明
- **成功标准**：两套单测；默认行为与改前一致
- **状态**：Complete

---

**待确认事项**：
- [x] 默认保留原策略；新策略可配置开启

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：`INFD_CEDIT_PROMPT_STYLE=preserve|target_only`，默认 `preserve`；`target_only` 只写改动/目标框 + 有锚点参考图短句。能力探测暴露 `prompt_style`。
- **偏差说明**：无前端切换 UI，靠环境变量。
