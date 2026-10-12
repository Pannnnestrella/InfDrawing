# 会话进展

## 2026-10-12

- 多轮编辑 RGBA：`alpha.py` / `qwen_mask_prompt.py`；sizing `keep_alpha`；service Qwen vs Wan/Wanx 分流；Studio `bg-checkerboard`；`docs/controlled_edit.md` 透明表；`tests/controlled_edit` 96 通过。

## 2026-10-11

- 拆解偏移再修：根因是 tldraw `object-fit: cover` 对宽高比不一致的图层居中裁切；回贴前 `bakeLayerToShapeBox`，锚点几何不再与错误选中混用；后端 EXIF + 强制同尺寸。相关 vitest / `test_decompose` 通过。
- API Key 弹层裁切：`PopoverPanel` fixed 定位。设置页 Stage 1–2 落地：`SettingsDrawer`（凭证/引擎/可控编辑/环境）；Header 用「设置」替代 API Key；cedit 偏好 `subscribeCeditOptions` 与 Studio 同步。`tsc` + 相关 vitest 通过。
- 额度失败画布 toast：后端规范化欠费文案；`CanvasToastHost` 手动关闭；侧栏/管线额度错误同步上画布。规划 `.planning/20261011_quota_error_toast.md`。
- 修复选中误报：`selectionHint ?? "请选中…"` 在 hint=null 时仍显示未选中；`store.listen({scope:'all'})`；贴图导出重试。

## 2026-10-10

- 图层基础操作：新建透明层、复制/粘贴/创建副本、多选合并；`layer-composite` + bridge + 面板工具栏。`tsc` 与 vitest 通过。规划 `.planning/20261010_layer_ops.md`。
- 拆解修复：默认模型改 `qwen-image-2.0`；ComfyUI 不可达时 rembg 用原图作背景。
- 图层面板落地（按推荐项）：`layer-model` + bridge API + `layers/LayerPanel` 浮窗；侧栏「图层」入口；显隐走 `meta.hidden` + `getShapeVisibility`。`tsc` 与相关 vitest 通过。规划 `.planning/20261010_layer_panel.md`。

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

## 2026-10-11 本地部署启动
- 前端 http://127.0.0.1:3000 HTTP 200；后端因缺少 SQLAlchemy 启动失败。现有虚拟环境 Python 3.13，不符合项目 3.11 要求。补齐方案见 .planning/20261011_local_deployment.md，依赖安装待批准。

## 2026-10-12 本地部署完成
- 用户批准环境补齐；使用 Python 3.11.15 重建 backend/.venv，旧环境保留。依赖安装与 pip check 通过。
- 前后端与能力代理 HTTP 200，DeepSeek 连通正常，浏览器已打开；能力测试 9 passed。ComfyUI 未运行，当前 api_fallback。

## 2026-10-12 编辑历史恢复
- 按用户要求，将 data/data/cedit 的 sessions.json、artifacts.json 复制到 data/cedit；共享图片索引关联的 71 张图片复制到 data/artifacts，原文件保留，图片哈希一致。
- 重启后端后，前端代理返回 3 个编辑会话，14 个版本图片全部 HTTP 200。

## 2026-10-12 局部重绘规划
- 已创建不规则 Mask、SAM 2.1/3、手工圈选与 Crop/Stitch 六阶段方案；本轮未修改代码、安装依赖或调用付费模型。
- 等待用户批准：.planning/20261012_local_inpaint_crop_stitch_plan.md


## 2026-10-12 局部重绘实现完成
- 已按批准规划实现手工/SAM Mask 与 Crop/Stitch；安装 SAM 2.1 small 和 Ruff，补齐已有前端依赖。
- 实验网页 /inpaint-comparison/index.html 已启动并打开。万相 116.6 秒成功，Mask 外差异为 0；盾牌出现白块且风格偏移。Qwen 2.1 单次 182.85 秒读取超时，未重试。
- 后端 90 passed，前端相关 11 passed，TypeScript/ESLint/Ruff 通过；审查与限制见规划完成记录。


## 2026-10-12 整图对照与 Qwen 异步修复执行
- 用户明确要求原图万相重绘及 Qwen 2.1 修复，追加规划 Stage 7–8。
- 已实现官方异步 endpoint、任务提交/轮询分离、任务 ID 持久化与同任务恢复；不重试生成提交。
- 后端相关 105 项测试通过，Ruff 通过。网页已打开 HTTP 200，正在执行两次新增生成。

- 后续结果：万相原图输入 143.3 秒成功，原始输出 Mask 外变化 613919 像素、最大差值104；融合后均为0。Qwen Base64 异步提交62.24秒超时，无任务ID。
- 用户明确不希望临时存储上传，上传及追加生成未执行；默认传图仍为 Base64。已按要求重新打开网页展示现有万相对照。


## 2026-10-12 GitHub 版本发布
- 用户要求将当前版本推送 GitHub。发布范围为功能代码、测试、规划、文档及骑士当前会话指针；遗留图片删除、数据归档副本、本地服务状态、权重与实验大文件不纳入提交。
- 验证：后端相关105项、前端相关11项测试通过，TypeScript、ESLint、Ruff及 Review Gate 通过。Qwen 实际生成仍未成功，临时存储上传未执行，默认仍使用Base64。
