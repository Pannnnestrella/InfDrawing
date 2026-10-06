## 任务：云端出图 / 改图 API

**背景**：本地 ComfyUI/SD1.5 已闭环，质量与速度受限；配置里已有 `dashscope_api_key` 占位但无真实调用。接入 OpenAI Images 与阿里云 DashScope（万相）作为 txt2img/inpaint 云端后端，侧栏提供引擎切换。
**影响范围**：`backend/app/pipeline/image_providers/`、`config.py`、`txt2img_router.py`、`orchestrator.py`、`generate.py`、`capabilities.py`、`jobs.py`、前端 `agent-panel`、文档
**前置条件**：现有本地四条链路可用；OpenAI/Ollama 意图 Provider 已存在

### Stage 1: Provider 抽象与云端实现
- **目标**：`ImageProvider` + OpenAI / DashScope 实现（txt2img + inpaint）
- **成功标准**：mock HTTP 下两家均可返回图片 bytes
- **状态**：Complete

### Stage 2: 路由、编排与 capabilities
- **目标**：resolver / orchestrator / generate / capabilities / jobs 打通云端 backend
- **成功标准**：`backend=openai|dashscope|local|auto` 可解析并执行
- **状态**：Complete

### Stage 3: 前端引擎切换
- **目标**：侧栏 自动/本地/云端 + 云端二级厂商选择
- **成功标准**：txt2img/inpaint 请求携带 backend
- **状态**：Complete

### Stage 4: 测试与文档
- **目标**：单元测试 + README / environment_setup / 进度更新
- **成功标准**：相关 pytest 通过；文档含环境变量说明
- **状态**：Complete

**待确认事项**：已确认 — Provider=OpenAI+DashScope；范围=txt2img+inpaint；UX=侧栏手动切换

## 完成记录

- **完成时间**：2026-10-04
- **实际结果**：实现统一 ImageProvider、OpenAI/DashScope txt2img+inpaint、resolver/capabilities/jobs、侧栏引擎切换与文档
- **验证结果**：后端 pytest 86 通过；新增 cloud provider / resolver / capabilities 用例
- **偏差说明**：DashScope inpaint 依赖 getPolicy 临时 oss:// URL；真实账号联调需用户自行配置 Key
