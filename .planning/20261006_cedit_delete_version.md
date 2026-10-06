## 任务：删除修改树节点（如 v9）

**背景**：失败或试错节点会留在树上，用户希望能删掉指定版本（例如 v9）清理历史。
**影响范围**：
- `backend/app/controlled_edit/repository.py`：Memory / Json / SQL 增加 `delete_versions`
- `backend/app/controlled_edit/service.py` + `api.py`：`DELETE .../versions/{version_id}`
- `frontend/src/lib/controlled-edit-api.ts`、`VersionTree` / `StudioWorkspace`：删除入口与确认
- 单测、`docs/controlled_edit.md`
**前置条件**：版本树与 checkout 已可用；JSON 落盘已稳定

### Stage 1: 后端删除（含子树）
- **目标**：删除指定节点及其全部后代；禁止删原图根节点；生成中（pending/running）禁止删；若当前指针落在被删子树内，自动 checkout 到被删节点的父节点
- **成功标准**：单测覆盖删叶子、删带子树、禁删根、禁删 busy、当前指针回落父节点；Json 落盘后重启列表不再含该节点
- **状态**：Complete

### Stage 2: 前端删除
- **目标**：当前选中非根节点时提供「删除」；确认后调用 API 并刷新树；删除后停留在父节点
- **成功标准**：`/studio` 可删 v9 一类叶子/失败节点，树与详情同步
- **状态**：Complete

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：`DELETE /versions/{id}` 删节点+子树；禁删根与 busy；当前指针回父节点；Studio「删除当前节点」带确认。artifact 文件不删。`tests/controlled_edit` 75 通过。
- **偏差说明**：无单独 API 层 HTTP 单测；前端用 `window.confirm`。

---

**待确认事项**：
- [x] 删除范围：默认「节点 + 全部后代」可以吗？（只删叶子会逼用户先清分支，体验更差）
- [x] 图像 artifact 文件：本期只删版本元数据，磁盘上的 PNG 可暂留（避免误伤被其他版本引用的锚点图）；可以吗？
