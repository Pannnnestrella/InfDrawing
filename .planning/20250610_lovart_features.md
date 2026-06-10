## 任务：Lovart 式功能扩展（插件 T2I / 元素拆解 / Tab 重绘 / 文字编辑）

**背景**：阶段一 MVP 核心链路（txt2img/inpaint）已通，Stage 6 收尾（Mask + 回贴）未完成。会议新增 Lovart 式能力，采用本地先行验证 + 云 GPU 最终部署 + 资源感知策略。

**影响范围**：
- `frontend/src/canvas/` — MaskTool、canvas-bridge、插件 UI
- `frontend/src/lib/` — capabilities、api 扩展
- `backend/app/system/` — 资源检测（Phase 0.5）
- `backend/app/pipeline/` — Flux/SAM/decompose workflows（Phase 1+）
- `docs/cloud_gpu_setup.md`

**前置条件**：
- [x] Stage 2–5 脚手架与 ComfyUI SD1.5 联调
- [x] Stage 6 收尾（Phase 0–4）

### Stage 1: Phase 0 — Mask Tool + 回贴画布
- **目标**：画布刷选 mask、生成图自动落位 tldraw
- **成功标准**：inpaint 可不手动上传文件；txt2img/inpaint 结果出现在画布
- **状态**：Complete（2025-06-10）

### Stage 2: Phase 0.5 — 资源检测
- **目标**：`GET /system/capabilities` + 前端能力感知 UI
- **成功标准**：本机 8GB tier 正确；ComfyUI 不可达时功能灰显
- **状态**：Complete（2025-06-10）

### Stage 3: Phase 1 — 插件 T2I
- **目标**：右键 AI 生图；本地 SD1.5 / 云 Flux 自动切换
- **状态**：Complete（2025-06-10）

### Stage 4: Phase 2 — 元素拆解（rembg + SD1.5 inpaint，本地；云 Flux+SAM 预留）
- **目标**：右键「元素拆解」→ 背景 + 前景 RGBA 双图层回贴画布
- **成功标准**：`POST /generate/decompose` + WS `layers` 事件；本机 8GB + rembg 可用
- **状态**：Complete（2025-06-10）

### Stage 5: Phase 3 — 侧栏对话式 UX + 功能按钮驱动任务（**替代原 Tab 局部重绘**）
- **目标**：侧栏改为对话流；输入区功能按钮（生图 / 局部重绘 / 元素拆解）锁定 intent，用户消息即 prompt；意图理解结合按钮做 task routing
- **详细规划**：见 [`.planning/20250610_sidebar_chat_ux.md`](20250610_sidebar_chat_ux.md)
- **取消**：独立 Tab 局部重绘 UI（与侧栏 inpaint 重复）
- **状态**：Complete（2025-06-10）

### Stage 6: Phase 4 — 文字编辑 POC
- **目标**：OCR 检测 + 文字替换（本机：inpaint 抹字 + tldraw 叠字；云：AnyText2 预留）
- **详细规划**：见 [`.planning/20250610_text_edit_poc.md`](20250610_text_edit_poc.md)
- **状态**：Complete（2025-06-10）

### Stage 7（顺延）: Agent 自动 intent（可选）
- **状态**：Not Started

### Stage 8: 录屏 demo + README
- **状态**：Not Started — **当前优先**

## 完成记录（整体）
- **时间**：2025-06-10
- **结果**：Lovart 式 Phase 0–4 全部完成并用户验收；Tab 重绘已取消
- **偏差**：文字编辑/拆解/生图效果受本机 SD1.5、EasyOCR、8GB VRAM 限制；AnyText2/Flux/SAM 留云 GPU Stage B

**待确认事项**：
- [x] 云 GPU 最终部署；开发期本地先行 — 用户确认 2025-06-10
- [x] 元素拆解路线 A（Flux+SAM） — 用户确认
- [x] Phase 3 改为侧栏对话 + 功能按钮 — 用户确认并完成 2025-06-10
- [ ] DashScope API fallback（可选）

**批准**：用户确认 2025-06-10
