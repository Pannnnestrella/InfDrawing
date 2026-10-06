# 关键发现

## 2026-10-06 素材库

- 去重按 **owner 全局 SHA-256**（存储字节，与 Artifact `sha256` 一致），换文件名仍算重复；不感知压缩/裁切。409 `duplicate_asset` 带回 `existing_id`；`force=true` 才再存一份。旧条目缺 `content_sha256` 不会被命中。
- 画布 image shape 无后端 artifact ID；入库必须导出像素再走 ArtifactService。
- Caption 复用 `scene_vision_client()`（默认 `qwen3-vl-plus`），不要用 OCR `app/api/vision.py`。
- 检索 MVP 用标题/标签/物体/描述/风格子串，不做 embedding。`shape_feat` 预留空。
- 静默失败常见因：① 拆解后 bg+fg 多选，旧逻辑要求单选导致无法入库或误导 UI；② 面板已打开时入库成功但不刷新，右侧仍显示旧场景元数据。修复：z-index 顶层导出 + `dataRevision` 刷新选中最新条。

## 2026-10-06 元素拆解云端

- `image-instance-segmentation` 能拿到 task_id，但 `task_status` 长期 PENDING（同时处理中上限 1；取消积压后仍不跑）。oss:// 需 `X-DashScope-OssResourceResolve: enable`。
- 可用路径：`qwen-image-edit-plus` 把背景换成纯色/改掉背景，用角点色或与原图差分做 alpha，前景贴回原图像素；第二轮指令去掉主体补场景。

## 2026-10-06 自动 mask + 万相 inpaint

- `wanx2.1-imageedit` + `description_edit_with_mask` 可用。官方文档白=改、黑=留；本地图用 `data:image/png;base64` 比 OSS getPolicy 更贴文档。
- 小白区连改可用：剑→木杖+水晶、盾→南瓜，脸和风景基本不动；物件像贴图、握持关系弱。手套金线过小，几乎无变化。大面积换背景仍应走千问整图。

## 2026-10-06 Studio 策略 / 模型选择

- 浮动窗曾用 `floating ? null : VersionDetails` 藏掉本轮指令/参考图/编译提示词；现已在右侧底部分栏恢复。
- capabilities `image_options` 用 `provider|model` 分号拼接（如 `dashscope|qwen-image-edit-plus;openai|gpt-image-1`），前端解析后生成下拉。
- 本轮 `prompt_style` / `image_provider` 写入版本 JSON；未传时回落 `INFD_CEDIT_*` settings。
- sessionStorage 键：`infd.cedit.prompt-style`、`infd.cedit.image-provider`。

## 2026-10-06 阿里改图与区域约束

- Qwen 多图编辑以最后一张图定输出比例，参考图必须先发、当前图后发；prompt 编号随之改为 `primary_last`。
- 万相 `wanx2.1-imageedit` 是单图/mask，带不了锁定 crop，不能替代 `qwen-image-edit-plus`。
- 环境/发型等出框操作必须走整图 + 锁定贴回；换剑/换色等单目标且有框的操作才走 crop-edit-paste。
- `get_controlled_edit_service()` 的 `return _service` 不能写进 `_cedit_editor_factory()`，否则进程级服务拿不到实例。
- `environment.sky` 测试场景默认无 bbox，prompt 不会出现 `occupies x=`；断言前要先写入框。
- v8「换北欧城堡」右上角矩形骑士残影：曾是 `uses_local_crop` 误把城堡当局部目标贴回。生成侧 crop-edit-paste 已彻底取消，统一整图 + 锁定锚点参考图 + prompt 区域框。
- Studio「与上一版对比」滑块左侧会标「上一版」，勿与生成残影混淆。

## 2026-10-05 实体定位

- `INFD_ALIBABA_API_KEY` 可作为 DashScope key 的别名；Settings 能读到。
- 同一张骑士源图上，gpt-4o 的脸/剑/盾框明显偏；三个 Qwen 模型（qwen3-vl-plus / flash / qwen-vl-max）框都落在正确部位，坐标格式都是提示词要求的 `xyxy_1000`。
- 默认选用 `qwen3-vl-plus`：源图 14 个实体、约 22s；flash 更快（约 15s）但框质量接近。对比图在 `data/logs/20261005_cedit_grounding/`。

## 2026-10-05 多轮可控编辑

- 没有 mask 时，OpenAI edits 会逐轮推近镜头、改表情；只靠 prompt 约束不够，需要 VLM 验收加修改树兜底。
- gpt-4o 让它直接给 bbox 时很粗；改用 `box_2d`（0–1000 网格，`[x_min, y_min, x_max, y_max]`）后明显变准。
- gpt-4o 当验收模型偏宽松：run3 的 v2 镜头明显推近，构图仍给 1.0；多轮下画面纹理逐渐退化，它也看不出来。
- 全局异常处理会把 `HTTPException.detail` 转成字符串，所以 409 冲突要用 `error_response(..., details)` 返回结构化实体列表。
- OpenAI 偶发 `httpx.ReadError`，`multi_image_edit` 需要做传输层重试（只看 `__cause__` 是否为 `TransportError`）。

## 2026-10-04

- AI 侧栏历史为多会话：`一次发送 = 一个 ChatSession`，存 `localStorage`（`infdrawing-chat-sessions-v1`），上限 30。
- `beginSession` 与紧随其后的 `appendMessage` 需同步 ref（`activeSessionIdRef`），否则同 tick 会写到旧会话或误建 fallback。
- 结果图持久化时 `blob:` 转 `data:`，避免刷新后失效。

## 2026-09-02

- 当前自动路由入口已有 Ollama JSON plan，但前端通常传 `intent_override`，且未接通 `TOOL_REGISTRY` 自动执行。
- 当前 `TaskManager`、事件队列与 `last_event` 均为进程内状态，服务重启后丢失。
- 输出与上传使用本地文件系统；无数据库、Redis、对象存储、鉴权或限流。
- 云端图像：`ImageProvider` 已实现 OpenAI Images 与 DashScope 万相（txt2img + inpaint）；侧栏支持自动/本地/云端切换。
- 生产化首版已确定：OpenAI 官方 API、API Key 鉴权、单机 Docker Compose，并保留 Ollama/ComfyUI 本地后端。
- 工作区存在用户生成图片、缓存和未提交文档，本任务不删除或覆盖这些文件。
- 持久 Jobs API 支持 `agent_route`、`txt2img`、`inpaint`、`decompose`、`text_edit`；图像任务通过 owner 保护的 artifact ID 传递输入和输出。
- 旧 `/generate/*` 与进程内 WebSocket 保留给画布兼容链路，任务绑定 API principal owner；程序调用推荐持久 Jobs SSE。
- API Key 使用随机 locator 加 HMAC-SHA256 pepper，支持 scope、吊销和过期。
- 生产依赖采用 PostgreSQL、Redis/arq、MinIO/S3 和独立 API/GPU/CPU worker；迁移服务先于 API 与 Worker。
- 浏览器 Key 仅存 sessionStorage，任务事件通过 Next.js 同源 SSE 代理在服务端添加 WebSocket 鉴权 header。
- 当前未实测真实 Docker/GPU 拓扑；本地 Python 版本与项目 3.11 规范不一致。
