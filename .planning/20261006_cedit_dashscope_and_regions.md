## 任务：可控编辑改用阿里改图 + 用实体区域真正控住修改

**背景**：Studio 多轮编辑的生图仍走 OpenAI `gpt-image-1`，单价高。用户同意改接百炼改图。同时场景解析已经能给出可用的实体框，需要把「识别到区域」变成「只改该区域、锁住其余」。
**影响范围**：
- `backend/app/config.py`：`INFD_CEDIT_IMAGE_PROVIDER`、阿里改图模型名
- `backend/app/pipeline/image_providers/`：新增或扩展 DashScope 多图编辑
- `backend/app/controlled_edit/service.py`、`prompt_compiler.py`、`anchors.py`
- 可能新增：`region_composite.py`（按框贴回）、矩形 mask 生成
- `docs/controlled_edit.md`、对比实验记录 `data/logs/`
**前置条件**：Qwen 场景解析已接入；`INFD_ALIBABA_API_KEY` 已配置；`ImageEditor` 协议已存在

### Stage 1: 阿里改图作为可切换的 ImageEditor
- **目标**：`qwen-image-edit-plus`（默认）实现 `multi_image_edit`：图1=当前图，图2..=锁定 crop；配置可切回 OpenAI
- **成功标准**：单测 mock 请求体；同一骑士源图跑 A 支三轮，记录价差与画质到 `data/logs/`
- **状态**：Complete

### Stage 2: 用实体框约束改动范围（见文末待确认）
- **目标**：按用户选定的区域策略，把 bbox 用进生成或合成
- **成功标准**：改目标实体时，未锁定区域的像素变化可量化下降（和 Stage 1 同图对比）
- **状态**：Complete

### Stage 3: 用实体框做确定性验收
- **目标**：重解析后比较目标/主体框的位置和面积；偏移超过阈值则失败并重试
- **成功标准**：镜头推近类问题不再只靠 VLM 打 1.0
- **状态**：Complete

---

**待确认事项**：
- [x] 生图改走阿里：默认 `qwen-image-edit-plus`（0.20 元/张），可切回 OpenAI
- [x] 区域怎么真正控住修改 → 用户选择「组合」：点选实体当目标 + 锁定框硬贴回 + 换武器/帽子等局部改完贴回；A 作为 prompt 补充；D（SAM mask）本期不做

| 方案 | 做法 | 效果 | 代价 |
|---|---|---|---|
| A. 提示词写框 | prompt 里写 target 的归一化框和「只改此区域」 | 实现快，约束仍然软 | 模型可以不理 |
| B. 目标裁块高清改、再贴回 | 只把 target bbox（加 padding）送给模型，结果羽化贴回原图 | 未改区域像素级不变 | 出框的改动（换背景、长大头发）做不了 |
| C. 锁定区域硬贴回 | 整图照改，再把 LOCKED 框从上一版羽化贴回去 | 脸/剑等锁定件像素级保住 | 接缝、锁定框不准时会切到错的部位 |
| D. 矩形/SAM mask 局部编辑 | 用框生成 mask，走万相 `description_edit_with_mask` | 和 B 类似，接口原生支持 | 换背景仍不适用；要接回 mask |
| E. 点选实体当指令目标 | 面板点中的实体直接写入 intent，少靠 LLM 猜 target | 减少改错对象 | 不管像素，管意图 |

推荐组合：**E + C 做锁定，B 仅用于目标完全落在框内的操作（换剑、换盾、换帽子）；换背景/换发型走整图 + C。** A 作为所有路径的 prompt 补充。D 本期不做。

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：默认编辑器为 `qwen-image-edit-plus`（无阿里 key 时回退 OpenAI）。点选实体写入 `target_entity_ids`；局部 replace/recolor/remove（及子部件 restyle）走 crop-edit-paste；每轮把 LOCKED 框从父图羽化贴回；主体框位移/面积超阈值先于 VLM 失败。能力探测 `models.image` 为 `qwen-image-edit-plus`。
- **偏差说明**：骑士 A 支阿里复跑与像素级「未锁定区域变化下降」对比未在本轮实图上做，只覆盖了单测与合成图。Wanx mask 路径按计划未做。
