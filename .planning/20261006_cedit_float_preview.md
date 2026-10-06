## 任务：多轮编辑改为对话入口弹出，预览可对比并可导入画布

**背景**：首页左侧常驻「多轮编辑」坞挡住画布；`layout=dock` 时故意不渲染 `VersionViewer`，所以预览图和「与上一版对比」拖动条都看不到，点修改树也只换侧栏状态。用户要：默认不占界面、从 AI 对话点开、看清预览/对比、满意后再导入画布。
**影响范围**：
- `frontend/src/app/HomeWorkspace.tsx`：去掉左侧常驻坞
- `frontend/src/agent-panel/ChatPanel.tsx` / `ChatComposer.tsx`：增加「多轮编辑」入口
- `frontend/src/studio/StudioWorkspace.tsx`：浮动窗布局；去掉自动向画布铺新图
- 新增 `frontend/src/components/DraggableWindow.tsx`（可拖动、可改大小）
- `frontend/src/studio/VersionViewer.tsx`：浮动窗内恢复对比滑杆
- 相关 vitest（Chat / studio）
**前置条件**：多轮编辑已在首页对接；`VersionViewer` 对比滑杆仍在 page 布局中

### Stage 1: 收起常驻坞，对话栏入口弹出
- **目标**：首页默认只有画布 + 右侧 AI 面板。AI 功能条增加「多轮编辑」，点击打开浮动窗（内嵌现有 StudioWorkspace）。
- **成功标准**：刷新首页左侧不再出现多轮编辑；点入口出现窗口；关闭窗口画布不被挡住。
- **状态**：Complete

### Stage 2: 预览 + 修改树 + 拖动对比
- **目标**：浮动窗主区渲染 `VersionViewer`（含「与上一版对比」clip-path 滑杆）。点击修改树节点 `checkout` 后主区立刻换图/可对比。框选实体仍叠在预览图上。
- **成功标准**：打开已有会话「Two-branch knight」，点 v1–v7 能看到对应预览；打开对比后拖动分割线能在上一版/当前之间扫过。
- **状态**：Complete

### Stage 3: 导入画布；生成不再自动铺图
- **目标**：去掉 dock 里「每成功一版就 paste 到画布右侧」。窗口底部「导入画布」把**当前预览版本**贴到选中图右侧（沿用 `pasteImageUrlToCanvas`）。
- **成功标准**：生成新版本只更新浮动窗预览；点导入后画布出现该图；未点导入则画布不变。
- **状态**：Complete

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：首页无左侧坞；AI 面板「多轮编辑」弹出可拖动/改大小窗口；Two-branch knight 预览可见；v2 对比滑杆可用；「导入画布」在窗头。
- **偏差**：对比在根节点（无上一版）时复选框禁用；未新装拖拽库。

