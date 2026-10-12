## 任务：多轮编辑「实际发送内容」如实预览 + 小物件万相明示

**背景**：用户指出右下角「参考图锚定」未如实反映发给 API 的内容；小物件局部改静默走万相，模型框仍显示通义/OpenAI，易误导。
**影响范围**：
- `backend/app/controlled_edit/schemas.py`、`service.py`、`region_ops.py`（如需导出判定）
- `frontend/src/studio/VersionDetails.tsx`、`EditComposer.tsx`、`StudioWorkspace.tsx`、`studio-turn-options.ts`
- `frontend/src/lib/controlled-edit-api.ts`
- 相关测试
**前置条件**：`0881e87` 局部 Crop/Stitch 与现有 VersionDetails 已落地。
**规划日期**：2026-10-12。
**整体状态**：Complete

### 用户已确认
1. 区块标题改为「本轮发送的图像」
2. 自动万相矩形 Mask 生成时落盘为 artifact
3. 万相路径下锁定锚点仍显示（标为未发送，仅身份/验收相关）
4. 选中局部小物件目标时：明确提醒；模型框自动切换到万相

### Stage 1: 后端记录本轮实际发送图
- **目标**：版本写入 `sent_images`：`role`（primary / reference / mask / crop）、`artifact_id`、`index`、`label`、`sent`。自动万相落盘矩形 Mask；`reference_artifact_ids` 仍可保留锁定锚点 id，但 UI 以 `sent_images` 为准。
- **成功标准**：三种路径（整图 / 自动万相 / Crop-Stitch）写入正确；历史无字段可回退。
- **状态**：Complete

### Stage 2: VersionDetails 展示与点击全图
- **目标**：「本轮发送的图像」；Mask 可辨；点击 lightbox 看全图；未发送锚点有灰标。
- **成功标准**：万相能看到 Mask；整图能点开参考图；Esc/遮罩关闭。
- **状态**：Complete

### Stage 3: 小物件目标 → 万相明示与模型框切换
- **目标**：前端镜像 `uses_local_mask`；命中时模型框切到万相并提示，取消小物件目标后恢复原选择。
- **成功标准**：选中剑/盾等小框有可见提醒与模型框变化；选背景/整主体仍显示通义/OpenAI。
- **状态**：Complete

### Stage 4: 测试与审查
- **目标**：pytest / vitest / tsc / Ruff；Review Gate。
- **成功标准**：相关测试通过；完成记录写回本文件。
- **状态**：Complete

## 完成记录

- **完成时间**：2026-10-12
- **实际结果**：`sent_images` 落盘；自动万相矩形 Mask 持久化；VersionDetails 改为「本轮发送的图像」并可点击全图；选中小物件时模型框切到万相并出提示条。capabilities 增加 `local_mask_model`。
- **测试**：controlled_edit 相关 32 passed；前端 uses-local-mask 等 12 passed；tsc / Ruff 通过。
- **偏差**：无新增独立 Wanx provider 选项写入 sessionStorage；小物件命中时仅为 UI 覆盖显示，提交时后端仍按原静默路由。

### Review Gate
- **正确性**：整图路径序号与 primary_first/last 一致；万相路径区分已发送 primary/mask 与未发送锁定锚点；历史无 `sent_images` 回退旧 `reference_artifact_ids`。
- **规范一致性**：Python type hints / Google docstring；前后端目录规范；无提交权重。
- **测试**：服务单测覆盖 sent_images；前端判定单测覆盖小物件/背景/整主体。
- **风险**：自动万相仅在有 DashScope key 时生效；前端判定与后端一致但若后端阈值日后变更需同步 `uses-local-mask.ts`。
