# InfDrawing

类似 Lovart 的 AI 创意画布产品（工程型项目）。Web 端提供无限画布交互，后端负责意图识别、LLM 推理与图像生成管线。

**目标**：交付一个可展示的作品集 demo（本地录屏）。

---

## 快速导航

| 文档 | 说明 |
|------|------|
| [**进度.md**](进度.md) | **项目进度追踪**（里程碑、MVP 清单、下一步） |
| [**docs/environment_setup.md**](docs/environment_setup.md) | **本地环境部署指南**（Ollama + ComfyUI，Windows 实测） |
| [`.planning/20250608_tech_stack_selection.md`](.planning/20250608_tech_stack_selection.md) | 技术选型（已 Approved） |
| [`AGENTS.md`](AGENTS.md) | Cursor Agent 项目指令 |

---

## 技术架构（阶段一）

| 层级 | 职责 | 选型 |
|------|------|------|
| 交互层 | 无限画布、图层、Mask | Next.js + tldraw |
| 中控层 | 意图识别、Prompt 改写 | FastAPI + Ollama（Qwen2.5-7B） |
| 执行层 | txt2img / inpaint | ComfyUI（SD 1.5，API 模式） |

---

## 本地环境

新成员部署开发环境，请按顺序阅读：

1. [**docs/environment_setup.md**](docs/environment_setup.md) — 安装 Ollama、ComfyUI、模型下载与验收清单
2. [**进度.md**](进度.md) — 确认当前项目阶段与待办事项

**日常启动（生图时）：**

```powershell
# ComfyUI（另开终端）
cd D:\ComfyUI
conda activate comfyui
python main.py --lowvram --port 8188

# Ollama 通常后台自启；API: http://localhost:11434/v1
```

---

## 目录结构

```
├── README.md
├── 进度.md                          # 项目进度追踪
├── AGENTS.md                        # Cursor Agent 主指令（auto-generated）
├── docs/
│   └── environment_setup.md         # 环境部署指南
├── .agent-rules/                    # Agent 规则源文件（编辑后需 sync）
├── .planning/                       # 任务规划与审批记录
├── .cursor/                         # Cursor 规则与会话状态
├── frontend/                        # Web 前端（待初始化）
└── backend/                         # FastAPI 后端（待初始化）
```

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
| **阶段一 — 原型** | 无限画布 + 基本交互 + Agent + 生图链路 | 🟡 进行中 |
| **阶段二 — 部署** | 云服务器流畅交互、性能与视觉优化 | ⏸ 未开始 |

详细进度见 [**进度.md**](进度.md)。
