# 会话进展

## 2026-10-06

- 多轮编辑：内部区域可拖条调节；浮动窗恢复本轮指令、参考图、实际发送提示词。SplitPane + studio-split vitest 通过。
- 入库增强落地：库 `purpose`、条目 keywords/source_project/character_name、SHA-256 去重 409+force、画布多选+本地文件批量。`tests/assets` 13 通过；library vitest 8 通过；tsc 通过。
- 网易作业素材包：`docs/submission/materials/`（不改现有 docx）。补第 4–6 节正文、实验表、截图清单、录屏脚本；抽出 Word 三张图。提醒 GitHub main 尚未包含本次模块。
- 修标注入库静默失败：拆解多选取 z-index 最上层；面板 `notifyLibraryDataChanged` 刷新并选中最新条；导出强制 PNG；空 MIME 后端 sniff。assets pytest + tsc + library vitest 通过。
- 素材库已落地：右键入库、命名库、Qwen-VL 标签/风格描述、文本检索、贴回画布。形状搜索本轮不做。`tests/assets` 与前端 library vitest 通过。
- 开始实施素材库：右键入库、命名库、Qwen-VL 标签/风格描述、文本检索。形状搜索本轮不做。
- 多轮编辑改为 AI 对话入口弹出可拖动窗口：预览 + 拖动对比 + 导入画布；首页不再常驻左侧坞。
- 元素拆解改走 `qwen-image-edit-plus`（品红/差分抠前景 + 指令补背景）。骑士对照 `data/logs/20261006_decompose_cloud/`。阿里免费 `image-instance-segmentation` 长期 PENDING，未采用。
- 小物件万相 mask 三轮（剑→法杖、盾→南瓜、手套金线）可用，对照 `data/logs/20261006_cedit_mask_small/compare.png`。换背景仍走千问整图。
- 首页左侧多轮编辑坞；`/studio` 重定向 `/`。新版本贴在选中图右侧。
- 万相 mask 已打通：官方 `description_edit_with_mask` 样例成功；inpaint 改走 data URL。骑士对照归档 `data/logs/20261006_cedit_auto_mask/`。
- Studio 双下拉：提示词策略（完整约束 / 仅描述目标）与生图模型（通义 / OpenAI）；按轮覆盖 settings，记入 sessionStorage。`tests/controlled_edit` 76 通过。
- 实现 JSON 落盘：会话树与 artifact 索引每次写入都写到 `data/cedit/`。重启后端后 `Two-branch knight` 仍在。
- 可控编辑默认可走阿里 `qwen-image-edit-plus`；点选实体当目标；局部改 crop 贴回，锁定框从上一版贴回；主体框漂移先于 VLM 失败。
- 质量门禁：`tests/controlled_edit` 71 通过；前端 tsc / eslint / `controlled-edit-api` vitest 通过。骑士 A 支阿里复跑未做。
- 后端已重启：`features.controlled_edit.models.image` = `qwen-image-edit-plus`。`/studio` 打开 `Two-branch knight`（v1–v7 仍在），点选 Longsword 后出现「本轮目标」。
- 级联锁定 + 硬贴回默认关：锁父锁后代；`INFD_CEDIT_LOCK_PASTE=false`；开启时只贴有锚点框。`tests/controlled_edit` 75 通过。
- 取消生成侧 crop-edit-paste：始终整图编辑 + 锚点参考图 + prompt 目标框。`tests/controlled_edit` 72 通过。
- 提示词双策略：默认 `preserve`；`INFD_CEDIT_PROMPT_STYLE=target_only` 只描述改动与目标框。
- 修改树可删当前节点（含子树）；根节点与生成中不可删。
- 跑完双分支实验：A 武器/盾/盔甲，B 发型/帽子/背景。归档 `data/logs/20261006_cedit_two_branch/`。Studio 底部树为 v1–v4 主线加 v5–v7 分支。

## 2026-10-05 实体定位

- 用户已在 `backend/.env` 配置 `INFD_ALIBABA_API_KEY`，Settings 可读。
- Stage 1 对比完成：gpt-4o 框仍偏；qwen3-vl-plus / flash / max 均明显更好。默认 `qwen3-vl-plus`。
- 线上创建会话「Qwen grounding check」：脸/剑/盾框正确。
- 对比图与原始回复：`data/logs/20261005_cedit_grounding/`。

## 2026-10-05

- 用户批准多轮可控编辑方案（语义锁定 + 参考图锚定 + VLM 验收 + 修改树，不用 mask），实施完成。
- 后端 `app/controlled_edit/`，前端 `/studio`；scope 是 `controlled_edit`。
- 端到端跑了三次（`data/logs/20261005_controlled_edit_e2e/`，含 run2、run3）：第一次后补了传输重试；第二次后补了 `box_2d`、构图评分、对锚点复核。
- 浏览器验证 `/studio`：打开会话 → 回退到 v2 → 从 v2 分支出 v5。
- 质量门禁：后端 pytest 140 通过，Ruff 通过；前端 tsc、ESLint 通过，vitest 48 通过。
- 规划：`.planning/20261005_controlled_multi_turn_edit.md`

## 2026-10-04

- 用户确认 AI 多会话历史方案并完成实施。
- 新增 `chat-history` 持久化、`SessionSwitcher`、发送时 `beginSession`；Vitest 覆盖标题/读写/上限。
- 规划：`.planning/20261004_ai_chat_history.md` 已标记 Complete。

## 2026-09-02

- 用户批准自动意图路由与生产化规划。
- 已创建 `.planning/20260902_production_ai_routing.md`。
- 基线测试：35 项中 33 通过、2 失败，失败来自 rembg 可用性缓存影响 mock 隔离。
- 当前 `backend/.venv` 为 Python 3.13.9，与项目规定的 Python 3.11 不一致。
- 后端核心、前端自动模式、部署与运维文档正在并行实施。
- 已完成 OpenAI/Ollama 自动路由、工具注册表校验和前端自动/手动双模式。
- 已完成 API Key、Jobs/Artifacts API、PostgreSQL/Alembic、Redis/arq、S3/MinIO 适配和四类持久图像 Worker。
- 已完成 owner 隔离、SSE 续传、幂等冲突、取消、重试、GPU 并发槽位、上传校验、审计、Provider 元数据与日志脱敏。
- 已完成单机 Compose、迁移门禁、secret 加载、Nginx、Prometheus/Grafana、部署/API/威胁模型/面试文档。
- 质量门禁：后端 pytest 78 通过、Ruff 通过；前端 Vitest 27 通过、TypeScript/ESLint/build 通过、npm audit 0 漏洞。
- 环境限制：本地 venv 为 Python 3.13.9；没有 Docker CLI，真实容器与 GPU 联调待目标主机验证。
