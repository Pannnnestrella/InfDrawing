## 任务：多轮可控编辑 · 实体定位改进（专用定位模型 + 手动校正框）

**背景**：多轮可控编辑目前用 gpt-4o 做场景解析。实体名称和层级基本合理，但位置框偏差很大。以 run3 源图为例：剑的框没包住剑尖，盾的框横向偏了约 20%，脸的框偏到了脖子；坐标几乎全是 0.05 的整数倍，说明模型在估位置，没有真正定位。框不准会直接影响两处：锁定时按框裁出的参考图（锚点）可能裁错部位，悬停高亮的位置也不对。本任务同时做两件事：场景解析换用专门训练过定位的视觉模型，并允许用户在界面上手动校正实体框。

**影响范围**：

后端（修改）：
- `app/config.py`：新增 `INFD_CEDIT_SCENE_*` 配置（provider、base_url、api_key、model、坐标格式）
- `app/controlled_edit/vision.py`：`VisionClient` 支持传入 base_url、api_key、model（OpenAI 兼容的 chat completions 接口，DashScope 兼容模式和 Gemini 的 OpenAI 兼容端点都适用）；验收与意图解析仍用 gpt-4o
- `app/controlled_edit/scene_parser.py`：按坐标格式解析框（见下方「坐标格式」）；提示词按模型微调
- `app/controlled_edit/schemas.py`：`SceneEntity` 新增 `bbox_source: "model" | "manual"`；新增 `EntityBBoxUpdate` 请求体
- `app/controlled_edit/entities.py`：重解析合并时，锁定实体如果是手动框，保留手动框
- `app/controlled_edit/service.py`：新增 `update_entity_bbox`；被修改的实体如果已锁定，并且锚点取自当前版本，就按新框重新裁剪锚点
- `app/controlled_edit/api.py`：新增 `PUT /sessions/{sid}/versions/{vid}/entities/{eid}/bbox`
- `app/system/capabilities.py`：`controlled_edit` 能力里返回当前场景解析所用的模型名，方便在前端展示

后端（新增）：
- `scripts/cedit_grounding_compare.py`：同一张图分别跑两个模型，把框画到图上并排输出，用于选型

前端（修改）：
- `src/studio/VersionViewer.tsx`：选中实体后显示可拖拽的框（拖动整体平移，四角缩放），按 Enter 或点「保存」提交，按 Esc 取消
- `src/studio/EntityPanel.tsx`：每个实体加一个「调整框」按钮；手动框显示小标记
- `src/lib/controlled-edit-api.ts`：`updateEntityBBox`，类型新增 `bbox_source`
- `src/studio/StudioWorkspace.tsx`：管理框编辑状态

测试：
- `backend/tests/controlled_edit/test_cedit_parsing.py`：各坐标格式的解析与归一化
- `backend/tests/controlled_edit/test_cedit_service.py`：手动改框、锚点重裁、重解析时保留手动框
- `backend/tests/controlled_edit/test_cedit_api.py`：新接口的 200 / 404 / 越界框 422
- 前端：框拖拽的坐标换算纯函数单测

文档：`docs/controlled_edit.md` 增加「Scene grounding」和「Manual box correction」两节

**前置条件**：
- 多轮可控编辑已完成（`20261005_controlled_multi_turn_edit.md`）
- 需要一个定位模型的 key：DashScope（Qwen-VL）或 Google（Gemini），二选一，见待确认事项

---

### 坐标格式（各模型输出不同，需在实现时用真实请求核实）

| 格式值 | 说明 | 典型模型 |
|---|---|---|
| `xyxy_1000` | `[x_min, y_min, x_max, y_max]`，0–1000 相对坐标（现状） | gpt-4o（按提示词要求）、Qwen3-VL |
| `yxyx_1000` | `[y_min, x_min, y_max, x_max]`，0–1000 相对坐标 | Gemini 2.x / 2.5 |
| `xyxy_pixel` | `[x_min, y_min, x_max, y_max]`，送入图片的绝对像素 | Qwen2.5-VL |

上表来自各模型的公开文档和社区经验，Stage 1 会用真实请求逐一验证后再写死默认值。

