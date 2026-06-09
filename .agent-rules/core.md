# 项目核心规则

## 项目定位

InfDrawing 是一个类似 Lovart AI 的 AI 创意画布产品（工程型项目）。前端在 Web 端提供带有缩放、拖拽、图层管理和节点渲染的无限画布；后端负责意图识别、大模型推理，以及图像处理管线与多模态能力。核心目标是交付一个可展示的作品集 demo。

**项目名称**：InfDrawing

**主要贡献 / 目标**：

| # | 方向 | 关键词 |
|---|------|--------|
| C1 | 交互式 AI 画布 | canvas, layers, nodes, multimodal |

目标：一个可展示的作品集 demo

## 开发阶段分离（如适用）

**阶段一 — 原型阶段**：尽量利用已有公开库搭建前后端框架，实现前端的无限画布，基本交互（缩放、拖拽、裁剪等），可绘制内容，上传图片，圈选区域等功能。
此阶段**不考虑** 性能优化、安全问题 约束。

**阶段二 — 部署阶段**：主要考虑如何在云服务器中实现流畅交互，重视反应速度和视觉美观度。
仅在阶段一完成后启动。

## Python 环境

**始终使用项目虚拟环境 `.venv/`（Python 3.11）**，禁止使用系统 Python。

所有 `python`、`pytest`、`pip` 命令必须使用 `.venv/bin/` 前缀，或在已激活虚拟环境的 shell 中执行：

```bash
source .venv/bin/activate   # 激活
.venv/bin/python ...        # 直接调用（推荐，确保隔离）
```

> 虚拟环境建议放在 `backend/.venv/`；Windows 用户将 `.venv/bin/` 替换为 `.venv\Scripts\`。

## 目录规范

<!-- 前后端分离结构，保持与真实目录一致 -->

```
frontend/        # Web 前端（无限画布、图层管理、节点渲染、交互）
backend/         # Python 后端（意图识别、LLM 推理、图像管线、多模态）
  app/           # 后端应用源码
  tests/         # 后端测试，镜像 app/ 结构
scripts/         # 构建、部署、工具脚本
data/            # 上传文件、静态资源（大二进制不提交 Git）
.planning/       # 所有规划文件（按任务命名）
.cursor/         # IDE 与 Agent 会话状态（memory/、task_plan.md 等）
docs/            # 文档
```

- 禁止在仓库根目录创建散落源码文件；Python 代码放在 `backend/`，前端代码放在 `frontend/`
- 大二进制文件（模型权重、原始图片、构建产物）不提交 Git
- 上游依赖通过包管理引入，不直接复制源码

## Cursor Agent 记忆存储规范

项目的持久化记忆保存在仓库内，便于跨会话共享上下文：

- **记忆根目录**：`.cursor/memory/`
- **索引文件**：`.cursor/memory/MEMORY.md`（仅包含指向各记忆文件的链接，不写记忆内容）
- **记忆文件命名**：`{type}_{topic}.md`，例如 `feedback_planning_location.md`
- **禁止**将项目特定约束仅写入 Cursor 全局 Memories；可复用的项目级记忆必须保存在本目录

每个记忆文件使用如下 frontmatter 格式：

```markdown
---
name: 记忆名称
description: 一句话描述（用于判断未来会话的相关性）
type: user | feedback | project | reference
---

内容
```
