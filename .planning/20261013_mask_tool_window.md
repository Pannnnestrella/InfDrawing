## 任务：局部重绘刷选改为独立窗口

**背景**：侧栏 `backdrop-blur` 让内部 `position: fixed` 相对侧栏定位，「刷选重绘区域」被挤在约 368px 宽的对话框里。
**影响范围**：
- `frontend/src/canvas/MaskTool.tsx`
- `frontend/src/agent-panel/ChatPanel.tsx`
- `frontend/src/agent-panel/ChatComposer.tsx`
**前置条件**：已有 `DraggableWindow`（多轮编辑 / 素材库 / 图层）。

### Stage 1: 独立窗口
- **目标**：刷选界面通过 portal 挂到 `document.body`，用可拖动、可缩放的窗口打开，画布随窗口变大。
- **成功标准**：窗口不再被侧栏裁切；确认 / 取消行为与原来一致。
- **状态**：Complete

**待确认事项**：无。用户要求把局部重绘刷选设为独立窗口，并从对话栏直接打开。

## 完成记录

- **完成时间**：2026-10-13
- **实际结果**：刷选通过 portal 挂到页面上的可拖动窗口「Mask 重绘」。窗口 760×840，画布显示约 662px，不再被 368px 侧栏裁切。对话栏按钮为「打开 Mask 重绘」。
- **偏差说明**：无。
