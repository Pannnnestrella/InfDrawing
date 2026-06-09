## 任务：InfDrawing 技术选型

**背景**：InfDrawing 目标是交付一个类似 Lovart 的 AI 创意画布作品集 demo。需在前后端分离架构下，选定无限画布、Agent 中控、图像管线三层技术栈，并区分阶段一（原型）与阶段二（部署）的约束。

**影响范围**：`frontend/`、`backend/`、`docs/`、后续依赖与基础设施决策

**前置条件**：项目模板已初始化（`AGENTS.md`、`.agent-rules/core.md`）

---

## 1. 总体结论

**建议采纳「三层架构」划分**，与收到的建议一致：

| 层级 | 职责 | 推荐选型 |
|------|------|----------|
| 交互层（皮囊） | 无限画布、图层、局部选区、Mask 生成 | **tldraw SDK + Next.js** |
| 中控层（大脑） | 意图识别、Prompt 改写、工具路由 | **FastAPI + 结构化 LLM（Qwen / 兼容 OpenAI API）** |
| 执行层（骨肉） | 文生图、图生图、局部重绘 | **ComfyUI（API 模式）为主，Diffusers 为辅** |

该组合与 `core.md` 中阶段一目标（画布 + 基本交互 + 上传/圈选）高度吻合，且学习曲线可控。

---

## 2. 对原始建议的评估

### 2.1 完全认同的部分

1. **不要从零手写无限画布** — 空间坐标变换、缩放平移、图层状态管理、性能优化均是非 trivial 工程，复用成熟引擎是正确决策。
2. **Agent 不是「多写几句 Prompt」** — Lovart 的核心差异在于「理解意图 → 拆解任务 → 选择工具链」，InfDrawing 应在后端显式建模 `Intent → Tool → Pipeline`。
3. **ComfyUI 应作为后端引擎而非面向用户的 UI** — 工作流 JSON 模板化 + FastAPI 动态注入参数，是业界成熟模式。
4. **WebSocket 回传进度与结果** — 生图任务耗时 10s–60s+，需要异步任务 + 实时状态推送。

### 2.2 需要修正或补充的部分

| 原建议 | 修正意见 | 理由 |
|--------|----------|------|
| Kopia 作为「开源版 Lovart 雏形」首选参考 | **降级为次要参考**；优先研读 **tldraw 官方 Image Pipeline / Agent Starter Kit** | Kopia 社区活跃度与维护不确定；tldraw 官方已提供 AI 画布、节点管线、Agent 集成的 MIT starter kits，文档与架构更可靠 |
| easy-vibe 含完整前后端逻辑可照搬 | **定位为方法论与产品设计参考，非可 fork 的代码库** | easy-vibe 的 Lovart 章节主要讲解 Lovart 产品工作流（Fast/Thinking Mode、参考锚定、工具调用），而非开源实现；Agent 层需自行设计 |
| 阶段一即上完整 ComfyUI 多工作流 | **阶段一收敛为 2–3 条核心工作流**（txt2img、img2img/inpaint） | 降低 GPU 环境与调试成本；先打通端到端再扩展 |
| Next.js / Vue3 均可 | **推荐 Next.js（React）** | `@tldraw/tldraw` 原生 React；Vue 需额外封装，无收益 |
| 未提及许可与部署成本 | **必须纳入选型** | tldraw SDK 4.0 起：开发环境免费，**生产部署需 license key**（100 天试用 / Hobby 水印 / 商业授权） |

---

## 3. 分层技术选型（详细）

### 3.1 前端 — 无限画布与交互

#### 选定方案

| 组件 | 选型 | 版本策略 |
|------|------|----------|
| 框架 | **Next.js 15（App Router）** | LTS 稳定版 |
| 语言 | **TypeScript** | 与 tldraw 生态一致 |
| 画布引擎 | **@tldraw/tldraw** | SDK 4.x |
| 状态管理 | tldraw 内置 Store + Records；业务状态用 **Zustand**（按需） | 避免重复造轮子 |
| 样式 | **Tailwind CSS** + 暗色主题 token | Lovart 暗色专业风（已确认） |
| 实时通信 | 原生 **WebSocket** 客户端 | 对接 FastAPI |

#### 选型理由

- tldraw 在无限画布领域已是事实标准：坐标系 `page ↔ screen` 转换、形状/图片资产管理、自定义 Shape 扩展均有成熟 API。
- 官方 Starter Kits 与 InfDrawing 目标直接相关：
  - **Agent Kit**：LLM 读取画布上下文并操作形状
  - **Image Pipeline Kit**：节点式 AI 图像工作流（类 ComfyUI 但基于 tldraw）
  - **Chat Kit**：画布 + 侧边对话，适合「刷涂 + 聊天指令」混合交互
