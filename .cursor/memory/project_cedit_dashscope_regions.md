---
name: 可控编辑阿里改图与区域约束
description: Studio 默认可走 qwen-image-edit-plus，点选目标 + 锁定贴回 + 局部 crop-edit
type: project
---

可控编辑默认图像模型是 DashScope `qwen-image-edit-plus`（`INFD_CEDIT_IMAGE_PROVIDER=dashscope`）。Qwen 以最后一张图定输出比例，参考图先发、当前图后发。万相 imageedit 带不了锁定 crop。

区域策略（用户选「组合」）：面板点选实体覆盖本轮 target；换武器/换色等单目标有框操作 crop 后贴回；其余整图编辑后再把 LOCKED 框从上一版贴回。主体框漂移先于 VLM 失败。SAM/mask 本期不做。
