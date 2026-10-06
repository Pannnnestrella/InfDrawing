## 任务：元素拆解改走云端分割/擦除

**背景**：当前 decompose 是本地 rembg + SD1.5 inpaint，插画边缘差。用户同意换成 API。
**影响范围**：
- 新增 `backend/app/pipeline/image_providers/dashscope_decompose.py`
- `decompose.py` / `decompose_executor.py` / `generate.py` / `capabilities.py`
- 测试 `tests/test_decompose.py`、`tests/test_capabilities.py`
**前置条件**：已有 `INFD_DASHSCOPE_API_KEY`

### Stage 1: 云端抠前景 + 擦除补背景
- **目标**：有阿里 key 时：`image-instance-segmentation` 出实例 mask → 合成透明前景；`image-erase-completion` 擦掉主体得背景。无 key 仍可走 rembg。
- **成功标准**：单测 mock 通过；capabilities 在仅配置 DashScope 时 `decompose.enabled`；骑士图能拆出前景层
- **状态**：Complete
- **备注**：`image-instance-segmentation` 提交后长期 PENDING（免费额度/并发=1），改走已验证的 `qwen-image-edit-plus`：品红底板抠前景（原图像素）+ 指令擦主体补背景。

---

**待确认事项**：用户已同意替换为 API。

## 完成记录

- **时间**：2026-10-06
- **实际结果**：骑士图云端拆层成功。前景透明 PNG 保留原图像素；背景由 Qwen 补全场景。对照：`data/logs/20261006_decompose_cloud/{fg,bg}.png`
- **偏差**：未使用 `image-instance-segmentation` / `image-erase-completion`（任务长期 PENDING）。有 DashScope key 时走 `qwen-image-edit-plus`，失败再回退 rembg。
