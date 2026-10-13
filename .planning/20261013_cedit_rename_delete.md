## 任务：多轮编辑节点改名 + 会话改名/删除

**背景**：修改树节点只有 vN，不好辨认；历史会话列表只能打开，不能改名或整段删掉。用户要求节点可改名，对话历史本身也可改名和删除。
**影响范围**：
- `backend/app/controlled_edit/schemas.py`、`api.py`、`service.py`、`repository.py`
- `frontend/src/lib/controlled-edit-api.ts`
- `frontend/src/studio/VersionTree.tsx`、`StudioWorkspace.tsx`、`UploadPanel.tsx`、`VersionDetails.tsx`（如需）
- 相关后端/前端测试
**前置条件**：版本已可删子树；会话有 `title`；节点标题规划见 `.planning/20261012_cedit_node_title_recommended_models.md` Stage 1（未做）。本任务只做命名与会话删除，不含推荐模型。

### Stage 1: 节点标题
- **目标**：`EditVersion` 增加可选 `title`（最长 40）。`PATCH /sessions/{id}/versions/{version_id}` 只改标题。树圆点仍显示 vN；有标题时画在圆点下方；tooltip / 详情同时显示标题与指令。当前节点旁提供重命名入口。
- **成功标准**：重命名后刷新会话仍在；空标题回退为「原图」或指令摘要；根节点可命名；旧会话缺字段仍可打开。
- **状态**：Complete

### Stage 2: 会话改名与删除
- **目标**：
  - `PATCH /sessions/{id}`：改 `title`（最长 120）。
  - `DELETE /sessions/{id}`：删会话及其全部版本记录；打开中的会话被删后回到上传页。
  - 历史列表每行：打开 / 改名 / 删除（删除前确认）。打开会话后的顶栏也可改当前会话名。
- **成功标准**：列表与顶栏改名同步；删除后列表不再出现，再 GET 返回 404；有进行中版本时拒绝删除并提示。
- **状态**：Complete

### Stage 3: 测试与文档
- **目标**：后端单测覆盖改名/删会话/忙时拒绝；前端 API 与 UploadPanel/VersionTree 相关 vitest；`docs/controlled_edit.md` 补一句 API。
- **成功标准**：相关测试通过；Review Gate 四类结论写清。
- **状态**：Complete

**待确认事项**：
1. 节点展示：圆点保持 vN，名字写在圆点下方（与既有节点命名规划一致）。若要改成只显示短名，请说明。→ **已确认**
2. 删除会话时：只删会话与版本元数据；图片 artifact 文件暂不级联清理（与现有删版本行为一致，本地 `data/cedit` 不回收磁盘）。若要顺带清 artifact，请说明。→ **已确认**
3. 本轮不做推荐模型标记与面试材料改写（仍留在 `20261012_cedit_node_title_recommended_models.md`）。→ **已确认**

## 完成记录

- **完成时间**：2026-10-13
- **实际结果**：节点/会话改名与会话删除已上线；后端 5 项相关测试与前端 API vitest 通过
- **偏差说明**：无；前端用 `window.prompt` 做节点/顶栏改名，历史列表用行内输入
