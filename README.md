# InfDrawing

类似 Lovart 的 AI 创意画布产品（工程型项目）。Web 端提供无限画布交互，后端负责意图识别、LLM 推理与图像生成管线。

**目标**：交付一个可展示的作品集 demo（本地录屏）。

---

## 快速导航

| 文档 | 说明 |
|------|------|
| [**进度.md**](进度.md) | **项目进度追踪**（里程碑、MVP 清单、下一步） |
| [**docs/environment_setup.md**](docs/environment_setup.md) | **本地环境部署指南**（Ollama + ComfyUI，Windows 实测） |
| [**docs/production_deployment.md**](docs/production_deployment.md) | 单机生产部署、运维、备份与回滚 |
| [**docs/api_usage.md**](docs/api_usage.md) | Production jobs API、SSE/WS 与调用示例 |
| [**docs/threat_model.md**](docs/threat_model.md) | 部署威胁模型与安全边界 |
| [**docs/deployment_interview_notes.md**](docs/deployment_interview_notes.md) | 部署方案面试说明与实现边界 |
| [`.planning/20250608_tech_stack_selection.md`](.planning/20250608_tech_stack_selection.md) | 技术选型（已 Approved） |
| [`AGENTS.md`](AGENTS.md) | Cursor Agent 项目指令 |

---

## 技术架构（阶段一）

| 层级 | 职责 | 选型 |
|------|------|------|
| 交互层 | 无限画布、图层、Mask | Next.js + tldraw |
| 中控层 | 意图识别、Prompt 改写 | FastAPI + DeepSeek（默认）/ OpenAI / Ollama（可选） |
| 执行层 | txt2img / inpaint / 拆解 / 文字编辑 | 本地 ComfyUI（SD 1.5）或云端 OpenAI Images / 万相 DashScope |

---

## 一键启动（推荐）

**前置**：已完成 [环境部署](docs/environment_setup.md)（Ollama、ComfyUI、backend `.venv`、frontend `npm install`）。Ollama 需已在后台运行。

```powershell
# 仓库根目录
.\scripts\dev.ps1          # 启动 ComfyUI + 后端 + 前端，并打开浏览器
.\scripts\dev.ps1 status   # 检查四个服务健康状态
.\scripts\dev.ps1 stop      # 停止由脚本启动的进程
.\scripts\dev.ps1 restart   # 重启
```

脚本会为 ComfyUI、FastAPI、Next.js 各开一个 **PowerShell 窗口**（便于看日志）。首次启动 ComfyUI 可能需 30–60 秒。

| 服务 | 地址 |
|------|------|
| 前端（画布） | http://127.0.0.1:3000 |
| 后端 API / Swagger | http://127.0.0.1:8000/docs |
| ComfyUI | http://127.0.0.1:8188 |
| Ollama | http://localhost:11434 |

**可选环境变量**（路径与端口非默认时）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `INFD_COMFYUI_DIR` | `D:\ComfyUI` | ComfyUI 安装目录 |
| `INFD_COMFYUI_ENV` | `comfyui` | ComfyUI 使用的 Conda 环境名 |
| `INFD_COMFYUI_PORT` | `8188` | ComfyUI 端口 |
| `INFD_BACKEND_PORT` | `8000` | FastAPI 端口 |
| `INFD_FRONTEND_PORT` | `3000` | Next.js 端口 |
| `INFD_LLM_PROVIDER` | `deepseek` | 意图 LLM：`deepseek` / `openai` / `ollama` |
| `INFD_DEEPSEEK_API_KEY` | （空） | DeepSeek 意图识别（推荐，无需 Ollama） |
| `INFD_DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek 模型 |
| `INFD_OPENAI_API_KEY` | （空） | OpenAI 意图（可选）+ Images 出图/改图 |
| `INFD_OPENAI_IMAGE_MODEL` | `gpt-image-1` | OpenAI Images 模型 |
| `INFD_DASHSCOPE_API_KEY` | （空） | 阿里云百炼 / 万相出图与局部重绘 |
| `INFD_DASHSCOPE_T2I_MODEL` | `wanx2.1-t2i-turbo` | 万相文生图模型 |
| `INFD_DASHSCOPE_EDIT_MODEL` | `wanx2.1-imageedit` | 万相局部重绘模型 |

**能力自检**（后端启动后）：

```powershell
backend\.venv\Scripts\python.exe scripts\check_capabilities.py
```

---

## 手动启动

若不想用脚本，可按顺序开四个终端：

```powershell
# 1. Ollama — 通常安装后自启，无需手动操作

# 2. ComfyUI
cd D:\ComfyUI
conda activate comfyui
python main.py --lowvram --port 8188

# 3. 后端
cd backend
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 4. 前端
cd frontend
npm run dev
```

> Windows 上若 `uvicorn app.main:app --reload` 无输出即退出，请改用 `python -m uvicorn`（见上文）。

联调步骤与验收清单见 [`docs/environment_setup.md` §7.1](docs/environment_setup.md)。

---

## 单机 Production Compose

生产拓扑入口为 [`compose.production.yaml`](compose.production.yaml)，包含 frontend、api、API/GPU/CPU worker、专用迁移服务、PostgreSQL、Redis、MinIO 与 Nginx；Prometheus/Grafana 为可选 profile。ComfyUI 默认使用外部服务，也提供需要自行构建镜像和准备模型的显式 profile。

后端已实现 PostgreSQL jobs、Alembic、Redis/arq、API Key 鉴权与过期、owner 隔离的 S3 artifacts，以及 `agent_route` 和四类图像 durable handlers。浏览器前端支持自动意图模式、session 级 API Key 和同源任务事件代理；后端提供 `/ready` 与 `/metrics`。真实 PostgreSQL、Redis、MinIO、ComfyUI 容器联调仍需在具备 Docker 与 GPU Runtime 的目标主机完成。详见 [`docs/api_usage.md`](docs/api_usage.md)。

```powershell
Copy-Item .env.production.example .env.production
# 按 deploy/secrets/README.md 创建本机 secret 文件并配置 TLS

