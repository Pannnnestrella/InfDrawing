## 任务：入库归库、用途说明、基础属性、批量与去重

**背景**：当前右键入库只能选已有库名或填新库名，没有库用途；条目缺少来源项目 / 角色归属等生产属性；多选只入库最上层一张；同图不同文件名会重复落盘。对应素材失控（Search）的补全。
**影响范围**：
- `backend/app/assets/schemas.py`、`repository.py`、`service.py`、`api.py`
- `backend/tests/assets/`
- `frontend/src/lib/library-api.ts`、`library-search.ts`
- `frontend/src/library/LibraryIngestDialog.tsx`、`LibraryPanel.tsx`
- `frontend/src/lib/canvas-bridge.ts`（批量导出选中图）
**前置条件**：素材库 CRUD、VLM 标注、面板刷新、`ArtifactRecord.sha256` 已可用。

### Stage 1: 数据模型
- **目标**：库增加 `purpose`；条目增加 `keywords`、`source_project`、`character_name`、`content_sha256`；旧 JSON 缺省为空串，读入不崩。
- **成功标准**：单测覆盖创建库带用途、条目补属性、search_blob 含新字段。
- **状态**：Complete

### Stage 2: 去重与入库 API
- **目标**：入库前按 owner + sha256 查找已有条目；命中返回 409 与已有条目 id；`force=true` 才再存一份。建库 `POST` 接受 `purpose`；`PATCH /libraries/{id}` 改用途。
- **成功标准**：同一 PNG 换文件名第二次入库 409；force 后有两条；哈希用**规范化后的存储字节**（与 Artifact sha256 一致）。
- **状态**：Complete

### Stage 3: 批量入库
- **目标**：对话框一次提交多张图（画布多选全部 image；面板可选本地文件）。共享归库 / 用途 / 关键词 / 来源 / 角色归属；逐张标注；进度「3/8」；重复项列出「已存在：标题」。
- **成功标准**：选中前景+背景可两张都进库；重复的那张不新建；失败一张不阻断其余。
- **状态**：Complete

### Stage 4: 面板展示与编辑
- **目标**：库下拉旁显示用途；详情可改关键词 / 来源项目 / 角色归属；搜索命中这些字段。
- **成功标准**：改完保存再搜「项目名」或角色名能命中。
- **状态**：Complete

**待确认事项**：
- [x] 去重范围：默认 **同一 owner 全局**（跨库也算重复）。若你希望「角色库和场景库可各存一份」，改为按库去重。
- [x] 重复时默认 **拒绝并指出已有条目**，对话框提供「仍要入库」。不做感知哈希（压缩率不同、裁切不同不算重复）。
- [x] 本轮不做：文件夹监视、云盘同步、以图搜图去重。

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：库可写 `purpose`；条目可写关键词 / 来源项目 / 角色归属；同一 owner 下相同存储字节 SHA-256 入库返回 409 `duplicate_asset`，勾选「仍要入库」才再存；画布多选与本地文件可批量入库，失败或重复不阻断其余。
- **偏差说明**：去重哈希与 Artifact 存储字节一致（先按入参字节查重，落盘后写入 `artifact.sha256`）。未做感知哈希。旧条目缺 `content_sha256` 时不会被这次去重命中。
