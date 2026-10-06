## 任务：素材管理（VLM 标注 + 可命名库）

**背景**：画布图只活在 tldraw IndexedDB，历史素材无法按内容找回。入库时用 Qwen-VL 打物体标签与风格描述，支撑后续文本检索。对应提交文档模块一。
**影响范围**：
- `backend/app/assets/`
- `backend/app/main.py`、`backend/app/system/capabilities.py`
- `backend/tests/assets/`
- `frontend/src/canvas/AiContextMenu.tsx`、`InfDrawingCanvas.tsx`
- `frontend/src/library/`
- `frontend/src/app/HomeWorkspace.tsx`、`frontend/src/agent-panel/ChatComposer.tsx`
**前置条件**：DashScope/OpenAI vision 与 ArtifactService 已可用。

### Stage 1: 后端素材库
- **目标**：命名库 JSON 仓、Artifact 存图、同步 VLM caption、CRUD + 文本检索 API
- **成功标准**：FakeVision 单测覆盖入库、失败落盘、检索、改标签
- **状态**：Complete

### Stage 2: 右键入库
- **目标**：选中图右键「加入素材库」；选/建库 + 标题；等待标注
- **成功标准**：无选中图时菜单项不出现；提交后条目出现在库中
- **状态**：Complete

### Stage 3: 素材库面板
- **目标**：可拖动面板：按库筛选、关键词搜、编辑、贴回画布
- **成功标准**：搜索命中描述/标签；点选贴回画布
- **状态**：Complete

### Stage 4: 质量门禁
- **目标**：pytest / vitest / 浏览器主路径
- **成功标准**：相关测试通过；手工入库与搜索可用
- **状态**：Complete

**待确认事项**：
- [x] 本轮不做形状搜索 / embedding / 质量 QC（规划已确认）

## 完成记录

- **时间**：2026-10-06
- **结果**：`/api/v1/assets` + 右键入库对话框 + 可拖动素材库面板。Qwen-VL 同步标注；失败条目仍保存。文本检索贴回画布已在浏览器验证。
- **偏差**：形状搜索未做（按规划）。索引落在 `data/assets/library.json`。
- **增量**：游戏资产结构字段（类型/视角/题材/背景/姿态/主色/材质）入库自动填，面板可改；旧条目缺省为空，重新标注后补全。
- **增量（静默失败）**：拆解后多选时按 z-index 取最上层入库；面板订阅 `notifyLibraryDataChanged` 刷新并选中最新条；导出强制 PNG；空 Content-Type 后端按 magic bytes 嗅探。
