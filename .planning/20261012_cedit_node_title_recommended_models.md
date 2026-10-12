## 任务：修改树节点命名 + 推荐模型标记

**背景**：修改树节点只有 v1、v2。整图默认已是 `qwen-image-3.0-pro`，小物件自动局部默认是 `wan2.7-image-pro`，但下拉框没有「推荐」标记，对外流程描述仍写着 Qwen 2.0 / 万相 2.1 Mask。
**影响范围**：`backend/app/controlled_edit/schemas.py`、`api.py`、`service.py`；`frontend/src/studio/VersionTree.tsx`、`StudioWorkspace.tsx`、`EditComposer.tsx`、`studio-turn-options.ts`、`frontend/src/lib/controlled-edit-api.ts`；对应测试；`docs/submission/materials/01_可粘贴正文补全.md` 第 4.3 节
**前置条件**：版本节点以 JSON 整包存储，新增可选字段即可兼容旧会话

### Stage 1: 节点标题
- **目标**：`EditVersion.title`（可空，最长 40 字）。`PATCH /sessions/{id}/versions/{version_id}` 只改标题。圆点仍显示 vN；有标题时画在圆点下方，tooltip 同时显示标题和指令。树头对当前节点提供重命名输入。
- **成功标准**：重命名后刷新会话仍在；空标题回退为「原图」或指令摘要；根节点也可命名
- **状态**：Not Started

### Stage 2: 推荐模型
- **目标**：整图下拉把 `qwen-image-3.0-pro` 标为「推荐」，并作为未记住选择时的默认项。小物件自动局部锁定文案标明推荐 `wan2.7-image-pro`。手绘 Mask 继续锁定 `wanx2.1-imageedit`，不标成整图推荐。
- **成功标准**：新会话默认选中推荐整图模型；点选小物件时界面写明实际模型是 `wan2.7-image-pro`
- **状态**：Not Started

### Stage 3: 流程描述
- **目标**：把面试材料 4.3 的模型分工改成下面这版推荐流程
- **成功标准**：正文不再把 Qwen 2.0 或万相 2.1 Mask 写成默认改图路径
- **状态**：Not Started

**待确认事项**：
1. 圆点保持 vN，名字写在圆点下方。若要改成只显示短名，需要另说。
2. 推荐模型按当前配置：定位/重识别 `qwen3-vl-plus`，意图与验收 `gpt-4o`，整图 `qwen-image-3.0-pro`，小物件 `wan2.7-image-pro`，手绘 Mask `wanx2.1-imageedit`。OpenAI `gpt-image-1` 保留为可选项，不作为推荐。
3. 验收失败后的重试按代码：一共最多 2 次（首次 + 1 次重试）。
