## 任务：自动生成 mask + inpaint 对照实验

**背景**：Studio 当前默认 `qwen-image-edit-plus`（整图 + 参考图 + 文字，无 mask）。用户希望由已有实体信息自动做出 mask，把 **原图 + mask** 发给支持 inpaint 的 API，对照画面是否更能保住锁定区域。
**影响范围**：
- 实验脚本（建议 `scripts/cedit_mask_compare.py`）与归档目录 `data/logs/20261006_cedit_auto_mask/`
- 可选后续：`controlled_edit` 增加 `image_provider=wanx_mask` 分支（本规划 Stage 1 不做进主路径）
**前置条件**：实体框已由 Qwen-VL 解析；万相 `wanx2.1-imageedit` / OpenAI `/images/edits` 的 `inpaint` 已接入主画布

### Stage 1: 用实体框自动出 mask，跑对照
- **目标**：
  - 从当前版本实体状态生成一张 mask（白 = 可改，黑 = 必须留）：锁定/批准框涂黑，点选目标或 instruction 指向的框涂白；无框区域默认可改或默认保留（待确认）
  - 将原图 + mask 发给已有 inpaint（优先万相 `description_edit_with_mask`；可选 OpenAI 带 mask 的 edits）
  - 同一指令再跑一版现有千问 instruction-edit，三图并排：原图 / 千问 / mask-inpaint，外加 mask 可视化
- **成功标准**：归档图能肉眼判断锁定区是否更稳；不改 Studio 默认路径
- **状态**：Complete

### Stage 2: 若对照明显更好，再接入 Studio（可选）
- **目标**：第三档生图选项，例如 `万相 mask inpaint`；每轮仍可切回千问
- **成功标准**：下拉可选；版本详情能看到所用 provider
- **状态**：Not Started

---

**待确认事项**：
- [x] Stage 1 只做实验对照，不改 `/studio` 默认生成路径
- [x] 自动 mask 先用已有实体 bbox（矩形），不上 SAM2
- [x] 无框背景：本轮用 unconstrained=edit（涂白），锁定框涂黑
- [x] 对照 API 先用万相 mask

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：
  - 官方样例 `description_edit_with_mask` 调用成功（`probe_official_wanx.png`）
  - 骑士根图自动 mask + 万相 inpaint + 千问 edit 对照已归档 `data/logs/20261006_cedit_auto_mask/`
  - 万相 inpaint 改为官方 `data:image/png;base64` 传图，不再依赖 OSS getPolicy
  - 万相更能保住锁定矩形内的脸/甲；大面积白区改背景时出现紫边、南瓜、背景未真正变夜
  - 千问整图指令把夜晚做完整，但人物身份有漂
- **偏差说明**：Stage 2（接入 Studio）未做，等看图后再决定