docker compose --env-file .env.production -f compose.production.yaml config --quiet
docker compose --env-file .env.production -f compose.production.yaml build
# migrate 为一次性服务；api 与 worker 会等待 alembic upgrade head 成功
docker compose --env-file .env.production -f compose.production.yaml up -d

# 安全的只读 smoke；基础负载脚本默认仅显示计划，不发送请求
backend\.venv\Scripts\python.exe scripts\smoke_production.py --base-url https://draw.example.com
backend\.venv\Scripts\python.exe scripts\load_probe.py
```

部署顺序、TLS、API Key bootstrap、迁移、备份恢复、容量清理、日志指标与回滚步骤见 [`docs/production_deployment.md`](docs/production_deployment.md)。

---

## 目录结构

```
├── README.md
├── 进度.md                          # 项目进度追踪
├── scripts/
│   ├── dev.ps1                      # 一键启动 / 停止 / 状态检查
│   ├── check_capabilities.py        # 环境能力探测 CLI
│   ├── smoke_production.py          # 生产只读 smoke 检查
│   └── load_probe.py                # 默认 dry-run 的有界基础负载探针
├── deploy/                           # Dockerfile、Nginx、可观测性与 secret 说明
├── compose.production.yaml           # 单机 production 编排
├── AGENTS.md                        # Cursor Agent 主指令（auto-generated）
├── docs/
│   └── environment_setup.md         # 环境部署指南
├── .agent-rules/                    # Agent 规则源文件（编辑后需 sync）
├── .planning/                       # 任务规划与审批记录
├── .cursor/                         # IDE 与会话状态（含 dev-services.json）
├── frontend/                        # Next.js 16 + tldraw 无限画布
│   └── src/
│       ├── app/                     # 页面布局
│       ├── canvas/                  # 画布、Mask、右键菜单
│       ├── agent-panel/             # 侧栏对话 UI
│       │   └── hooks/               # 按模式拆分的 flow hooks
│       └── lib/                     # API、WebSocket、canvas-bridge
└── backend/                         # FastAPI 后端
    └── app/
        ├── api/                     # REST + WebSocket 路由
        ├── agent/                   # Ollama 意图规划
        ├── pipeline/                # ComfyUI 生图管线
        └── system/                  # GPU / 服务能力探测
```

---

## 主要功能（阶段一 MVP）

| 功能 | 入口 |
|------|------|
| 文生图 txt2img | 侧栏「生图」或画布右键 |
| 局部重绘 inpaint | 侧栏选图 + Mask 刷选 |
| 指令改图 image_edit | 侧栏选图 + 文字描述 → OpenAI Images（无需 Mask） |
| 元素拆解 | 侧栏 / 右键，rembg + inpaint 双图层 |
| 文字编辑 | OCR 检测 + inpaint 抹字 + 矢量叠字 |
| 引擎切换 | 侧栏「自动 / 本地 / 云端」；云端可选 OpenAI 或万相 |

侧栏会根据 `GET /system/capabilities` 自动灰显不可用功能。配置了 `INFD_OPENAI_API_KEY` 或 `INFD_DASHSCOPE_API_KEY` 后即可在无 ComfyUI 时用云端出图/改图。

---

## 近期工程改进（2026-07）

| 改进 | 说明 |
|------|------|
| **一键启动** | `scripts/dev.ps1` — 启停 ComfyUI / 后端 / 前端，含健康检查 |
| **WS 重连** | 生图任务 WebSocket 意外断开后自动重连；后端重放 `last_event` |
| **侧栏重构** | `ChatPanel` 拆为 `useTxt2ImgFlow` / `useInpaintFlow` 等 hooks，便于维护 |

提交：`1cd93c2` · 详细进度见 [**进度.md**](进度.md)

---

## Cursor Agent 工作流

规则源文件在 `.agent-rules/`，修改后运行同步脚本：

```bash
python .agent-rules/sync_agent_rules.py
```

**勿直接编辑** `AGENTS.md` / `.cursor/rules/*.mdc` — 同步脚本会覆盖。

| Pattern | 说明 |
|---------|------|
| 先规划后执行 | 重要任务在 `.planning/` 创建规划文件，等待批准 |
| 进度追踪 | 里程碑与 MVP 状态维护在 [`进度.md`](进度.md) |
| 阶段分离 | 阶段一原型不考虑性能/安全；阶段二再优化部署 |

---

## 开发阶段

| 阶段 | 目标 | 状态 |
|------|------|------|
| **阶段一 — 原型** | 无限画布 + Agent + 生图链路 + Lovart 式扩展 | 🟢 功能闭环，待录屏 demo |
| **阶段二 — 部署** | 云服务器流畅交互、性能与视觉优化 | ⏸ 未开始 |

详细进度见 [**进度.md**](进度.md)。