- 阶段一可基于 `npm create tldraw` 引导模板快速启动。

#### 必须掌握的技术点（来自原建议，保留）

1. **坐标变换**：`editor.pageToScreen()` / `editor.screenToPage()`，将刷涂区域映射到原图像素坐标。
2. **Mask 生成**：在图片 Shape 上捕获笔刷轨迹 → 离屏 Canvas 渲染二值 Mask → 导出 PNG base64。
3. **Store 架构**：理解 `TLRecord` 增量同步，为后续「生成结果自动落位到画布」打基础。

#### 备选方案（不首选）

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| Excalidraw | 手绘风格、MIT | AI 图片编辑扩展弱 | 不适合 |
| Fabric.js / Konva | 灵活、免费 | 需自建无限画布与图层系统 | 工作量大 |
| React Flow | 节点图强 | 非无限画布产品形态 | 仅适合管线编辑子模块 |

#### 风险与应对

- **tldraw 生产许可**：Demo 仅本地录屏（已确认），无需 license key；阶段二若公网部署再申请 Trial/Hobby。
- **自定义 Inpainting UI**：tldraw 无开箱「局部重绘刷具」，需在自定义 Tool 或 Overlay 层实现（参考社区项目 `gpt-image-canvas` 的交互模式）。

---

### 3.2 中控层 — Agent 与意图识别

#### 选定方案

| 组件 | 选型 |
|------|------|
| API 框架 | **FastAPI 0.11x**（Python 3.11） |
| LLM 接入 | **OpenAI 兼容 API**（抽象 Provider 层） |
| 默认模型 | **Qwen2.5-7B-Instruct**（**Ollama 本地**，已确认） |
| Agent 模式 | **轻量 Intent Router**（阶段一），非完整 ReAct 框架 |
| 任务队列 | 阶段一：**内存队列 + BackgroundTasks**；阶段二：Redis + Celery/ARQ |
| 协议 | REST（提交任务）+ WebSocket（进度/结果） |

#### 架构设计（阶段一 MVP）

```
用户操作（刷涂 / 聊天 / 拖拽选图）
        ↓
前端 Context Bundle（选中 shape ID、截图缩略图、mask、用户文本）
        ↓
POST /api/v1/agent/plan
        ↓
LLM Structured Output → IntentPlan {
  intent: "inpaint" | "style_transfer" | "outpaint" | "txt2img" | ...
  refined_prompt: string
  negative_prompt: string
  target_tool: "comfyui_inpaint_v1"
  params: { strength, steps, ... }
}
        ↓
Pipeline Executor 调用 ComfyUI / Diffusers
        ↓
WebSocket 推送 progress → result_image_url
        ↓
前端将新图 Shape 放置在原图旁
```

#### 选型理由

- FastAPI 与 Python 图像生态（Pillow、numpy、diffusers）同栈，避免 Node 后端再桥接 Python。
- 阶段一不需要 LangGraph / AutoGen 等重型 Agent 框架；**结构化 JSON 输出 + 工具注册表**即可演示「意图识别」价值。
- easy-vibe 的价值在于理解 Lovart 的 **Thinking Mode 产品逻辑**（意图分解、参考锚定、后处理工具链），应在 InfDrawing 中用 `IntentPlan` schema 复现，而非依赖其代码。

#### 备选方案

| 方案 | 适用场景 |
|------|----------|
| LangGraph | 阶段二多步 Agent、复杂分支 |
| 纯规则引擎（无 LLM） | 仅演示画布，无意图识别卖点 |
| Node.js 中控 | 团队只熟 TS；但图像管线仍要调 Python |

#### 阶段一 Intent 收敛（已确认范围）

1. `txt2img` — 纯文本生图 ✅
2. `inpaint` — 局部重绘（核心，对齐 Lovart 刷涂）✅
3. `img2img` — 风格迁移 / 整图重绘（时间允许时做）
4. `outpaint` — 扩图 ❌ 阶段一不做，留待阶段二 / 大显存环境

---

### 3.3 执行层 — 图像处理管线

#### 选定方案（分阶段）

| 阶段 | 主引擎 | 备用 |
|------|--------|------|
| 阶段一（本机 8GB 显存） | **ComfyUI** 本地，`--lowvram` + 轻量模型 | **Diffusers** 脚本化 inpaint（调试备用） |
| 阶段二（大显存服务器） | ComfyUI + SDXL / 更高分辨率工作流 | 多 GPU worker 池 |

#### ComfyUI 集成模式（推荐）

