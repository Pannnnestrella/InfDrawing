# InfDrawing 任务状态

## 2026-10-06 多轮编辑分栏与本轮详情

- `done`：内部四处分栏可拖；浮动窗恢复 VersionDetails（指令/参考图/实际提示词）
- 规划：`.planning/20261006_cedit_resizable_panes.md`

## 2026-10-06 入库归库 / 用途 / 去重

- `done`：库用途、关键词/来源/角色、owner 全局 SHA-256 去重（409 + force）、批量入库
- 规划：`.planning/20261006_library_ingest_meta_dedup.md`

## 2026-10-06 素材库 VLM 标注

- `done`：可命名库 + 右键入库 + Qwen-VL 标注 + 文本检索贴回画布
- `done`：拆解后入库静默失败（多选顶层 + 面板刷新 + MIME sniff）
- 规划：`.planning/20261006_asset_library.md`

## 2026-10-06 多轮编辑浮动预览

- `done`：对话栏入口弹出可拖动窗口；修改树切预览；导入画布；不再自动铺图
- 规划：`.planning/20261006_cedit_float_preview.md`

## 2026-10-06 元素拆解换云端模型

- `done`：有 DashScope key 时 decompose 走千问改图拆层；失败回退 rembg
- 规划：`.planning/20261006_decompose_cloud.md`

## 2026-10-06 混合生成 + 收回画布

- `done`：小物件 mask 三轮对照；背景/整主体走整图，零件走万相 mask
- `done`：首页左侧坞；`/studio` 重定向；新图贴在选中图右侧

规划来源：`.planning/20261006_cedit_hybrid_on_canvas.md`

## 2026-10-06 自动 mask + inpaint 对照

- `done`：实体框自动 mask；万相 `description_edit_with_mask` 官方样例 + 骑士对照已归档
- `planned`：Stage 2 是否接入 Studio，等看图决定

规划来源：`.planning/20261006_cedit_auto_mask_inpaint.md`

## 2026-10-06 Studio 策略与模型选择框

- `done`：每轮可选 `prompt_style` / `image_provider`；capabilities 暴露选项
- `done`：EditComposer 双下拉 + sessionStorage；版本详情展示本轮选择

规划来源：`.planning/20261006_cedit_prompt_style_ui.md`

## 2026-10-06 删除修改树节点

- `done`：删节点+子树；禁删根/busy；指针回父；Studio「删除当前节点」

规划来源：`.planning/20261006_cedit_delete_version.md`

## 2026-10-06 取消生成侧裁剪贴回

- `done`：生成始终整图；删除 crop-edit-paste；保留锚点参考图与 prompt 区域框

规划来源：`.planning/20261006_cedit_drop_crop_edit.md`

## 2026-10-06 级联锁定 + 硬贴回可选

- `done`：锁父级联锁后代；父锁时子项不可单独解锁
- `done`：硬贴回默认关（`INFD_CEDIT_LOCK_PASTE`）；开启时只贴有锚点的锁定框

规划来源：`.planning/20261006_cedit_cascade_lock_optional_paste.md`

## 2026-10-06 阿里改图 + 区域约束

- `done`：`qwen-image-edit-plus` 作为默认可切换 ImageEditor（`primary_last`，最多 2 张参考图）
- `done`：点选实体覆盖 intent；局部操作 crop-edit-paste；锁定框硬贴回（后改为默认关）
- `done`：主体框构图偏移在 VLM 之前失败并重试
- `planned`：同一骑士源图用阿里改图复跑 A 支，记录价差与画质

规划来源：`.planning/20261006_cedit_dashscope_and_regions.md`

## 2026-10-06 落盘与双分支实验

- `done`：memory 模式会话/版本/artifact 元数据写入 `data/cedit/`
- `done`：双分支六轮实验并归档到 `data/logs/20261006_cedit_two_branch/`
- `done`：重启后端后会话仍可打开

规划来源：`.planning/20261006_cedit_persist_two_branch.md`

## 2026-10-05 实体定位改进

- `done`：Stage 1 选型对比（默认 `qwen3-vl-plus`，`xyxy_1000`）
- `done`：场景解析接入 Qwen-VL，三种坐标格式
- `done`：手动校正框后端（此前已实现，测试覆盖）
- `done`：手动校正框前端（此前已实现）
- `planned`：完整三轮生图 e2e（定位本身已用真实会话验证）

规划来源：`.planning/20261005_cedit_entity_grounding.md`

## 2026-10-05 多轮可控编辑

- `done`：领域模型与仓储（Memory + SQL，迁移 0002）
- `done`：VLM 场景解析与意图解析
- `done`：Prompt 编译、参考图锚定、多图 edits 和比例处理
- `done`：VLM 验收（实体分数、锚点复核、构图）、重试、编排
- `done`：API、scope、能力探测
- `done`：前端 `/studio` 工作台
- `done`：端到端验证与 `docs/controlled_edit.md`
- `planned`：验收模型偏宽松，考虑加确定性构图检查（主体 bbox 比例）或换更强的 VLM

规划来源：`.planning/20261005_controlled_multi_turn_edit.md`

## 2026-10-04 AI 多会话历史

- `done`：ChatSession 模型 + localStorage
- `done`：发送时 beginSession + useChatMessages 多会话
- `done`：SessionSwitcher UI（切换 / 新对话 / 清空）
- `done`：单测与规划完成记录

规划来源：`.planning/20261004_ai_chat_history.md`

## 自动路由与生产化（历史）

- `done`：架构基线、测试修复与 Python 环境确认
- `done`：OpenAI/Ollama Provider、自动意图路由与前端自动模式
- `done`：API Key 鉴权与 Jobs/Artifacts API
- `done`：PostgreSQL、Redis、对象存储与异步 Worker
- `done`：并发控制、安全加固与审计
- `done`：Docker Compose、可观测性、测试、压测脚本与文档

部署环境待验证：真实容器启动、GPU 推理和实际负载测试。

规划来源：`.planning/20260902_production_ai_routing.md`
