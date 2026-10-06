---
name: 开发端口与报告对照图
description: 用户从 :3000 打开 Studio；FastAPI 在 :8000。报告需要并排对照图。
type: user
---

用户日常打开的是前端 `http://127.0.0.1:3000`（Next.js）。后端 uvicorn 仍是 `http://127.0.0.1:8000`，由 `next.config.ts` 代理。对用户说「打开页面」时用 3000，不要把 8000 说成产品地址。

写报告需要并排对照图（原图 / mask / 各模型结果），同类实验优先产出 `compare.png` 这类拼图。
