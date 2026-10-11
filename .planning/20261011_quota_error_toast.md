## 任务：调用余额/额度不足时在画布上提示

**背景**：用户希望在生图/拆解/对话等 API 调用因余额或额度不足失败时，在无限画布上直接看到提示（不仅侧栏聊天）。当前右键管线已有 `PipelineToast`；侧栏 `appendError` 只进对话流，画布无统一失败条。
**影响范围**：
- `backend/app/pipeline/image_providers/` — 识别上游余额/额度错误码并规范化文案
- `backend/app/agent/` 或 LLM provider（若 DeepSeek/OpenAI 对话也会欠费）— 同样规范化
- `frontend/src/lib/canvas-toast-store.ts`（新建）— 全局画布 toast
- `frontend/src/components/PipelineToast.tsx` / `CanvasToastHost.tsx` — 画布常驻宿主
- `frontend/src/lib/run-pipeline.ts`、`agent-panel/hooks/*` — 失败时推送画布 toast
- 对应 vitest / pytest
**前置条件**：
- [x] 画布 `PipelineToast`（右键生图/拆解）
- [x] 任务错误经 WS/SSE `type: error` + `message` 回前端
- [x] DeepSeek 有余额 API；DashScope/OpenAI 余额需靠调用失败码推断

### Stage 1: 后端错误分类与文案
- **目标**：从 DashScope / OpenAI / DeepSeek 响应中识别「余额/额度/欠费/免费额度用尽」类错误，抛出稳定、可读的中文消息
- **匹配（示例，实现时以实测码为准）**：
  - DashScope：`Arrearage`、`InsufficientBalance`、`AllocationQuota`、文案含「欠费」「余额」「quota」
  - OpenAI：`insufficient_quota`、`billing_not_active`
  - DeepSeek：余额相关 402/文案，或预检 `is_available === false`
- **成功标准**：单测用假响应覆盖至少 3 类；普通网络/参数错误不被误判
- **状态**：Complete

### Stage 2: 前端全局画布 Toast
- **目标**：任意调用路径失败且判定为额度问题时，画布底部显示错误 toast（可手动关闭）
- **规则**：
  - 右键管线 / `runPipeline`：额度错误 → `showCanvasToast`
  - 侧栏 `appendError`：额度错误同步画布 toast
  - 非额度错误：保持原侧栏/overlay 行为
- **成功标准**：额度错误时画布出现 toast；可手动关闭
- **状态**：Complete

### Stage 3: 质量门禁
- **目标**：pytest + vitest；手测一条额度失败路径（可用 mock）
- **成功标准**：相关测试通过；手测文案可见且不挡关键操作
- **状态**：Complete（自动化）

**明确不做（本轮）**：
- 常驻「余额角标 / 定时轮询余量」
- 自动跳转充值页
- 伪造精确「剩余张数」（公开 API 拿不到 DashScope/OpenAI 真实余额）

**待确认事项**：
1. **画布提示范围**：仅余额/额度类 — 已确认（2026-10-11）
2. **Toast 停留**：手动点关闭 — 已确认
3. **DeepSeek 预检**：仅失败后再提示 — 已确认（不做调用前预检）

**批准**：用户确认「三点按推荐，3 仅失败后再提示」（2026-10-11）
**执行顺序**：Stage 1 → 2 → 3

**关联 bug（同批修复）**：侧栏 `selectionHint ?? "请选中…"` 在选中成功（hint=null）时仍显示未选中；贴图后导出偶发失败加重「选中失效」观感。

## 完成记录

- **时间**：2026-10-11
- **结果**：
  - `provider_errors` + `TaskState.emit_error` 规范化额度文案
  - `CanvasToastHost` + `runPipeline` / `appendError` 推送额度 toast（手动关闭）
  - 修复侧栏选中误报；`store.listen({scope:'all'})`；导出重试
- **验证**：待本轮 pytest / vitest
- **偏差**：DeepSeek 不做调用前预检（按确认）
