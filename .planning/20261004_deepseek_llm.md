## 任务：意图 LLM 接入 DeepSeek

**背景**：摆脱对本地 Ollama 的依赖，使用 DeepSeek OpenAI 兼容 API 做意图识别与 Prompt 改写。
**影响范围**：`backend/app/config.py`、`providers.py`、`capabilities.py`、`worker.py`、前端 `CapabilityStatus`、文档与测试
**前置条件**：用户已在 `backend/.env` 配置 `INFD_LLM_PROVIDER` 与 `INFD_DEEPSEEK_API_KEY`

### Stage 1: Provider 与配置
- **目标**：`llm_provider=deepseek`，复用 OpenAICompatibleProvider
- **成功标准**：配 Key 后可 classify；未配 Key 报清晰错误
- **状态**：Complete

### Stage 2: capabilities / UI / 文档
- **目标**：探测与展示 DeepSeek；文档说明；Ollama 可选
- **成功标准**：capabilities 含 deepseek；重启后可用
- **状态**：Complete

**待确认事项**：已确认 — 默认 deepseek，模型 deepseek-chat

## 完成记录

- **完成时间**：2026-10-04
- **实际结果**：DeepSeek 意图 Provider（json_object）、默认 llm_provider=deepseek、capabilities/UI/文档
- **偏差说明**：DeepSeek 用 `json_object` 而非 `json_schema`
