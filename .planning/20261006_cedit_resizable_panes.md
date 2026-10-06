## 任务：多轮编辑窗口内部区域可拖拽调节，并恢复本轮详情

**背景**：`DraggableWindow` 只能改整窗大小；会话打开后左侧预览 + 底部修改树（固定 `h-40`）+ 右侧栏（固定 `320px`）无法单独拉大。浮动布局还把 `VersionDetails` 藏掉了，本轮指令、参考图锚定、实际发送提示词看不到。窗口本身的拖动/改大小保持不变。
**影响范围**：
- 新增 `frontend/src/components/SplitPane.tsx`（横向 / 纵向分隔条）
- 新增 `frontend/src/studio/studio-split.ts`（分栏尺寸 sessionStorage）
- `frontend/src/studio/StudioWorkspace.tsx`（可拖分栏；浮动窗也渲染 VersionDetails）
- 单测：`frontend/src/components/SplitPane.test.tsx`、`frontend/src/studio/studio-split.test.ts`
**前置条件**：浮动窗多轮编辑已落地（`.planning/20261006_cedit_float_preview.md`）。

### Stage 1: 通用分隔条
- **目标**：`SplitPane` 支持 `horizontal`（左右）和 `vertical`（上下）；拖动手柄；最小尺寸；指针捕获。
- **成功标准**：单测覆盖拖动后尺寸变化、不低于最小值。
- **状态**：Complete

### Stage 2: 接入 Studio 会话布局并恢复本轮详情
- **目标**：四处可调：① 预览 | 右侧栏；② 预览 | 修改树；③ 编辑指令 | 场景实体；④ 实体列表 | 本轮详情。浮动窗与整页都显示 `VersionDetails`（本轮指令、参考图、实际发送提示词）。默认接近现状（右栏 320、树高 160、详情 200）。
- **成功标准**：打开 Two-branch knight，点 v2 能看到本轮修改、参考图、可展开的实际提示词；拖条后各区立刻变大变小。
- **状态**：Complete

### Stage 3: 记住本次偏好
- **目标**：四个尺寸写入 `sessionStorage`（`infd.cedit.split.*`），刷新窗口后恢复。
- **成功标准**：拉大右侧栏后关掉再开多轮编辑，宽度仍在。
- **状态**：Complete

**待确认事项**：
- [x] 四处可调：预览/右栏、预览/修改树、指令/实体、实体/本轮详情。
- [x] 尺寸按像素拖、设下限（右栏 ≥220、树 ≥96、指令 ≥140、详情 ≥88），不引入第三方 split 库。
- [x] 浮动窗恢复 VersionDetails；本轮不改整窗拖动逻辑。

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：浮动窗恢复本轮修改 / 参考图 / 实际发送提示词；预览、修改树、实体列表、本轮详情均可拖条调节，尺寸写入 sessionStorage。Two-branch knight 打开后可见「本轮修改」与「参考图锚定」。
- **偏差说明**：分栏按尾部面板像素（右栏/树/实体/详情），不是百分比。

