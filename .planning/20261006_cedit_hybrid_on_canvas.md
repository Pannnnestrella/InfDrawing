## 任务：背景整图 / 小物件 mask，可控编辑收回画布

**背景**：大改（换背景）应走千问整图；小物件应用万相 mask。独立 `/studio` 收回首页无限画布，新版本向右铺开。
**影响范围**：
- `region_ops.py`：`uses_local_mask` 路由
- `service.py`：小目标走万相 inpaint；背景/主体/无框走 instruction-edit
- 实验：`scripts/cedit_mask_small_rounds.py` → `data/logs/20261006_cedit_mask_small/`
- 前端：首页嵌入多轮编辑坞；结果 `pasteImageUrlToCanvas`（已在选中图右侧）；`/studio` redirect `/`
- `docs/controlled_edit.md`
**前置条件**：万相 mask 已打通；实体树已有 `character.*` / `environment.*`

### Stage 1: 小物件 mask 多轮实验
- **目标**：同一骑士图连改剑、盾、手套（白区仅目标框），出对照拼图
- **成功标准**：归档 `compare.png`；能判断小白区是否比换背景那轮可用
- **状态**：Complete

### Stage 2: 运行时路由
- **目标**：`environment*` / `foreground*` / 整主体 `character` / 无框 / 面积过大 → 整图；其余带框的 `character.*` 零件 → mask
- **成功标准**：单测覆盖上述分支；缺万相 key 时回退整图
- **状态**：Complete

### Stage 3: 画布铺开 + 关掉独立 Studio
- **目标**：首页从选中图开始会话；每轮新图贴在父图右侧；`/studio` 重定向首页；去掉顶栏独立入口
- **成功标准**：浏览器：首页选图 → 多轮编辑 → 画布向右出现新图；访问 `/studio` 回到 `/`
- **状态**：Complete

---

**待确认事项**（已由用户拍板）：
- [x] 换背景等大改走整图；小物件走 mask
- [x] 新版本在画布向右铺开，不原地替换
- [x] `/studio` 关掉，只留首页

## 完成记录

- **完成时间**：2026-10-06
- **实际结果**：小物件三轮 mask 归档 `data/logs/20261006_cedit_mask_small/compare.png`。路由 `uses_local_mask` 已接入。首页左侧坞 + `/studio` redirect。
- **偏差说明**：bbox 叠在 tldraw 图上尚未做；手套金线几乎看不出

