## 任务：画布图层面板（多图层管理 UI）

**背景**：InfDrawing 已通过 tldraw image shape + z-index 支持多层叠放（元素拆解会回贴前景/背景），但缺少可浏览、选中、显隐、锁定、重排的图层管理 UI。阶段一 demo 需要「看得见的多图层」，对齐 Lovart 式画布体验与项目定位中的 layers 关键词。
**影响范围**：
- `frontend/src/lib/canvas-bridge.ts` — 图层列举 / 选中 / 显隐 / 锁定 / 重排 / 重命名 API
- `frontend/src/layers/`（新建）— 面板 store、列表 UI、缩略图
- `frontend/src/app/HomeWorkspace.tsx` — 挂载图层面板浮窗
- `frontend/src/agent-panel/ChatPanel.tsx` / `ChatComposer.tsx` — 入口按钮（与素材库并列）
- `frontend/src/lib/canvas-bridge.test.ts` 或 `frontend/src/layers/*.test.ts` — 单元测试
- 不改后端；不改拆解管线（继续产出多层 image shape）
**前置条件**：
- [x] tldraw 画布 + `canvas-bridge` 单例桥接
- [x] 元素拆解 `pasteLayersToCanvas` 双层回贴
- [x] `DraggableWindow` / 素材库面板交互范式可复用

### Stage 1: canvas-bridge 图层 API
- **目标**：在 bridge 层提供「当前页 image 图层」的只读快照与写操作，不引入平行数据模型
- **交付物**（建议签名）：
  - `listImageLayers(): CanvasLayerInfo[]` — 按 z-index（`shape.index`）从顶到底
  - `selectLayer(id)` / `setLayerHidden(id, hidden)` / `setLayerLocked(id, locked)`
  - `reorderLayer(id, direction: "up" | "down" | "front" | "back")` — 封装 tldraw bringForward / sendBackward 等
  - `renameLayer(id, name)` — 写入 `shape.meta.layerName`（或 asset `props.name`，见待确认）
  - `subscribeCanvasLayers(listener)` — 订阅 editor store 变更，面板实时刷新
- **成功标准**：纯函数/桥接单测覆盖排序与顶层选取；无 Editor 时 API 安全返回空/false
- **状态**：Complete

### Stage 2: 图层面板 UI
- **目标**：可拖动「图层」浮窗，列表展示当前页图片图层
- **交互**（MVP）：
  - 每行：缩略图 + 名称 + 显隐 / 锁定 / 选中高亮
  - 点击行 → 仅 `select`（不 zoom）
  - 置顶 / 上移 / 下移 / 置底按钮
  - 双击名称重命名（`meta.layerName`）
  - 空态：「画布上还没有图片图层」
  - z-index 与素材库/多轮编辑一致：`DraggableWindow`（约 600），避开 tldraw blocking overlay
- **成功标准**：拆解后面板出现前景+背景两行；点选/显隐/锁定与画布一致
- **状态**：Complete

### Stage 3: 入口与拆解联动
- **目标**：侧栏「打开图层」入口；拆解后若面板已开则自动刷新
- **成功标准**：与「素材库」入口并列可达；订阅 `subscribeCanvasBridge` 实时刷新
- **状态**：Complete

### Stage 4: 质量门禁
- **目标**：vitest + `tsc`；浏览器手测主路径
- **手测清单**：
  1. 生图 → 面板出现一层
  2. 元素拆解 → 两层，顶层为前景
  3. 隐藏背景 → 画布只见前景
  4. 锁定前景 → 画布拖不动该层
  5. 重排后入库仍取 z-index 顶层
- **成功标准**：相关测试通过；上述 5 条手测通过
- **状态**：Complete（自动化）；手测待用户浏览器确认

**明确不做（本轮）**：
- 自研图层系统 / 脱离 tldraw 的合成引擎
- 混合模式（multiply 等）、图层组/文件夹、非 image shape（文字/几何）管理
- 后端持久化图层树（仍靠 tldraw `persistenceKey` 本地存盘）
- Photoshop 式图层蒙版编辑器（MaskTool 保持现有入口）

**待确认事项**：
1. **图层范围**：仅 `image` — 已确认（2026-10-10）
2. **面板形态**：`DraggableWindow` 浮窗 — 已确认
3. **排序交互**：四向按钮 — 已确认
4. **点选行为**：仅 `select` — 已确认
5. **重命名存储**：`shape.meta.layerName` — 已确认
6. **拆解后自动开面板**：仅刷新已打开面板 — 已确认
7. **不透明度滑条**：下一轮 — 已确认；本轮在 `CanvasLayerInfo` / meta 预留扩展位

**扩展性约定**（实现时遵守）：
- 图层元数据统一走 `shape.meta`（`layerName` / `hidden`；后续可加 `opacityOverride`、`blendMode`、`groupId`）
- 桥接 API 与面板 UI 分离：`canvas-bridge` 只做读写；`layers/` 只做展示与入口
- `listImageLayers` 返回结构化 `CanvasLayerInfo`，后续字段可加不破旧调用
- 显隐通过 tldraw `getShapeVisibility` + `meta.hidden`（官方推荐模式）

**批准**：用户确认「按照推荐实现」并要求可扩展（2026-10-10）
**执行顺序**：Stage 1 → 2 → 3 → 4

## 完成记录

- **时间**：2026-10-10
- **结果**：
  - `frontend/src/lib/layer-model.ts`：可扩展 meta 模型（`layerName` / `hidden`，预留 `blendMode` / `groupId`）+ 纯函数
  - `canvas-bridge`：`listImageLayers` / 选中 / 显隐 / 锁定 / 重命名 / 重排；拆解回贴写入 `meta.layerName`
  - `InfDrawingCanvas`：`getShapeVisibility` ← `meta.hidden`
  - `frontend/src/layers/`：浮窗面板 + store；侧栏「图层」入口
  - `DraggableWindow`：可选 `minWidth` / `minHeight`（窄图层面板）
- **验证**：`tsc --noEmit` 通过；`layer-model` / `layer-panel-store` / `ChatComposer` vitest 通过
- **偏差**：无；透明度滑条按确认留待下一轮（`CanvasLayerInfo.opacity` 已暴露）
- **后续扩展点**：在 `LayerMeta` 加字段 → bridge setter → `LayerRow` 控件；无需平行图层仓
