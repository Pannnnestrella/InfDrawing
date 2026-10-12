## 任务：可控编辑工作流图（Edit Workflow Graph）

**背景**：现有多轮编辑已把每轮完整落成 `EditVersion` 节点，且修改树支持分叉。需要可复用的完整节点图（分叉、条件、合并），以便同一套操作拓扑套到新图上。

**核心原则**：模板图（Workflow DAG）与执行树（EditSession / EditVersion）分层；从会话子图导出模板 → 对输入图执行 → 生成新会话执行树。

**影响范围**：
- `backend/app/controlled_edit/workflow/`（schemas / graph / repository / export / runner / api）
- `backend/app/controlled_edit/schemas.py`（`input_version_ids`）
- `backend/app/controlled_edit/service.py`（`submit_turn` 同步执行选项）
- `backend/app/production/models.py`（`edit_workflows`）
- `backend/app/config.py`（runner 并发）
- `frontend/src/studio/workflow/`、`controlled-edit-api.ts`、`VersionTree` 导出入口
- `docs/controlled_edit.md`

**前置条件**：多轮可控编辑会话 / 版本树 / 锁定 / 验收已可用。

### Stage 1: 领域模型与仓储
- **目标**：`EditWorkflow`、节点/边 schema、Memory+SQL 仓储、CRUD API、环检测
- **成功标准**：可创建/读取/更新 DAG；非法边校验失败
- **状态**：Complete

### Stage 2: 会话子图 → 工作流导出
- **目标**：`POST /sessions/{id}/export-workflow`
- **成功标准**：含分叉子图可导出；角色抽取单测通过
- **状态**：Complete

### Stage 3: Runner（分叉 / 条件 / 合并）
- **目标**：`POST /workflows/{id}/runs`；condition / merge；`input_version_ids`
- **成功标准**：mock 覆盖线性、分叉、condition、merge
- **状态**：Complete

### Stage 4: 工作流编辑器 UI
- **目标**：xyflow 编辑器、导出入口、Run
- **成功标准**：浏览器可编辑并跑通
- **状态**：Complete

### Stage 5: 文档与门禁
- **目标**：英文文档 + 测试 / lint
- **成功标准**：文档可读；相关测试通过
- **状态**：Complete

## 完成记录

- **完成时间**：2026-10-12
- **实际结果**：模板/执行分层；workflow CRUD + export + runner；Studio 导出；`/workflows` xyflow 编辑器；`docs/controlled_edit.md` Workflow 章节；`test_cedit_workflow.py` 覆盖校验/导出/runner。
- **偏差**：Postgres 上 workflow runs 仍走进程内 Memory 旁路（模板进 `edit_workflows` 表）；条件边在编辑器中从 condition 节点连出时默认 `pass`。

**待确认事项**（已按规划默认）：
- merge 默认 `multi_ref`；`select_best` 可选
- 与 `controlled_edit` 同 scope
- Runner 并发上限默认 2
