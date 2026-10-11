## 任务：素材库自由文本改为「分词 + 子串 AND」

**背景**：当前 `item_matches_query` 把整段 `q` 当作一个 needle 做 `needle in search_blob`。多关键词必须连续出现才能命中。改为 jieba 分词后，对每个 token 做子串匹配，**任一命中即命中（OR）**。

**影响范围**：
- `backend/requirements.txt`（增加 jieba）
- `backend/app/assets/repository.py`（分词 + OR 匹配）
- `backend/tests/assets/test_repository.py`
- `frontend/src/lib/library-search.ts`（空白/标点近似 OR，生产检索走 API）
- `frontend/src/lib/library-search.test.ts`

**前置条件**：素材库 `search_blob` 与 `/api/v1/assets/items?q=` 已存在。

**已确认**：jieba 分词；多词 OR；过滤过短 token（长度 &lt; 2）以降低单字误伤。

### Stage 1: 后端分词匹配
- **目标**：`tokenize_query` 用 jieba 切词；token `casefold` 后任一为 `search_blob` 子串即命中；空查询仍返回全部；无有效 token 时回退为整段子串。
- **成功标准**：`pytest backend/tests/assets/` 通过；覆盖多词 OR、无空格中文切词、无关词不误杀。
- **状态**：Complete

### Stage 2: 前端镜像与测试
- **目标**：前端 helper 用空白/标点拆分做 OR（无 jieba）；面板检索仍走后端。
- **成功标准**：相关 vitest 通过。
- **状态**：Complete

## 完成记录

- **完成时间**：2026-10-09
- **实际结果**：后端 `tokenize_query` = 空白/标点 chunk（保留整词）+ jieba 词（len≥2），`item_matches_query` 为 OR 子串；依赖 `jieba>=0.42.1`。前端 helper 仅空白 OR（面板走 API）。`pytest tests/assets/` 15 passed；`library-search` vitest 4 passed。
- **偏差说明**：除 jieba 外额外保留 chunk，避免「红发」被切成单字后 OR 失效。
