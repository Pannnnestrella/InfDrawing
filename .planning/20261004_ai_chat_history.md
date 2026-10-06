## 任务：AI 多会话历史

**背景**：侧栏消息仅内存态，刷新丢失；用户需要回看操作，并按「每次请求」拆成可切换会话。
**影响范围**：`frontend/src/agent-panel/`（消息状态、列表 UI、会话切换）、可选小工具模块 `chat-history.ts`
**前置条件**：现有 ChatPanel / MessageList / useChatMessages

### 已拍板决策

| 项 | 决定 |
|---|---|
| 会话粒度 | **每次用户发起的一次 AI 请求 = 一个会话**（含该次的状态/结果图/错误） |
| 切换 | 侧栏支持多会话列表切换；当前会话继续追加消息 |
| 存储 | `localStorage`，刷新可恢复 |
| 图片 | 持久化前 `blob:` → `data:` |
| 容量 | 最多保留约 30 个会话；每会话消息上限；超限删最旧会话 |
| 不做 | 服务端同步；把历史喂回 LLM 多轮上下文（可后续） |

### Stage 1: 数据模型与持久化
- **目标**：`ChatSession { id, title, mode, createdAt, updatedAt, messages[] }`；localStorage 读写
- **成功标准**：刷新后会话列表与消息可恢复
- **状态**：Complete

### Stage 2: 会话生命周期
- **目标**：用户点击发送时新建会话；该次请求的 user/status/image/error 都写入该会话
- **成功标准**：连续两次请求产生两条可切换会话
- **状态**：Complete

### Stage 3: UI
- **目标**：侧栏顶部/列表展示会话（标题=用户首句摘要或模式+时间）；点击切换；「新对话」与「清空全部」
- **成功标准**：可切换查看历史结果图与提示词
- **状态**：Complete

**待确认事项**：无（已批准并实施）

## 完成记录

- **完成时间**：2026-10-04
- **实际结果**：
  - 新增 `frontend/src/lib/chat-history.ts`（会话模型、localStorage、blob→data）
  - `useChatMessages` 改为多会话 + 同步 ref，发送前 `beginSession`
  - `SessionSwitcher` 接入 `ChatPanel`；支持切换 / 新对话 / 清空
  - 单测：`chat-history.test.ts`
- **偏差说明**：容量上限仅按会话数（30）；未单独做「每会话消息条数」硬上限
