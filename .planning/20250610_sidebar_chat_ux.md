## 任务：侧栏对话式 UX + 功能按钮驱动任务分配

**背景**：Phase 2 元素拆解已完成。原 Phase 3「Tab 局部重绘」与现有侧栏 inpaint 能力高度重叠，仅差入口形态。用户决策：**不再单独做 Tab UI**，改为将侧栏升级为对话式交互；输入框区域提供功能按钮（生图、局部重绘等），用户选中按钮后发送的内容即提示词，由意图理解结合按钮完成 task routing。

**与项目目标关联**：统一 InfDrawing 主交互为「画布 + 侧栏 Agent」，降低多套入口的认知成本，为 Stage 7 自动 intent 与 demo 录屏打基础。

**影响范围**：
- `frontend/src/agent-panel/` — ChatPanel 重构为对话流 + Composer + 功能按钮
- `frontend/src/lib/api.ts` — 请求 payload 扩展（`selected_mode` / 对齐 `intent_override`）
- `backend/app/agent/` — plan 接口：按钮优先 + LLM prompt 润色
- `backend/app/agent/schemas.py` — 可选扩展 `IntentType`（含 `decompose`）
- `.planning/20250610_lovart_features.md` — Stage 5 定义替换
- `进度.md` — 当前焦点更新

**前置条件**：
- [x] Phase 0 — Mask + 回贴
- [x] Phase 0.5 — capabilities
- [x] Phase 1 — 右键 AI 生图
- [x] Phase 2 — 元素拆解 API + 右键入口

---

### Stage 1: 侧栏对话 UI 骨架
- **状态**：Complete（2025-06-10）

### Stage 2: 功能按钮（Mode Chips）与能力灰显
- **状态**：Complete（2025-06-10）

### Stage 3: 意图理解 × 按钮联动（后端 + 前端）
- **状态**：Complete（2025-06-10）

### Stage 4: 元素拆解收入侧栏 + 清理旧表单 UI
- **状态**：Complete（2025-06-10）

## 完成记录
- **时间**：2025-06-10
- **结果**：侧栏对话式 UX 上线；默认「生图」；按钮 `[生图][局部重绘][元素拆解]`；右键菜单保留；IntentType 含 decompose；对话历史内存列表
- **偏差**：intent_override 时仍走 fallback plan（LLM 润色留待 Stage 7）

---

### Stage 1: 侧栏对话 UI 骨架（归档）
- **目标**：将现有表单式 ChatPanel 改为「消息列表 + 底部输入区」布局
- **交付物**：
  - `MessageList`：用户消息、系统状态、错误、结果缩略图
  - `ChatComposer`：多行输入 + 发送按钮
  - 保留 `TaskStatus` / WS 进度以气泡或 inline 状态展示
- **成功标准**：txt2img / inpaint 现有链路在对话 UI 下可跑通，行为与重构前一致
- **状态**：Complete（2025-06-10）

### Stage 5（原 Phase 4 顺延）：文字编辑 POC
- **目标**：输入框上方（或下方）放置功能按钮，替代 Intent 下拉框
- **按钮（初版）**：
  | 按钮 | 对应 intent | 前置条件 |
  |------|-------------|----------|
  | 生图 | `txt2img` | capabilities.txt2img |
  | 局部重绘 | `inpaint` | capabilities.inpaint + 画布选图 |
  | 元素拆解 | `decompose` | capabilities.decompose + 画布选图 |
- **交互**：
  - 单选激活一个 mode；未选时默认「生图」或上次选中项
  - 不可用按钮 disabled + tooltip 显示 `feature.reason`
  - 选中「局部重绘」时，Composer 区展示「刷选 Mask」快捷入口与选图提示（沿用 MaskTool）
- **成功标准**：切换按钮后 placeholder / 校验规则随 mode 变化；disabled 与 CapabilityBanner 一致
- **状态**：Not Started

### Stage 3: 意图理解 × 按钮联动（后端 + 前端）
- **目标**：用户选中按钮 → 意图已确定；LLM 主要负责 **prompt 润色**，而非重新猜 intent
- **协议**（沿用并明确 `intent_override` 语义）：
  ```json
  POST /api/v1/agent/plan
  {
    "user_message": "用户输入即提示词",
    "intent_override": "txt2img | inpaint | decompose",
    "context": { "selectedShapeId", "hasMask", ... }
  }
  ```
- **后端行为**：
  - 有 `intent_override`：intent 锁定为按钮值；LLM 仅输出 `refined_prompt` / `negative_prompt`（可选轻量校验：inpaint 时 context 无 mask 则 reasoning 提示）
  - 无 override（未来 Stage 7）：LLM 自动分流 intent + 润色
- **前端行为**：发送时带当前选中 mode；消息列表展示「模式标签 + 润色后 prompt」
- **成功标准**：三种 mode 均通过侧栏一次发送完成 plan → generate → 回贴
- **状态**：Not Started

### Stage 4: 元素拆解收入侧栏 + 清理旧表单 UI
- **目标**：decompose 从仅右键入口扩展为侧栏按钮；移除 Intent `<select>`、inpaint 手动上传区块（Mask 刷选保留）
- **可选**：右键菜单保留为画布快捷方式，与侧栏共享同一套 generate 逻辑（不重复实现）
- **成功标准**：侧栏可独立完成生图 / 局部重绘 / 元素拆解；UI 无冗余表单控件
- **状态**：Not Started

### ~~原 Stage 5~~：Tab 局部重绘 — **取消**
- **原因**：与侧栏 inpaint + 画布 Mask 重复；不再单独实现 Tab 切换 UI
- **状态**：Cancelled

### Stage 5（原 Phase 4 顺延）：文字编辑 POC
- **状态**：Not Started（不变）

---

**架构示意**：

```
┌─────────────────────────────────────────────────────────┐
│ 画布 (tldraw)          │ 侧栏                           │
│ 选图 / Mask / 右键快捷  │ ┌ MessageList ─────────────┐ │
│                        │ │ user: 红色苹果            │ │
│                        │ │ assistant: 生成中…        │ │
│                        │ │ [结果缩略图] → 已贴画布    │ │
│                        │ └──────────────────────────┘ │
│                        │ [生图] [局部重绘] [元素拆解]   │
│                        │ ┌────────────────── [发送] ┐ │
│                        │ │ 描述你想生成的内容…        │ │
│                        │ └──────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
         │                              │
         └──────── canvas-bridge ───────┘
                        │
              intent_override = 当前按钮
              user_message    = 输入框文本
                        │
              /agent/plan → /generate/* → WS → 回贴
```

---

**待确认事项**（请用户确认后再开工）：

1. **右键菜单**：是否保留「AI 生图 / 元素拆解」作为画布快捷入口？（建议：保留，与侧栏共用底层逻辑）
2. **默认 mode**：打开侧栏时默认选中「生图」还是「无选中、必须用户点按钮」？
3. **对话历史**：本阶段是否只做当前会话内存列表，还是暂不做历史持久化？（建议：内存列表即可，demo 阶段够用）
4. **`decompose` 纳入 agent IntentType**：是否在 `schemas.py` 正式增加 `decompose`，与 txt2img/inpaint 并列？（建议：是，便于统一 plan 输出）
5. **局部重绘命名**：侧栏按钮文案用「局部重绘」还是「Inpaint / 重绘」？

---

**批准信号**：用户回复「确认 / 开始 / ok」等后，按 Stage 1 → 4 顺序实施。

**偏差说明**：相对原 `20250610_lovart_features.md` Stage 5（Tab 重绘），本任务为产品交互路线调整，不新增 ComfyUI workflow，复用现有 generate 接口。
