## 任务：元素拆解按提示识别多层

**背景**：云端拆解固定把整组主体收成一层前景。用户要求：提示为空时保持这一刀；提示里点名物体时，先识别再逐个拆成独立层。
**影响范围**：
- `backend/app/pipeline/image_providers/dashscope_decompose.py`
- `backend/app/pipeline/decompose_executor.py`
- `backend/app/api/generate.py`
- `backend/tests/test_decompose.py`
- `frontend/src/agent-panel/hooks/useChatSubmit.ts`
- `frontend/src/agent-panel/ChatComposer.tsx`
- `frontend/src/lib/pipeline-steps.ts`
**前置条件**：DashScope Key 已配置；画布回贴已按图层数组叠放，不限制层数。

### Stage 1: 空提示与点名分流
- **目标**：空白提示和历史默认句 `clean seamless background` 仍走现有两层；其余提示走识别。
- **成功标准**：单测覆盖空串、历史默认句与真实点名。
- **状态**：Complete

### Stage 2: 识别并逐个抠层
- **目标**：`qwen3-vl-plus` 按提示列出最多 6 个可见物体；每个物体一次品红抠图（允许小物体）；最后一次只擦掉这些物体补背景。背景在最下，物体由后到前。
- **成功标准**：mock 测试得到 N+1 层且标签正确；点名失败不退回 rembg 两层。
- **状态**：Complete

### Stage 3: 侧栏文案
- **目标**：留空不再塞入默认英文背景句；占位与提示说明两种用法。
- **成功标准**：ChatComposer 文案测试通过。
- **状态**：Complete

**待确认事项**：无。用户已要求接上：无提示默认两层，有提示做识别。

## 完成记录

- **完成时间**：2026-10-12
- **实际结果**：空提示与历史默认句走两层；点名提示经场景模型识别后逐个抠层，最多 6 个。点名失败直接报错。`tests/test_decompose.py` 13 通过；ChatComposer vitest 通过。
- **偏差说明**：小物体抠图放宽到至少 64 个不透明像素，避免原来的 8% 面积门槛把剑、盾判失败。