1. 在 ComfyUI 中设计并验证工作流（txt2img、inpaint）。
2. 导出 `workflow_api.json`，将可变参数（`prompt`、`image_path`、`mask_path`、`seed`）标记为模板占位符。
3. FastAPI 收到请求后：
   - 保存上传图/Mask 到 `data/uploads/`
   - `POST http://127.0.0.1:8188/prompt` 提交工作流
   - `ws://127.0.0.1:8188/ws?clientId={uuid}` 监听执行进度
   - 完成后从 `/history/{prompt_id}` 或 WebSocket 二进制流取图
4. 通过 WebSocket 转发进度给前端。

#### 模型建议（按显存分档）

**阶段一 — 本机 8GB 显存（已确认）**

| 用途 | 模型 | 关键参数 |
|------|------|----------|
| 通用生图 | **SD 1.5**（`v1-5-pruned-emaonly.safetensors`） | 分辨率 **512×512**，fp16，steps 20–28 |
| 局部重绘 | **SD 1.5 Inpainting**（`sd-v1-5-inpainting.ckpt`） | 同上；Mask 区域不宜过大 |
| ComfyUI 启动 | `--lowvram` 或 `--novram` | 避免与 Ollama 同时占满显存 |
| 加速（可选） | LCM LoRA for SD1.5 | steps 降至 4–8，demo 录屏更流畅 |

> **8GB 约束**：SDXL base 约需 6–8GB+，与 Ollama 7B 争抢显存易 OOM。阶段一**禁用 SDXL**；Ollama 与 ComfyUI **不要同时跑满 GPU**——Agent 规划完成后再触发 ComfyUI，或 Ollama 用 CPU offload（较慢但稳）。

**阶段二 — 大显存服务器（未来）**

| 用途 | 模型 | 说明 |
|------|------|------|
| 通用生图 | SDXL 1.0 base | 768×768 或更高 |
| 局部重绘 | SDXL Inpaint | 配合 Mask 输入 |
| 加速 | LCM / Lightning LoRA | 降低延迟 |

#### 备选方案

| 方案 | 优点 | 缺点 |
|------|------|------|
| 纯 Diffusers | Python 内嵌、无 ComfyUI 进程 | 复杂管线编排能力弱 |
| Automatic1111 API | 上手快 | 工作流灵活性不如 ComfyUI |
| 云端 API only | 零 GPU 运维 | 成本、延迟、作品集可控性差 |

---

### 3.4 横切关注点

| 主题 | 阶段一 | 阶段二 |
|------|--------|--------|
| 存储 | 本地 `data/uploads/`、`data/outputs/` | S3 / Cloudflare R2 |
| 认证 | 无 | JWT / Session |
| CORS | 全开（开发） | 域名白名单 |
| 日志 | 结构化 JSON 日志到 `data/logs/` | 集中式 observability |
| 部署 | **localhost 录屏 demo**（已确认，无需 tldraw license） | Docker Compose / 云 GPU |
| 测试 | pytest（后端 API）+ Playwright（关键交互，可选） | 扩展 E2E |

---

## 4. 参考开源项目优先级

