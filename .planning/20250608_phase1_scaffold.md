## 任务：阶段一脚手架实施（InfDrawing MVP）

**背景**：技术选型（Approved）与本地环境（Ollama + ComfyUI txt2img）已就绪。下一步需建立 `frontend/`、`backend/` 代码骨架，并打通「上传图 → 刷 Mask → inpaint → 回贴画布」最小链路，交付 localhost 录屏 demo。

**影响范围**：

| 路径 | 操作 |
|------|------|
| `frontend/` | 新建（Next.js 15 + tldraw + 暗色 UI） |
| `backend/` | 新建（FastAPI + Agent + ComfyUI client） |
| `backend/app/pipeline/workflows/` | ComfyUI API workflow 模板 |
| `scripts/comfyui/workflows/` | ComfyUI UI 可加载的工作流参考（复制到 `D:\ComfyUI\workflows\`） |
| `data/uploads/`、`data/outputs/`、`data/logs/` | 运行时目录（`.gitkeep`，大二进制不提交） |
| `docs/environment_setup.md` | 补充 inpaint 验证步骤（Stage 2 完成后） |
| `进度.md` | 各 Stage 完成后同步 |

**前置条件**：

- [x] [`.planning/20250608_tech_stack_selection.md`](20250608_tech_stack_selection.md) Approved
- [x] Ollama + `qwen2.5:7b-instruct` 可用
- [x] ComfyUI `--lowvram` + SD 1.5 txt2img 出图验证
- [ ] SD 1.5 inpaint 工作流 UI 验证 + API JSON 导出

**参考决策（不再讨论，直接执行）**：

- Demo 形态：localhost 录屏，无需 tldraw 生产 license
- Intent 范围：txt2img + inpaint；outpaint 不做
- 模型：SD 1.5，512×512，ComfyUI `--lowvram`
- UI：Lovart 暗色风（token 见技术选型 §8）
- GPU：Ollama 与 ComfyUI 串行，避免 OOM

---

## 目标架构

```text
┌─────────────────────────────────────────────────────────────┐
│  frontend/ (Next.js 15, port 3000)                          │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────┐  │
│  │ tldraw 画布   │  │ Mask Tool      │  │ Agent 侧边栏     │  │
│  │ 缩放/平移/贴图 │  │ page→pixel    │  │ 聊天 + 任务状态   │  │
│  └──────┬───────┘  └───────┬────────┘  └────────┬────────┘  │
│         │                  │                     │            │
│         └──────────────────┴─────────────────────┘            │
│                            │ REST + WebSocket                 │
└────────────────────────────┼──────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  backend/ (FastAPI, port 8000)                              │
│  POST /api/v1/agent/plan  →  IntentPlan (Ollama)            │
│  POST /api/v1/generate/*  →  提交 ComfyUI 任务               │
│  WS   /api/v1/ws          →  进度 / 结果推送                 │
└────────────────────────────┬────────────────────────────────┘
                             ▼
        Ollama :11434                    ComfyUI :8188
        qwen2.5:7b-instruct              SD 1.5 / inpaint ckpt
```

---

## 目录结构（阶段一最终态）

```text
frontend/
  src/
    app/
      layout.tsx              # 暗色主题根布局
      page.tsx                # 主画布页
      globals.css             # Tailwind + 暗色 token
    canvas/
      InfDrawingCanvas.tsx    # tldraw 封装
      MaskTool.tsx            # 刷涂 → 二值 Mask PNG
      types.ts
    agent-panel/
      ChatPanel.tsx           # 侧边聊天 + intent override
      TaskStatus.tsx          # WebSocket 进度条
    lib/
      api.ts                  # REST 客户端
      ws.ts                   # WebSocket 客户端
      theme.ts                # 暗色 token 常量

backend/
  .venv/                      # Python 3.11 虚拟环境
  app/
    main.py                   # FastAPI 入口、CORS
    config.py                 # 环境变量（Ollama/ComfyUI URL）
    api/
      agent.py                # POST /agent/plan
      generate.py             # POST /generate/txt2img | /inpaint
      ws.py                   # WebSocket 路由
    agent/
      router.py               # LLM 调用 + JSON 解析
      schemas.py              # IntentPlan Pydantic models
      tools.py                # target_tool 注册表
      prompts.py              # system prompt 模板
    pipeline/
      comfyui_client.py       # prompt 提交、history、WS 监听
      executor.py             # IntentPlan → workflow 参数注入 → 执行
      workflows/
        sd15_txt2img_api.json
        sd15_inpaint_api.json
    storage/
      local.py                # uploads/outputs 读写
  tests/
    test_agent_schemas.py
    test_comfyui_client.py    # mock ComfyUI
  pyproject.toml              # 或 requirements.txt
  README.md

scripts/
  comfyui/workflows/          # UI 工作流（拖入 ComfyUI 验证用）
    sd15_txt2img_basic.json   # 已有，同步副本
    sd15_inpaint_basic.json

data/
  uploads/   .gitkeep
  outputs/   .gitkeep
  logs/      .gitkeep
```

---

## 接口约定

### IntentPlan（`backend/app/agent/schemas.py`）

```python
class IntentType(str, Enum):
    TXT2IMG = "txt2img"
    INPAINT = "inpaint"
    # img2img 阶段一可选，暂不默认

class IntentPlan(BaseModel):
    intent: IntentType
    refined_prompt: str
    negative_prompt: str = "blurry, low quality, distorted, ugly"
    target_tool: str  # e.g. "comfyui_txt2img_v1" | "comfyui_inpaint_v1"
    params: dict = {}  # steps, seed, cfg, denoise 等
    confidence: float = 1.0
    reasoning: str | None = None  # 可选，demo 调试用
```

**阶段一 fallback**：前端提供 intent 下拉（txt2img / inpaint），用户可 override LLM 输出。

### Context Bundle（前端 → `POST /api/v1/agent/plan`）

```typescript
interface AgentPlanRequest {
  user_message: string
  intent_override?: 'txt2img' | 'inpaint'
  context?: {
    selected_shape_id?: string
    image_width?: number
    image_height?: number
    has_mask?: boolean
  }
}
```

Mask 与图片在 **generate** 阶段上传，不在 plan 阶段传大图（减轻 LLM 请求体）。

### Generate（`POST /api/v1/generate/inpaint`）

```text
multipart/form-data:
  image: File          # 原图 PNG/JPEG
  mask: File           # 二值 Mask PNG（白=重绘区）
  prompt: string
  negative_prompt?: string
  seed?: int
  steps?: int          # 默认 20
```

响应：`{ "task_id": "uuid" }`，结果经 WebSocket 推送。

### WebSocket（`/api/v1/ws?task_id={uuid}`）

```json
{ "type": "progress", "task_id": "...", "step": 3, "max_steps": 20, "node": "KSampler" }
{ "type": "complete", "task_id": "...", "image_url": "/api/v1/files/outputs/xxx.png" }
{ "type": "error", "task_id": "...", "message": "..." }
```

### ComfyUI 集成要点

1. UI 验证通过后，**Save (API Format)** 导出 JSON → 放入 `backend/app/pipeline/workflows/`
2. `comfyui_client.py` 动态替换节点 `inputs` 中的 prompt、seed、图片文件名
3. 上传图/Mask 先 `POST /upload/image` 到 ComfyUI，或使用 `input/` 目录 + `LoadImage` 节点文件名
4. 监听 `ws://127.0.0.1:8188/ws?clientId={uuid}`，完成后读 `/history/{prompt_id}`

**可变参数占位（workflow 内约定 node id，实现时写死在 executor）**：

| 工作流 | 节点类型 | 可变 widgets |
|--------|----------|--------------|
| txt2img | CLIPTextEncode ×2 | positive / negative prompt |
| txt2img | KSampler | seed, steps, cfg |
| inpaint | CLIPTextEncode ×2 | prompt |
| inpaint | KSampler | seed, steps, denoise |
| inpaint | LoadImage ×2 | image / mask 文件名 |

---

## Stage 分步实施

### Stage 1: 脚手架规划（本文件）

- **目标**：明确目录、接口、Stage 顺序与验收标准
- **成功标准**：用户批准本文档；`进度.md` M4 标记完成
- **状态**：✅ 已完成（2025-06-08，用户确认按计划执行）

---

### Stage 2: ComfyUI inpaint 验证 + API JSON

- **目标**：
  1. UI 跑通 SD 1.5 inpaint（`sd-v1-5-inpainting.ckpt`）
  2. 导出 `sd15_inpaint_api.json` 至 `backend/app/pipeline/workflows/`
  3. 仓库内保留 UI 参考工作流 `scripts/comfyui/workflows/sd15_inpaint_basic.json`
- **成功标准**：
  - [ ] ComfyUI 中 inpaint 出图成功（mask 区域可见变化）
  - [ ] API JSON 经 `curl` 或临时脚本提交 `/prompt` 可出图
  - [ ] `docs/environment_setup.md` §6 补充 inpaint 小节
- **操作步骤**：
  1. 复制 `scripts/comfyui/workflows/sd15_inpaint_basic.json` → `D:\ComfyUI\workflows\`
  2. 在 `D:\ComfyUI\input\` 放入测试图 `test.png` 与 mask `test_mask.png`（白区=重绘）
  3. ComfyUI 加载工作流 → 选 checkpoint `sd-v1-5-inpainting.ckpt` → Run
  4. 确认 output 后：**Save (API Format)** → 保存为 `sd15_inpaint_api.json`
  5. 同样处理 txt2img → `sd15_txt2img_api.json`（可与 Stage 6 并行）
- **状态**：✅ 已完成（2025-06-08，UI 出图 + API `/prompt` 验证通过）

---

### Stage 3: 开发环境补全

- **目标**：安装 Node.js 20 LTS；创建 `infdrawing` Conda 环境
- **成功标准**：
  - [x] `node -v` ≥ 20.x（v22.16.0）
  - [x] `backend/.venv` Python 3.11 + 依赖安装
  - [ ] Conda `infdrawing`（可选；当前用 `backend/.venv` 替代）
- **状态**：✅ 已完成（2025-06-08）

---

### Stage 4: backend 初始化

- **目标**：FastAPI 骨架 + Ollama client + ComfyUI client（可先 mock inpaint）
- **成功标准**：
  - [x] `uvicorn app.main:app --reload --port 8000` 启动
  - [x] `GET /health` 返回 ok
  - [x] `POST /api/v1/agent/plan` 返回合法 `IntentPlan` JSON
  - [x] `POST /api/v1/generate/txt2img` / `inpaint` 触发 ComfyUI
  - [x] WebSocket 收到 progress + complete
  - [x] pytest 覆盖 schemas
- **状态**：✅ 已完成（2025-06-08）

---

### Stage 5: frontend 初始化

- **目标**：Next.js + tldraw 暗色画布 + 侧边栏占位
- **成功标准**：
  - [x] `npm run dev` / `npm run build` 通过
  - [x] tldraw 无限画布集成
  - [x] 暗色 UI + 侧边 ChatPanel
  - [x] `lib/api.ts` + `lib/ws.ts` 桩代码
- **状态**：✅ 已完成（2025-06-08）

---

### Stage 6: 最小链路联调（inpaint 优先）

- **目标**：端到端 inpaint（Agent 可先用 intent override 跳过 LLM 不确定性）
- **成功标准**：
  - [ ] 画布上传图片 → Mask Tool 刷选 → 导出 mask PNG
  - [x] 聊天框 inpaint + 上传 test.png/mask → backend → ComfyUI（2025-06-08 实测通过）
  - [x] txt2img 聊天框 → backend → ComfyUI（2025-06-08 实测通过）
  - [x] WebSocket 进度 → 结果在侧边栏预览
  - [ ] 生成图自动贴到画布（原图旁偏移放置）
  - [x] 512×512 约束下 8GB 显存无 OOM
- **状态**：🟡 进行中（核心链路已通，Mask Tool + 回贴画布待做）

---

### Stage 7: txt2img + Agent 完善

- **目标**：补齐 txt2img 链路；LLM 自动识别 intent（仍保留 override）
- **成功标准**：
  - [ ] 纯文本「画一只猫」→ txt2img → 新 Shape 落位
  - [ ] `IntentPlan` 对 inpaint / txt2img 分类基本可用
  - [ ] Ollama 与 ComfyUI 串行调度（plan 完成后再 trigger generate）
- **状态**：Not Started

---

### Stage 8: MVP 收尾与录屏

- **目标**：M8 里程碑 — 可演示的 localhost 录屏
- **成功标准**：
  - [ ] 演示脚本：上传 → 刷 mask → 聊天 inpaint → 再 txt2img 一张
  - [ ] `进度.md` M5–M8 全部 ✅
  - [ ] README 补充启动命令（四进程顺序）
- **状态**：Not Started

---

## 启动顺序（联调期）

```text
1. ollama serve（通常已自启）
2. cd D:\ComfyUI && conda activate comfyui && python main.py --lowvram --port 8188
3. cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
4. cd frontend && npm run dev
5. 浏览器 http://localhost:3000 → 录屏
```

---

## 风险与缓解（阶段一执行层）

| 风险 | 缓解 |
|------|------|
| inpaint mask 错位 | Stage 6 加可视化 debug；单元测试 page→pixel |
| LLM JSON 解析失败 | pydantic validate + 重试一次 + intent override |
| ComfyUI API node id 变化 | workflow 版本号写在文件名；executor 集中映射 |
| 8GB OOM | 串行 GPU；steps=20；512 固定 |

---

## 待确认事项

- [x] 按本 Stage 顺序执行 — **用户已确认（2025-06-08）**
- [ ] Stage 2 测试图：使用仓库内示例图，还是用户自备？（默认：用户自备放入 `D:\ComfyUI\input\`）
- [ ] 前端布局：画布全屏 + 右侧固定面板，还是底部聊天条？（默认：**右侧固定 Agent 面板**，贴近 Lovart）

---

## 完成记录

| Stage | 完成日期 | 备注 |
|-------|----------|------|
| Stage 1 | 2025-06-08 | 本文档创建，用户批准执行 |
| Stage 2 | 2025-06-08 | inpaint UI + API `/prompt` 验证 |
| Stage 3 | 2025-06-08 | Node.js + backend/.venv |
| Stage 4 | 2025-06-08 | FastAPI 骨架 |
| Stage 5 | 2025-06-08 | Next.js + tldraw 暗色 UI |
| Stage 6 | 2025-06-08 | txt2img/inpaint UI 全链路联调通过（Mask Tool 待做） |
| Stage 7 | — | |
| Stage 8 | — | |

---

**文档状态**：**Approved**（2025-06-08，用户确认按计划逐步执行）
