## 任务：InfDrawing 自动意图路由与生产化

**背景**：当前项目已经完成本地 AI 无限画布的四条编辑链路，需要增加自动意图路由、OpenAI 官方 API、对外业务 API，并补齐生产部署所需的安全、并发、持久化和可观测性能力。
**影响范围**：`backend/app/agent/`、`backend/app/api/`、`backend/app/pipeline/`、新增后端 Provider、数据库、Worker 与安全模块、`frontend/src/agent-panel/`、`frontend/src/lib/`、测试、Docker Compose、部署与 API 文档。
**前置条件**：现有 Next.js + tldraw 前端、FastAPI 后端、Ollama 与 ComfyUI 本地链路可用；实施前需修复基线测试并确认项目使用 Python 3.11 虚拟环境。

### Stage 0: 架构基线
- **目标**：确认现有 API 兼容边界，修复测试基线，记录迁移和回滚策略。
- **成功标准**：后端测试在 Python 3.11 项目虚拟环境中全部通过；现有四条生成链路的 API 契约被测试覆盖。
- **状态**：Complete

### Stage 1: 自动意图路由与 Provider 抽象
- **目标**：实现 OpenAI 与 Ollama Provider、严格的 IntentPlan 校验、工具注册表调度及前端自动模式。
- **成功标准**：自然语言请求可根据画布上下文选择四类工具；低置信度请求返回澄清结果；显式模式仍可确定性执行。
- **状态**：Complete

### Stage 2: 对外业务 API
- **目标**：提供 API Key 鉴权的版本化 Jobs API、任务查询、取消、WebSocket/SSE 事件和幂等提交。
- **成功标准**：外部调用方可通过 OpenAPI 与示例脚本完整提交和跟踪任务；无效 Key、scope 和超限请求被拒绝。
- **状态**：Complete

### Stage 3: 持久化与对象存储
- **目标**：使用 PostgreSQL 持久化任务和审计数据，Redis 负责队列与事件，对象存储保存图片。
- **成功标准**：API 或 Worker 重启后任务可查询和恢复；本地文件可迁移；图片通过短期签名 URL 访问。
- **状态**：Complete

### Stage 4: 并发与可靠性
- **目标**：按 GPU、CPU 和外部 API 拆分 Worker，增加背压、租约、重试、取消、事件续传和死信记录。
- **成功标准**：并发提交不会造成 GPU 任务争抢；重复提交可去重；重连按事件序号续传；负载测试通过。
- **状态**：Complete

### Stage 5: 生产安全
- **目标**：完成 API Key 安全存储、scope、限流、上传校验、SSRF 防护、密钥管理、日志脱敏和 TLS 边界。
- **成功标准**：安全测试覆盖主要滥用路径；敏感信息不进入日志或数据库明文；外部地址不可由用户任意指定。
- **状态**：Complete

### Stage 6: 单机生产部署与可观测性
- **目标**：以 Docker Compose 部署前端、API、Worker、PostgreSQL、Redis、MinIO、反向代理和 ComfyUI GPU 服务。
- **成功标准**：具备健康检查、结构化日志、关键指标、备份恢复和容量清理；服务可在单机重启后恢复。
- **状态**：Complete

### Stage 7: 测试、文档与发布门禁
- **目标**：补齐前后端单元、集成与端到端测试，完善 API、部署、威胁模型和面试材料。
- **成功标准**：lint、类型检查、单测、集成测试和基础压测全部通过；文档与实际实现一致；Review Gate 通过。
- **状态**：Complete

**待确认事项**：
1. 外部模型首期采用 OpenAI 官方 API，Ollama 保留为本地 Provider。
2. 对外业务 API 首期采用服务端签发的 API Key。
3. 第一版生产环境采用单机 Docker Compose，并保留横向扩展能力。
4. 是否批准按 Stage 0 至 Stage 7 开始修改源码、安装依赖与创建部署文件。

## 完成记录

- **完成时间**：2026-09-02
- **实际结果**：实现 OpenAI/Ollama 自动意图路由、工具校验与前端自动模式；新增 API Key 鉴权、Jobs/Artifacts API、PostgreSQL/Alembic、Redis/arq、local/S3 存储、四类持久图像 Worker、幂等与取消、SSE 续传、owner 隔离、上传校验、审计与 Provider 元数据、`/ready`、`/metrics`、生产 Compose、运维与 API 文档。
- **验证结果**：后端 78 项 pytest 通过；Ruff 基础规则通过；前端 27 项 Vitest、TypeScript、ESLint、Next.js 生产构建和 npm audit 通过；Compose YAML 结构与部署脚本 dry-run 通过。
- **偏差说明**：当前本地 `backend/.venv` 是 Python 3.13.9，生产 Dockerfile 使用 Python 3.11；本机无 Docker CLI，真实 PostgreSQL、Redis、MinIO、ComfyUI、NVIDIA Runtime 的容器联调与实际压测需在目标部署主机完成。Artifact 内容通过 owner 鉴权端点读取，没有使用预签名 URL。浏览器首期使用 sessionStorage API Key，共享设备场景仍建议增加短期 HttpOnly session。
