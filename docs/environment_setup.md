# InfDrawing 本地开发环境部署指南

> 适用平台：**Windows 10/11**  
> 目标：在本地搭建 InfDrawing 阶段一所需的基础组件（Ollama + ComfyUI）  
> 最后验证日期：2026-07-06  
> 验证硬件：NVIDIA GeForce RTX 4060 Laptop GPU（8GB 显存）

本文档整理自项目实际安装过程，供团队成员从零部署环境时参考。

---

## 目录

1. [环境总览](#1-环境总览)
2. [前置要求](#2-前置要求)
3. [磁盘规划（推荐 D 盘）](#3-磁盘规划推荐-d-盘)
4. [Step 1：安装 Ollama（Agent 层）](#4-step-1安装-ollamaagent-层)
5. [Step 2：安装 ComfyUI（图像层）](#5-step-2安装-comfyui图像层)
6. [Step 3：ComfyUI 首次使用](#6-step-3comfyui-首次使用)
7. [日常启动顺序](#7-日常启动顺序)
8. [8GB 显存注意事项](#8-8gb-显存注意事项)
9. [常见问题排查](#9-常见问题排查)
10. [验收清单](#10-验收清单)

---

## 1. 环境总览

InfDrawing 阶段一依赖两个本地服务：

| 组件 | 作用 | 默认地址 | 环境管理方式 |
|------|------|----------|--------------|
| **Ollama** | 本地 LLM，负责意图识别与 Prompt 改写 | `http://localhost:11434` | Ollama 安装包（独立） |
| **ComfyUI** | 本地生图引擎（txt2img / inpaint） | `http://127.0.0.1:8188` | **Conda** 环境 `comfyui` |

后续项目代码（FastAPI 后端、Next.js 前端）将使用独立的 `infdrawing` Conda 环境，**不要与 ComfyUI 混用**。

---

## 2. 前置要求

| 软件 | 版本建议 | 用途 | 下载 |
|------|----------|------|------|
| Windows | 10/11 | 操作系统 | — |
| NVIDIA 驱动 | 最新稳定版 | GPU 推理 | [NVIDIA Driver](https://www.nvidia.com/drivers) |
| Git | 最新 | 克隆 ComfyUI | [Git for Windows](https://git-scm.com/download/win) |
| Conda | Miniconda / Anaconda | Python 环境管理 | [Miniconda](https://docs.conda.io/en/latest/miniconda.html) |
| Ollama | 0.30+ | 本地 LLM | [Ollama](https://ollama.com/download) |

阶段一**暂不需要** Node.js（前端脚手架阶段再装）。

---

## 3. 磁盘规划（推荐 D 盘）

模型体积大，建议将数据集中放在 D 盘（路径可按机器调整）：

| 内容 | 推荐路径 | 预估体积 |
|------|----------|----------|
| Ollama 模型 | `D:\OllamaModels` | ~5 GB（Qwen 7B） |
| ComfyUI 程序 | `D:\ComfyUI` | ~2 GB（含依赖） |
| SD 1.5 模型 | `D:\ComfyUI\models\checkpoints\` | ~8 GB（两个模型） |
| 生成图片输出 | `D:\ComfyUI\output\` | 视使用量增长 |

---

## 4. Step 1：安装 Ollama（Agent 层）

### 4.1 下载安装

1. 访问 https://ollama.com/download ，下载 Windows 安装包
2. 按向导完成安装
3. 启动后可见 Ollama 桌面界面（**Launch** 页签为 Agent 启动器，本项目不使用，可忽略）

### 4.2 将模型存储路径改到 D 盘

1. 打开 **系统属性 → 环境变量 → 用户变量 → 新建**
2. 设置：

```
变量名：OLLAMA_MODELS
变量值：D:\OllamaModels
```

3. **完全退出** Ollama（系统托盘右键 → Quit），再重新启动
4. 打开**新的** PowerShell 窗口验证：

```powershell
echo $env:OLLAMA_MODELS
# 期望输出：D:\OllamaModels
```

> 设置环境变量后必须重启 Ollama 进程，否则仍可能写入默认 C 盘路径。

### 4.3 拉取项目用模型

```powershell
ollama pull qwen2.5:7b-instruct
```

模型约 **4.7 GB**，下载时间取决于网络。完成后确认：

```powershell
ollama list
```

期望输出包含：

```
NAME                    SIZE
qwen2.5:7b-instruct     4.7 GB
```

### 4.4 对话测试

```powershell
ollama run qwen2.5:7b-instruct "你好，请用一句话介绍你自己"
```

能正常中文回复即通过。退出对话：输入 `/bye` 或按 `Ctrl+D`。

### 4.5 API 测试

> **注意**：PowerShell 中 `curl` 是 `Invoke-WebRequest` 的别名，会弹出安全警告。请使用 `curl.exe` 或 `Invoke-RestMethod`。

**Ollama 原生 API：**

```powershell
curl.exe -s http://localhost:11434/api/tags
```

**OpenAI 兼容 API（后端将使用此接口）：**

```powershell
curl.exe -s http://localhost:11434/v1/models
```

**对话补全测试（PowerShell 写法）：**

```powershell
$body = @{
  model = "qwen2.5:7b-instruct"
  messages = @(@{ role = "user"; content = "回复OK两个字母" })
  max_tokens = 10
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:11434/v1/chat/completions" `
  -Method Post -ContentType "application/json" -Body $body
```

后端接入参数：

```
Base URL : http://localhost:11434/v1
Model    : qwen2.5:7b-instruct
```

---

## 5. Step 2：安装 ComfyUI（图像层）

### 5.1 克隆仓库

```powershell
cd D:\
git clone https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
```

### 5.2 创建 Conda 环境

```powershell
conda create -n comfyui python=3.11 -y
conda activate comfyui
python --version
# 期望：Python 3.11.x
```

### 5.3 安装 PyTorch（CUDA 12.4）

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

安装结束时若出现**红色依赖冲突警告**（涉及 jupyterlab、matplotlib 等），通常**不影响 ComfyUI**。以 CUDA 验证为准：

```powershell
python -c "import torch; print('torch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
```

期望输出示例：

```
torch: 2.6.0+cu124
CUDA: True
GPU: NVIDIA GeForce RTX 4060 Laptop GPU
```

### 5.4 安装 ComfyUI 依赖

```powershell
cd D:\ComfyUI
conda activate comfyui
pip install -r requirements.txt
```

### 5.5 下载 SD 1.5 模型（8GB 显存方案）

创建目录：

```powershell
mkdir D:\ComfyUI\models\checkpoints -Force
```

需要下载两个文件到 `D:\ComfyUI\models\checkpoints\`：

| 文件名 | 用途 | 大小约 | HuggingFace |
|--------|------|--------|-------------|
| `v1-5-pruned-emaonly.safetensors` | 文生图 txt2img | ~4 GB | [stable-diffusion-v1-5](https://huggingface.co/runwayml/stable-diffusion-v1-5/tree/main) |
| `sd-v1-5-inpainting.ckpt` | 局部重绘 inpaint | ~4 GB | [stable-diffusion-inpainting](https://huggingface.co/runwayml/stable-diffusion-inpainting/tree/main) |

**方式 A — 浏览器手动下载**（推荐，最稳定）

从 HuggingFace 页面下载后，放入 `checkpoints` 目录。

**方式 B — 命令行下载**

```powershell
conda activate comfyui
pip install huggingface_hub

huggingface-cli download runwayml/stable-diffusion-v1-5 v1-5-pruned-emaonly.safetensors `
  --local-dir D:\ComfyUI\models\checkpoints

huggingface-cli download runwayml/stable-diffusion-inpainting sd-v1-5-inpainting.ckpt `
  --local-dir D:\ComfyUI\models\checkpoints
```

验证：

```powershell
Get-ChildItem D:\ComfyUI\models\checkpoints\*.safetensors, D:\ComfyUI\models\checkpoints\*.ckpt
```

### 5.6 启动 ComfyUI（低显存模式）

```powershell
cd D:\ComfyUI
conda activate comfyui
python main.py --lowvram --port 8188
```

浏览器访问：**http://127.0.0.1:8188**

看到节点画布界面即表示启动成功。终端不要关闭，关闭即停止服务。

---

## 6. Step 3：ComfyUI 首次使用

### 6.1 界面基本操作

| 操作 | 方法 |
|------|------|
| 平移画布 | 空格 + 鼠标左键拖动，或鼠标中键拖动 |
| 缩放 | 滚轮 |
| 添加节点 | 空白处双击，搜索节点名 |
| 运行工作流 | 右上角 **▶ Run**，或 `Ctrl + Enter` |
| 查看历史输出 | 左侧文件夹图标；文件在 `D:\ComfyUI\output\` |

### 6.2 加载入门工作流（文生图）

项目提供了一个 SD 1.5 基础工作流（若从本仓库克隆，路径可能在 ComfyUI 安装目录）：

```
D:\ComfyUI\workflows\sd15_txt2img_basic.json
```

加载方式（任选其一）：

1. 将 JSON 文件**拖入**浏览器中的 ComfyUI 画布
2. 画布右键 → **Load** / **Open** → 选择该文件

### 6.3 生成第一张图

1. **Load Checkpoint** 节点：选择 `v1-5-pruned-emaonly.safetensors`
2. **正向 Prompt**（上方 CLIP Text Encode）：输入英文描述，例如  
   `a cute cat sitting on a windowsill, soft lighting, digital art`
3. **Empty Latent Image**：保持 `512 × 512`（8GB 显存不要用更高分辨率）
4. 点击 **▶ Run**
5. 在 **Save Image** 节点或 `D:\ComfyUI\output\` 查看结果

工作流节点关系：

```
Load Checkpoint → KSampler ← 正向/负向 Prompt
                      ↑
               Empty Latent (512×512)
KSampler → VAE Decode → Save Image
```

### 6.4 局部重绘（inpaint）

**工作流文件**（仓库内模板，复制到 ComfyUI 使用）：

```
scripts/comfyui/workflows/sd15_inpaint_basic.json  →  D:\ComfyUI\workflows\
```

**测试图**（可用脚本一键生成）：

```powershell
D:\Anaconda3\envs\comfyui\python.exe D:\Desktop\Fan_Files\Codes\infDrawing\scripts\comfyui\make_test_images.py
```

生成文件：

| 文件 | 路径 | 说明 |
|------|------|------|
| `test.png` | `D:\ComfyUI\input\` | 512×512 原图 |
| `test_mask.png` | `D:\ComfyUI\input\` | 同尺寸 mask，**白=重绘区** |

**验证步骤**：

1. 拖入 `sd15_inpaint_basic.json` 到 ComfyUI 画布
2. **Load Checkpoint** 选择 `sd-v1-5-inpainting.ckpt`（不是 txt2img 用的 safetensors）
3. 两个 **Load Image** 节点确认指向 `test.png` / `test_mask.png`
4. 修改正向 prompt（例：`a bright red apple, highly detailed`）→ **▶ Run**
5. 在 output 确认 mask 区域已重绘

**API 工作流**（后端集成用，已验证 `/prompt` 可提交）：

```
backend/app/pipeline/workflows/sd15_inpaint_api.json
backend/app/pipeline/workflows/sd15_txt2img_api.json
```

节点关系：

```
Load Image (原图) ──┐
Load Image (mask) → ImageToMask ──┐
Load Checkpoint (inpaint ckpt) ───┼→ VAE Encode (for Inpainting) → KSampler → VAE Decode → Save Image
正向/负向 Prompt ─────────────────┘
```

---

## 7. 日常启动顺序

```text
1. Ollama（安装后通常后台自启，无需手动操作）
2. 仓库根目录执行 .\scripts\dev.ps1（推荐，一键启动 ComfyUI + 后端 + 前端）
   或按下方命令分别手动启动
3. 本地录屏演示
```

### 一键启动（推荐）

```powershell
cd D:\Desktop\Fan_Files\Codes\infDrawing
.\scripts\dev.ps1          # 启动并打开浏览器
.\scripts\dev.ps1 status   # 健康检查
.\scripts\dev.ps1 stop       # 停止脚本记录的进程
```

详见 [`README.md`](../README.md) 中的环境变量说明（`INFD_COMFYUI_DIR` 等）。

**InfDrawing 后端（手动）：**

```powershell
cd D:\Desktop\Fan_Files\Codes\infDrawing\backend
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> Windows 上 `uvicorn app.main:app --reload` 可能无输出即退出，请优先使用 `python -m uvicorn`。

**InfDrawing 前端：**

```powershell
cd D:\Desktop\Fan_Files\Codes\infDrawing\frontend
npm run dev
```

浏览器访问 `http://127.0.0.1:3000`；API 文档 `http://127.0.0.1:8000/docs`

**启动后快速自检：**

```powershell
curl.exe -s http://127.0.0.1:8000/health          # {"status":"ok"}
curl.exe -s http://127.0.0.1:8188/ -o NUL -w "%{http_code}\n"   # 200
curl.exe -s http://127.0.0.1:3000/ -o NUL -w "%{http_code}\n"   # 200
```

> 建议用 **Chrome / Edge** 打开 `http://127.0.0.1:3000`。Cursor 内置浏览器偶发 HMR WebSocket 报错，不影响功能，但系统浏览器更稳。

**ComfyUI 启动命令（每次）：**

```powershell
cd D:\ComfyUI
conda activate comfyui
python main.py --lowvram --port 8188
```

**Ollama 常用命令：**

```powershell
ollama list                              # 查看已安装模型
ollama run qwen2.5:7b-instruct "..."     # 交互测试
curl.exe -s http://localhost:11434/api/tags   # API 健康检查
```

---

## 7.1 InfDrawing 全链路联调（已验证）

> 2025-06-08 起持续验证：tldraw 画布 + FastAPI + ComfyUI **txt2img / inpaint / 拆解 / 文字编辑** 均已打通。  
> 2026-07-06 起推荐通过 `.\scripts\dev.ps1` 启动全套服务。

### 前置：四服务同时运行

Ollama（通常自启）→ 执行 `.\scripts\dev.ps1`，或按 §7 手动启动 ComfyUI → backend → frontend。

### 测试 A — txt2img（文生图）

1. 浏览器打开 `http://127.0.0.1:3000`
2. 等待左侧 tldraw 画布加载完成（首次约 10–30 秒）
3. 右侧模式选 **生图**
4. 输入 prompt，例如：`a cute cat on a windowsill, soft lighting`
5. 点击 **发送** → 对话流显示进度 → 生成图回贴画布

也可在画布空白处 **右键 → AI 生图**。

### 测试 B — inpaint（局部重绘）

1. 在画布上放置或生成一张图片并**选中**
2. 右侧模式选 **局部重绘** → 点击 **刷选 Mask（画布）**
3. 在 Mask 编辑器中涂抹重绘区域 → 完成
4. 输入 prompt，例如：`a bright red apple, highly detailed`
5. 点击 **发送** → 约 20–40 秒 → 结果回贴画布

### 测试 C — 元素拆解（可选）

1. 选中画布图片 → 侧栏 **元素拆解** → 发送（prompt 可留空使用默认）
2. 完成后应回贴 background + foreground 两个图层

### 测试 D — 文字编辑（可选）

1. 选中含文字的图片 → 侧栏 **文字编辑**
2. OCR 自动检测文字块 → 选择要替换的块 → 输入新文字 → 发送

### 备选：Swagger 直接调 API

打开 `http://127.0.0.1:8000/docs`：

| 端点 | 用途 |
|------|------|
| `POST /api/v1/agent/plan` | 意图规划（Ollama） |
| `POST /api/v1/generate/txt2img` | 文生图 |
| `POST /api/v1/generate/inpaint` | 局部重绘（multipart：image + mask + prompt） |
| `POST /api/v1/generate/decompose` | 元素拆解 |
| `POST /api/v1/generate/text-edit` | 文字编辑 |
| `GET /api/v1/system/capabilities` | 环境能力探测 |

### 阶段一剩余工作

| 已完成 | 待做 |
|--------|------|
| 四模式侧栏 + 右键生图 + Mask 刷选 + 回贴画布 | 录屏 demo 脚本与成片 |
| WebSocket 进度 + 断线重连 | Stage 7 自动 intent（可选） |
| `dev.ps1` 一键启动 + README | 阶段二云部署 / 高质量模型（P2） |

---

| 规则 | 说明 |
|------|------|
| 生图模型用 **SD 1.5**，不用 SDXL | SDXL 单模型即可占满 8GB |
| 分辨率固定 **512×512** | 更高分辨率易 OOM |
| ComfyUI 必须加 `--lowvram` | 已在启动命令中 |
| Ollama 与 ComfyUI **避免同时满载 GPU** | 推荐串行：先 LLM 规划，再生图 |
| OOM 时让 Ollama 走 CPU | 见下方命令 |

**OOM 时临时让 Ollama 使用 CPU：**

```powershell
$env:OLLAMA_NUM_GPU = "0"
# 然后重启 Ollama 应用
```

Agent 响应会变慢，但生图更稳定。

---

## 9. 常见问题排查

### Q1：`curl` 弹出 PowerShell 安全警告

**原因**：`curl` 是 `Invoke-WebRequest` 别名。  
**解决**：使用 `curl.exe` 或 `Invoke-RestMethod`。

### Q2：PyTorch 安装后出现红色依赖冲突

**原因**：Conda 环境中其他包（Jupyter 等）缺依赖。  
**判断**：运行 CUDA 验证命令，若 `CUDA: True` 则可继续。  
**ComfyUI 不依赖 Jupyter**，可暂时忽略。

### Q3：ComfyUI 报错 OOM / out of memory

1. 确认启动参数含 `--lowvram`
2. 分辨率改为 512×512
3. 关闭 Ollama 对话或设 `OLLAMA_NUM_GPU=0`
4. 重启 ComfyUI

### Q4：`OLLAMA_MODELS` 设置后模型仍在 C 盘

1. 确认变量名为 `OLLAMA_MODELS`（全大写）
2. 完全退出 Ollama 后重新启动
3. 在新 PowerShell 窗口中执行 `echo $env:OLLAMA_MODELS`

### Q5：ComfyUI 下拉框看不到模型

确认文件存在且扩展名正确：

```powershell
Get-ChildItem D:\ComfyUI\models\checkpoints\
```

### Q6：想重建干净的 ComfyUI 环境

```powershell
conda deactivate
conda remove -n comfyui --all -y
conda create -n comfyui python=3.11 -y
conda activate comfyui
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r D:\ComfyUI\requirements.txt
```

### Q7：后端 `uvicorn` 报错 `[WinError 10013]` 或端口占用

**原因**：`8000` 端口已被其他进程占用（常见：上次未关闭的 uvicorn，或 Hyper-V 保留端口）。

**排查**：

```powershell
netstat -ano | findstr ":8000"
```

若看到 `LISTENING` 和 PID，结束旧进程：

```powershell
Stop-Process -Id <PID> -Force
```

**验证后端是否已在运行**（无需重复启动）：

```powershell
curl.exe -s http://127.0.0.1:8000/health
# 若返回 {"status":"ok"}，说明后端正常，直接启动前端即可
```

**仍无法绑定 8000 时**，可换端口：

```powershell
uvicorn app.main:app --reload --port 8001
```

并在 `frontend/.env.local` 中设置：

```
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001
```

### Q8：前端 `npm run dev` 成功但浏览器白屏 / 一直「画布加载中」

**原因**：tldraw 体积大，且不能在 SSR 阶段初始化；dev 模式首次加载较慢。

**解决**：

1. **Ctrl+C** 停止 dev 后重新 `npm run dev`
2. 用 **Chrome / Edge** 打开 `http://127.0.0.1:3000`（避免 Cursor 内置浏览器）
3. 首次等待 **10–30 秒**；若仍失败，F12 → Console 查看报错
4. 项目已在 `InfDrawingCanvas.tsx` 用客户端 `useEffect` 按需加载 tldraw

**可忽略**：Console 中 `webpack-hmr` WebSocket 失败（dev 热更新），一般不影响生图功能。

---

## 10. 验收清单

完成以下全部项，即表示阶段一基础环境就绪：

### Ollama

- [ ] `ollama --version` 有版本号输出
- [ ] `echo $env:OLLAMA_MODELS` 指向预期目录（如 `D:\OllamaModels`）
- [ ] `ollama list` 包含 `qwen2.5:7b-instruct`
- [ ] `curl.exe -s http://localhost:11434/v1/models` 返回 JSON
- [ ] 对话测试可正常中文回复

### ComfyUI

- [ ] `conda activate comfyui` 后 `python --version` 为 3.11
- [ ] PyTorch CUDA 验证：`CUDA: True`，GPU 名称正确
- [ ] `models/checkpoints/` 下有两个 SD 1.5 模型文件
- [ ] `python main.py --lowvram --port 8188` 可启动
- [ ] 浏览器可访问 `http://127.0.0.1:8188`
- [ ] 加载 `sd15_txt2img_basic.json` 后可成功出图
- [ ] 加载 `sd15_inpaint_basic.json` + 测试图后可 inpaint 出图
- [ ] 输出目录 `D:\ComfyUI\output\` 有生成图片

### InfDrawing 全栈（frontend + backend + ComfyUI）

- [ ] `backend/.venv` 已创建，`pip install -r requirements.txt` 完成
- [ ] `python -m uvicorn app.main:app --port 8000` 启动，`/health` 返回 ok
- [ ] `frontend/` 下 `npm install` + `npm run dev` 可访问 `http://127.0.0.1:3000`
- [ ] `.\scripts\dev.ps1 status` 四项服务均为 OK（或手动等价验证）
- [ ] tldraw 画布可绘制、缩放、平移
- [ ] 侧栏 **生图** 发送后结果回贴画布
- [ ] 侧栏 **局部重绘**：选中图片 → 刷选 Mask → 发送后结果回贴
- [ ] （可选）**元素拆解** / **文字编辑** 流程可跑通
- [ ] ComfyUI 与 backend 串行运行时 8GB 显存无 OOM

---

## 附录：已验证版本快照

| 组件 | 验证版本 |
|------|----------|
| Ollama | 0.30.6 |
| Qwen 模型 | qwen2.5:7b-instruct（Q4_K_M，4.7 GB） |
| Python（comfyui 环境） | 3.11 |
| PyTorch | 2.6.0+cu124 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU |
| Node.js | v22.16.0 |
| Next.js | 16.2.7 |
| @tldraw/tldraw | 5.1.0 |
| FastAPI backend | `backend/.venv`，port 8000 |

---

## 相关文档

- 项目进度追踪：[`进度.md`](../进度.md)
- 技术选型总览：`.planning/20250608_tech_stack_selection.md`
- 项目 Agent 规则：`AGENTS.md`
- 项目主页：[`README.md`](../README.md)

---

*如有环境差异（Linux、macOS、更大显存），请以技术选型文档中的分阶段策略为准，并在此文档基础上调整路径与启动参数。*