### Stage 1: 定位模型选型对比
- **目标**：`VisionClient` 支持独立配置；`scripts/cedit_grounding_compare.py` 在 run3 源图（以及另外 1–2 张不同风格的图）上对比 gpt-4o 与候选模型，输出画框对比图和 JSON
- **成功标准**：对比图保存到 `data/logs/20261005_cedit_grounding/`；人工检查剑、盾、脸三个实体的框，候选模型明显优于 gpt-4o；确定默认模型和坐标格式
- **状态**：Complete

### Stage 2: 场景解析接入定位模型
- **目标**：`scene_parser.py` 支持三种坐标格式；未配置专用模型时回退到 gpt-4o（保持现有行为）
- **成功标准**：解析单测覆盖三种格式与越界裁剪；全部后端测试通过；用真实 key 跑一次创建会话，框位置正确
- **状态**：Complete

### Stage 3: 手动校正框（后端）
- **目标**：`bbox_source` 字段、`PUT .../bbox` 接口、锚点重裁、重解析时保留手动框
- **成功标准**：服务和 API 单测覆盖：改框、已锁定实体改框后锚点更新、下一轮重解析后锁定实体的手动框不被覆盖、越界或零面积框返回 422
- **状态**：Not Started

### Stage 4: 手动校正框（前端）
- **目标**：在图上拖拽和缩放框、保存、取消；实体面板显示手动标记
- **成功标准**：tsc、ESLint、vitest 通过；浏览器中完成一次「选中 → 调整 → 保存 → 锁定 → 查看参考图已更新」
- **状态**：Not Started

### Stage 5: 端到端验证与文档
- **目标**：用新模型重跑 `cedit_e2e.py` 三轮；更新文档
- **成功标准**：记录写入 `data/logs/`；参考图锚点裁到的是正确部位；文档更新
- **状态**：Not Started

---

**待确认事项**：
- [ ] 定位模型用哪家？
  - Qwen-VL（推荐）：通过 DashScope 兼容模式接入，项目里已有 DashScope 配置项，中文场景表现好；需要在 `backend/.env` 填写 `INFD_DASHSCOPE_API_KEY`（目前未配置）
  - Gemini 2.5：定位能力强；需要新配置 Google API key，国内网络可能需要代理
  - 两家都接，用配置切换（工作量多一点，主要在 Stage 1 的对比）
- [ ] 下一轮重解析时，手动框如何继承？推荐：只有锁定实体保留手动框（锁定意味着这块区域不应变化）；未锁定实体使用新解析的框，因为图已经变了
- [ ] 是否同时支持「手动新增实体」（在图上画框并命名）？用于模型漏识别的情况。推荐本期不做，先只做校正
- [ ] 本期不做：Grounding DINO / SAM 本地检测、像素级轮廓

## 用户决策（2026-10-05）

- 定位模型：Qwen-VL，通过 DashScope 兼容模式接入（`https://dashscope.aliyuncs.com/compatible-mode/v1`）。用户实际写入的是 `INFD_ALIBABA_API_KEY`，Settings 已支持该别名
- 手动框继承：只有锁定实体保留手动框，其余实体使用新解析的框
- 手动新增实体：本期不做
- 默认模型：`qwen3-vl-plus`（2026-10-05 对比后确认）；坐标格式 `xyxy_1000`

## Stage 1 对比记录（2026-10-05）

图像：`run3/v0_source.png`、`run3/v3.png`。输出：`data/logs/20261005_cedit_grounding/`。

源图关键实体 `box_2d`（0–1000）：

| 实体 | gpt-4o | qwen3-vl-plus | 目视 |
|---|---|---|---|
| face | [350,150,450,300] 偏左下 | [430,30,540,160] | plus 落在脸上 |
| sword | [150,300,350,600] 缺剑尖 | [80,50,315,580] | plus 包住整把剑 |
| shield | [500,400,650,700] 偏左 | [595,400,790,695] | plus 落在盾上 |

flash 与 max 的框与 plus 接近；plus 实体更全（14 个），作为默认。创建会话「Qwen grounding check」已用线上 Qwen 复验，脸/剑/盾坐标与上表一致。
