## 任务：SAM2.1 不 crop 万相路径与方法对照

**背景**：显式 local 目前强制 crop→万相→stitch；自动小物件走整图+矩形 mask。需要把 SAM 不规则 mask 也能接到「原图 + 源尺寸涂白 mask → 万相」路径，并用同一起点、同一两轮指令对比四种变更方法。
**影响范围**：`inpaint_types.py`、`service.py`、preview API、Studio 前端、`scripts/cedit_method_compare.py`、`docs/controlled_edit.md`、相关测试
**前置条件**：crop/stitch、SAM2.1、万相 inpaint、Qwen 2.1 整图编辑、Two-branch knight 根图与 `character.sword` / `character.face`
**规划日期**：2026-10-12

### Stage 1: 后端 placement=fullframe
- **目标**：`InpaintOptions.placement`；local+fullframe 跳过 crop/stitch；preview 支持叠色原图
- **成功标准**：mock 测试断言整图尺寸入模、无 stitch；历史缺字段默认 crop
- **状态**：Complete

### Stage 2: 前端开关与提示
- **目标**：Studio「裁剪后发送 / 整图+Mask」；文案路径 `fullframe_mask`
- **成功标准**：提交仍 `edit_mode=local`，options 带 placement
- **状态**：Complete

### Stage 3: 对照实验脚本
- **目标**：武器/表情两组 × 四方法 × 两轮；拼图写入 `data/logs/20261012_method_compare_weapon_face/`
- **成功标准**：`--generate` 后产出 compare_weapon/face/all.png 与 report.json
- **状态**：Complete

### Stage 4: 文档与 Review
- **目标**：更新 controlled_edit.md；Review Gate
- **成功标准**：文档说明 placement；审查四类结论
- **状态**：Complete

**待确认事项**：用户已批准本规划并要求完整实施（含付费生成）。

## 完成记录

- **完成时间**：2026-10-12
- **实际结果**：`placement=fullframe` 已接入后端/Studio；16/16 对照格生成成功；拼图位于 `data/logs/20261012_method_compare_weapon_face/compare_{weapon,face,all}.png`
- **偏差说明**：表情组 SAM crop→万相 出现白脸椭圆（crop 小目标失败模式）；武器组多数方法第二轮「匕首」仍偏长刃，实体框万相更接近短刃
- **Review**：正确性——fullframe 跳过 stitch、默认 crop 兼容；规范——type hints/测试；测试——新增 fullframe 单测 + 原有 crop 通过；风险——fullframe 无硬像素保证，小脸 crop 不稳定
