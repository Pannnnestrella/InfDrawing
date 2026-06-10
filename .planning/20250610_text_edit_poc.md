## 任务：Phase 4 — 图中文字编辑 POC

**背景**：Phase 3 侧栏对话 + 功能按钮已上线（生图 / 局部重绘 / 元素拆解）。Lovart 式能力清单中「图中文字编辑」尚未实现；capabilities 中 `text_edit` 当前固定 disabled。

**与项目目标关联**：完善作品集 demo 的多模态编辑故事线；与侧栏统一入口一致，不新增 Tab UI。

**影响范围**：
- `backend/app/pipeline/` — OCR 检测、文字编辑 executor（AnyText2 或 fallback）
- `backend/app/pipeline/workflows/` — AnyText2 ComfyUI workflow JSON（云 GPU 路径）
- `backend/app/api/` — `POST /generate/detect-text`、`POST /generate/text-edit`
- `backend/app/agent/schemas.py` — `IntentType.TEXT_EDIT`
- `backend/app/system/capabilities.py` — `text_edit` 动态启用
- `frontend/src/agent-panel/` — 侧栏第 4 个按钮「文字编辑」+ 检测结果 UI
- `frontend/src/lib/` — api、capabilities 扩展

**前置条件**：
- [x] Phase 0 — 画布选图 + Mask + 回贴
- [x] Phase 0.5 — capabilities
- [x] Phase 3 — 侧栏 mode 按钮 + `intent_override` 协议

---

### 技术路线（建议）

| 层级 | 本机 8GB（Stage A） | 云 GPU 24GB+（Stage B，可选后续） |
|------|---------------------|----------------------------------|
| 检测 | **EasyOCR（CPU）** 返回 bbox + 文本 | 同左或 ComfyUI OCR 节点 |
| 编辑 | 用户改字 → 生成文字区域 mask → **SD1.5 inpaint 抹字** → **tldraw 文本层叠新字** | ComfyUI **AnyText2** .workflow 直接渲染新字 |
| 能力 flag | `text_edit` backend=`ocr_inpaint_overlay` | backend=`anytext2` |

**POC 成功定义（Stage A）**：选中含文字图片 → 侧栏「文字编辑」→ 自动 OCR 列出文字块 → 用户修改某条文案并发送 → 原图文字区被 inpaint 抹除 + 画布上叠加 editable 文本（位置对齐 bbox）→ 可录屏演示。

**非目标（本阶段）**：字体/透视/风格完美匹配 AnyText2 级效果；文字持久化到项目文件；多语言 OCR 调优。

---

### Stage 1: OCR 文字检测 API
- **状态**：Complete（2025-06-10）

### Stage 2: 侧栏「文字编辑」模式 + 检测 UI
- **状态**：Complete（2025-06-10）

### Stage 3: 文字替换管线（本机 fallback）
- **状态**：Complete（2025-06-10）

### Stage 4: Agent + capabilities 收尾
- **状态**：Complete（2025-06-10）

## 完成记录
- **时间**：2025-06-10
- **结果**：EasyOCR detect-text + text-edit inpaint + 侧栏「文字编辑」按钮 + tldraw 叠字；`text_edit` capabilities 启用
- **偏差**：AnyText2 云路径（Stage 5）未实现；**用户验收通过**，视觉融合质量受 SD1.5 inpaint + 叠字方案限制（非 AnyText2）
- **修复**：tldraw `asset:` URL 经 `resolveAssetUrl` 导出后再 OCR

---

### Stage 1: OCR 文字检测 API（归档）
- **目标**：对上传/选中图片返回文字块列表
- **交付物**：
  - `backend/app/pipeline/text_detect.py` — EasyOCR wrapper
  - `POST /api/v1/vision/detect-text`（multipart image）
  - 响应：`{ "regions": [{ "text", "bbox": [x0,y0,x1,y1], "confidence" }] }`
- **成功标准**：本地 CPU 可跑；无 easyocr 时 API 503 + capabilities 灰显
- **状态**：Not Started

### Stage 2: 侧栏「文字编辑」模式 + 检测 UI
- **目标**：第 4 个 mode 按钮；选中图片后自动/手动触发 OCR，列表展示可编辑项
- **交付物**：
  - `ModeChips` 增加「文字编辑」
  - `TextEditPanel` 或 Composer 内嵌：检测列表 + 单条替换输入
  - 发送时 `intent_override: "text_edit"`，`user_message` = 新文案（或 JSON：`{ region_index, new_text }`）
- **成功标准**：UI 能展示 OCR 结果；未选图时提示
- **状态**：Not Started

### Stage 3: 文字替换管线（本机 fallback）
- **目标**：抹除旧字 + 画布叠字
- **交付物**：
  - `text_edit_executor.py`：bbox → 膨胀 mask → SD1.5 inpaint（prompt: clean background）→ WS complete
  - `canvas-bridge`：`overlayTextOnCanvas(bbox, text, style?)` 创建 tldraw `text` shape
  - `POST /api/v1/generate/text-edit`
- **成功标准**：端到端替换一条 OCR 文字块并回贴；侧栏对话流有状态消息
- **状态**：Not Started

### Stage 4: Agent + capabilities 收尾
- **目标**：`TEXT_EDIT` intent；`text_edit` feature 按 easyocr + inpaint 启用
- **交付物**：schemas / router / prompts 更新；测试；规划文档完成记录
- **状态**：Not Started

### Stage 5（可选 / 云 GPU）：AnyText2 ComfyUI 路径
- **目标**：检测到 AnyText2 节点时切换 backend，跳过 tldraw 叠字
- **状态**：Not Started（本阶段可不做，留接口）

---

**数据流示意**：

```
选中图片 → [文字编辑] → detect-text → 展示 OCR 列表
用户改「HELLO」→「WORLD」→ plan(text_edit) → text-edit API
  → inpaint 抹除 HELLO 区域 → 回贴净图 → overlayText(WORLD @ bbox)
```

---

**待确认事项**：

1. **本机 POC 路线**：是否接受 **OCR + inpaint 抹字 + tldraw 文本叠层** 作为 8GB demo？（AnyText2 留 Stage 5 / 云 GPU）
2. **OCR 引擎**：默认 **EasyOCR**（pip 安装，CPU）是否可以？（体积较大，首次下载模型）
3. **交互**：一次只改 **一条** OCR 文字块，还是支持批量？（建议：POC 只做单条）
4. **检测时机**：切到「文字编辑」自动 OCR，还是点「检测文字」按钮？（建议：自动 OCR，失败可重试）
5. **右键菜单**：是否增加「文字编辑」快捷入口？（建议：暂不增加，仅侧栏，与 Phase 3 一致）

---

**批准信号**：用户确认后按 Stage 1 → 4 实施；Stage 5 视本机/云环境再定。