| 优先级 | 项目 | 学习重点 | 备注 |
|--------|------|----------|------|
| P0 | [tldraw/tldraw](https://github.com/tldraw/tldraw) | 坐标系、Store、自定义 Shape/Tool | 核心依赖 |
| P0 | [tldraw/image-pipeline-template](https://github.com/tldraw/image-pipeline-template) | 画布 + AI 节点管线 + Provider 抽象 | 官方 MIT starter |
| P0 | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) | API 提交、WebSocket 进度 | 执行层引擎 |
| P1 | [tldraw Agent Starter Kit](https://tldraw.dev/starter-kits/agent) | 画布上下文 → LLM → 操作画布 | Agent 交互范式 |
| P1 | [lvipcode/gpt-image-canvas](https://github.com/lvipcode/gpt-image-canvas) | tldraw + 本地 API + 生成历史 | 轻量全栈参考 |
| P2 | [datawhalechina/easy-vibe](https://github.com/datawhalechina/easy-vibe) | Lovart 产品工作流、资产 Agent 设计 | 教程，非代码库 |
| P2 | Kopia AI Canvas | Inpainting 交互 | 维护状态待验证，作补充 |

---

## 5. 阶段一 MVP 交付边界（Scope）

### 必须交付（Must Have）

- [ ] 可缩放/平移的无限画布，支持拖入图片
- [ ] 图片局部刷选 + Mask 导出
- [ ] 侧边聊天框输入自然语言指令
- [ ] 后端 LLM 输出结构化 `IntentPlan`
- [ ] 至少 **inpaint** 与 **txt2img** 两条 ComfyUI 工作流跑通
- [ ] WebSocket 实时进度 + 生成图自动贴到画布

### 明确不做（阶段一 Out of Scope）

- 多人协同编辑
- Lovart 级 30+ 模型自动路由
- 视频生成、Brand Kit、PSD/SVG 导出
- 性能优化、安全加固、计费系统

---

## 6. 推荐目录与模块划分

```
frontend/
  src/
    app/                 # Next.js 路由
    canvas/              # tldraw 封装、自定义 Tool、Mask 层
    agent-panel/         # 聊天与任务状态 UI
    lib/ws.ts            # WebSocket 客户端

backend/
  app/
    main.py              # FastAPI 入口
    api/
      agent.py           # /agent/plan
      generate.py        # /generate/*
      ws.py              # WebSocket 路由
    agent/
      router.py          # Intent 识别
      schemas.py         # IntentPlan Pydantic models
      tools.py           # 工具注册表
    pipeline/
      comfyui_client.py  # ComfyUI API 封装
      workflows/         # workflow_api.json 模板
    storage/
      local.py           # 文件读写
  tests/                 # 镜像 app/ 结构
```

---

## 7. 风险登记

| 风险 | 影响 | 缓解 |
|------|------|------|
| 8GB 显存 OOM | ComfyUI / Ollama 争抢 GPU | SD1.5 + lowvram；串行调度；Ollama 可选 CPU |
| GPU 环境搭建复杂 | 阻塞图像管线 | 见附录 A ComfyUI 安装指引 |
| tldraw 生产许可 | 公网 demo 受限 | 已确认仅本地录屏，无影响 |
| ComfyUI 工作流调试耗时 | 延期 | 先用单一 inpaint 工作流；Diffusers 作 fallback |
| Agent 意图识别不准 | demo 体验差 | 阶段一允许用户手动选择 intent 类型作为 override |
| Mask 坐标精度 | 重绘错位 | 单元测试覆盖 page→pixel 变换；可视化 debug overlay |

---

## 8. 决策记录

### 已确认

| 决策项 | 结论 | 日期 |
|--------|------|------|
| 项目名称 | InfDrawing | — |
| 目标 | 作品集 demo | — |
| 阶段分离 | 先原型后部署 | — |
| 技术栈 | Python 3.11 + 前后端分离 + 三层架构 | — |
| **GPU** | 本机 **~8GB** 显存；未来迁移大服务器或大显存电脑 | 2025-06-08 |
| **LLM** | **Ollama 本地**，模型 Qwen2.5-7B-Instruct | 2025-06-08 |
| **Demo 形态** | **仅 localhost 录屏**，不公网部署 | 2025-06-08 |
| **UI 风格** | **Lovart 暗色专业风**（深灰底、高对比、克制 accent 色） | 2025-06-08 |
| **阶段一 Intent** | **txt2img + inpaint**；outpaint 不做；img2img 视进度 | 2025-06-08 |
| **生图模型** | 阶段一 **SD 1.5**（非 SDXL）；阶段二升级 SDXL | 2025-06-08 |

### UI 暗色主题参考 token（实现时用）

```
background:     #0D0D0F ~ #141418
surface/panel:  #1A1A1F ~ #222228
border:         #2A2A32
text-primary:   #E8E8ED
text-muted:     #8B8B96
accent:         #6C5CE7 或 #00D2AA（择一，与 Lovart 紫/青类似）
canvas-bg:      #18181C（略亮于页面底，区分画布区）
```

---

## 9. 附录 A — 本机环境安装指引

> **完整分步命令、排错与验收清单**见 [`docs/environment_setup.md`](../docs/environment_setup.md)（2025-06-08 实测整理）。

要点摘要：

- **Ollama**：`OLLAMA_MODELS` 指向 D 盘 → `ollama pull qwen2.5:7b-instruct` → API `http://localhost:11434/v1`
- **ComfyUI**：Conda 环境 `comfyui`（Python 3.11）→ PyTorch cu124 → SD 1.5 模型 → `python main.py --lowvram --port 8188`
- **8GB 显存**：SD 1.5 + 512×512；Ollama 与 ComfyUI 串行使用 GPU
- **启动顺序**：Ollama → ComfyUI →（后续）backend → frontend → 录屏

---

## 10. 下一步行动

1. ~~用户确认待确认事项~~ ✅ 已完成
2. 创建 `.planning/20250608_phase1_scaffold.md` 脚手架实施规划
3. 用户按附录 A 安装 Ollama + ComfyUI（可在脚手架阶段并行）
4. 初始化 `frontend/` + `backend/`
5. 打通最小链路：上传图 → 刷 Mask → inpaint → 回贴画布

---

**文档状态**：**Approved**（2025-06-08）
