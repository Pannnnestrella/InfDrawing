## 任务：不规则 Mask 与局部重绘 Crop / Stitch

**背景**：用户希望通过 SAM 2/3 或手工圈选获得不规则 Mask，只向生成模型发送局部裁剪图和对应 Mask，再精确拼回原图。当前多轮编辑的小部件路径仍发送完整原图与实体矩形 Mask；需要把分割、预处理、尺寸适配、生成和融合拆为可独立验证的步骤。

**影响范围**：见下文文件清单；本轮仅新增本规划并追加会话记录，不修改源代码、不安装依赖、不下载权重、不进行付费调用。
**前置条件**：现有 controlled_edit 会话、版本树、ArtifactService 和万相 inpaint 可复用；实施须用户明确批准本规划。SAM 依赖安装和权重下载的具体清单在环境检查后呈报确认。
**规划日期**：2026-10-12。
**整体状态**：Stage 1–6 / Stage 8 代码与缩减验收已完成；Stage 7 代码完成但 Qwen 真实出图未成功。以下状态已于 2026-10-12 对照仓库源码复核（本轮不改代码）。

### Stage 1: 确认模型能力、环境与数据契约
- **目标**：实现按 provider/model 区分的尺寸能力配置；确认 SAM 2.1 环境与权重；定义 Mask、CropResult、Stitcher 和局部编辑接口契约。
- **成功标准**：离线契约测试覆盖输入边长、像素面积、宽高比、尺寸取整和不支持 Mask 的模型；输出依赖清单；历史会话能兼容新增可选字段。真实出图前明确记录文档能力与当前 Key 实测能力的区别。
- **状态**：Complete（代码与契约）
- **核实**：`inpaint_capabilities.py`、`inpaint_types.py`（MaskRecord / Stitcher / LocalTurnFields）、`requirements-segmentation.txt`、相关几何与契约测试均在仓库中。SAM 权重路径已配置（`data/models/sam2.1/...`，gitignore）；**当前工作区未见权重文件**，需本机存在才可真实分割。

### Stage 2: 实现不规则 Mask 获取与手工编辑
- **目标**：SAM 2.1 使用实体框或正负点击点生成轮廓；前端支持套索/多边形圈选、画笔添加、橡皮擦除、撤销/重做和候选 Mask 选择。自动分割不可用时仍可手工完成流程。
- **成功标准**：显示坐标正确映射到原图像素；缩放、留白、设备像素比不改变 Mask 位置；用户确认后保存 Mask artifact，与具体父版本绑定；切换版本清理未确认草稿。
- **状态**：Complete（批准范围内）
- **核实**：`MaskEditor.tsx` / `mask-edit.ts`、`sam2_segmenter.py`、`sam3_client.py`、`POST .../masks` 与 `.../segment` 已实现。SAM 3 仅为可配置 HTTP adapter；无独立服务时前端显示未配置。版本切换通过 `InpaintControls` 的 `key` 重挂载清理草稿。

### Stage 3: 实现 Mask 预处理与 Inpaint Crop
- **目标**：实现阈值、可选封闭空洞填充、膨胀、有限羽化，计算联合 Bounding Box、上下文扩展、宽高比适配和统一空间变换；输出裁剪图、模型 Mask 和 Stitcher。
- **成功标准**：合成图测试覆盖空 Mask、多块区域、细长区域、图像四边/四角、奇数尺寸和超界裁剪；不发生非等比拉伸；裁剪区域覆盖最终融合支持域；原图与 Mask 始终共用变换。
- **状态**：Complete（首版万相正方形画布）
- **核实**：`masks.py`、`inpaint_crop.py` 与 `test_inpaint_geometry.py` 覆盖空 Mask、多块联合框、边角/奇数尺寸、Mask 外不变性。当前工作画布固定约 1024×1024（万相保守策略）；未实现规划中的「可选最小连通域面积过滤」「远距离多块上下文浪费提示」。

### Stage 4: 接入局部生成与 Inpaint Stitch
- **目标**：默认以万相 2.1 接收 crop + 二值 Mask；生成后逆变换并仅按融合 Mask 写回；在完整合成图上复用实体重解析与验收。增加实际请求提示词和重试反馈记录。
- **成功标准**：通过 mock 验证生成请求中没有完整原图或额外身份参考图；无论模型如何修改上下文，最终 Mask 支持域外原图像素逐值一致；返回尺寸轻微取整能恢复，异常比例或生成构图变化有明确提示；失败不创建损坏结果。
- **状态**：Complete（稳定路径 = 万相）
- **核实**：`service.py` 显式 `edit_mode=local` 走 crop→万相→stitch；`prompt_compiler` / `retry_feedback` 接入；版本持久化 `stitcher`。`InpaintOptions.model` 仅允许 `wanx2.1-imageedit`；非 `binary_field` 模型在 crop 层拒绝。Qwen 2.1 不在 Studio 稳定局部路径。

### Stage 5: 集成多轮编辑 UI、持久化与演示
- **目标**：浮窗内提供 Mask 编辑、裁剪预览、编辑区/羽化区/上下文区显示、参数调整、局部重绘模型选择和版本详情；完整结果可导入画布与分支回退。
- **成功标准**：自然语言指令与用户 Mask 配合可执行；重启后原图、Mask、裁剪元信息和版本仍可关联；现有无 Mask 整图编辑不受影响；已有会话不需重建。
- **状态**：Complete（有小缺口）
- **核实**：`InpaintControls`（参数、离线预览、候选/历史 Mask）、`StudioWorkspace` 提交局部 turn、`VersionDetails` 展示 stitch 元信息、导入画布仍可用。缺口：UI 文案写死「万相 2.1」，无局部模型切换器；预览为裁剪图/生成 Mask/融合 Mask 三图，非原图上叠加「编辑区/羽化区/上下文区」分区标注；设置页无 SAM 专项配置入口。

### Stage 6: 真实样例验证与 Review Gate
- **目标**：对照现有整图 Mask 路径和新 Crop/Stitch 路径，测试换剑、改手套、删除物件、边缘物件及多块 Mask；运行相关测试、lint、类型检查并完成代码审查。
- **成功标准**：记录非编辑区域差异像素数为 0、尺寸保持、边缘接缝、人眼修改效果、延迟和实际调用成本；归档输入/输出尺寸与截图。审查明确给出正确性、规范一致性、测试、风险结论。
- **状态**：Complete（用户缩减范围）
- **核实**：离线测试与 Review Gate 结论见下文完成记录。真实样例以盾牌改色为主；换剑/手套/删除/换形状等未按原清单全跑。实验归档目录 `data/logs/20261012_local_inpaint_crop_stitch/` 与对照页 `frontend/public/inpaint-comparison/` 均在 `.gitignore`；**当前工作区未见这些产物**（需本机曾生成或另存）。

## 一、当前实现与历史风险

- `backend/app/controlled_edit/region_ops.py` 的 `build_edit_mask` 按实体框画矩形；`uses_local_mask` 判断非背景/非整体主体且框面积不超过 25%。
- `service.py` 的万相分支直接传 `parent_bytes` 和整图 Mask；输出尚未用目标 Mask 强制与原图合成。
- `sizing.py` 目前沿用三种 OpenAI 输出比例，并未按阿里模型区分；`pad_to_supported` 的画布也没有显式缩放成目标像素尺寸。新 Crop 流程需要明确像素变换，不能直接套用该函数。
- `dashscope_wanx.py` 会在 provider 内部把短边不足 512 的图像放大；新流程应在 Crop 层完成尺寸适配，避免未记录的二次缩放。
- 万相局部路径现在优先原始用户指令，编译的验收反馈未真正进入下一次请求。接入时修正并记录实际发送文本，遵守 800 字符限制，优先保留本轮目标和关键纠错内容。
- 2026-10-06 曾取消旧 crop-edit-paste，原因含矩形残影和构图漂移。本次按用户新需求重新引入，使用不规则融合 Mask、明确逆变换与像素不变门禁，不能恢复旧矩形覆盖逻辑。
- 相似实现可复用：`BBoxEditor.tsx` 的显示坐标映射、现有锚点裁图、版本 artifact 和 Memory/SQL JSON 仓储。

## 二、API 尺寸调研与接入策略

调研时间为 2026-10-12。以下是官方文档能力，不代表当前 Key 已实际成功调用。输入尺寸和输出尺寸是两个独立约束，不能混用。

| 模型 / 接口 | 输入要求 | 输出要求及本次策略 |
|---|---|---|
| 万相 `wanx2.1-imageedit` | 原图和 Mask 同尺寸，各边 512–4096，单图不超过 10MB；Mask 必须纯黑/纯白 | HTTP 异步。局部重绘参数表没有清晰给出可配置输出尺寸契约，SDK 示例出现 size，但不能据此假定生效。读取实际返回尺寸并实测横/竖/方图；首版保守使用 1024×1024 工作画布，不声明它仅支持固定尺寸。 |
| Qwen `qwen-image-2.0` 系列 | 建议每边 384–3072，单图不超过 10MB；多图最后一张影响比例 | size 可指定 W*H，总像素 512²–2048²；实际宽高调整到最近 16 倍数。支持多种尺寸，不限固定三档；现有 2.0 路径无专用 Mask 参数，本次不把普通多图输入当作已验证 mask inpaint。 |
| Qwen `qwen-image-2.1-pro/turbo` | 文档每边 1–8000，长短边比不超过 10，建议 384–2048；单图 10MB | 输出总像素 512²–2048²、比例 1:8–8:1；无专用 mask 字段。候选路径只传 crop 与独立 Mask 两张输入图，角色顺序由适配器定义并明确提示。能力须实测，不继承 2.0 的最后图定比例或 16 倍数规则为既定事实。 |
| 万相 `wan2.7-image/pro` | 每边 240–8000，比例 1:8–8:1，单图 20MB | 编辑支持 1K/2K 或自定义宽高，编辑总像素 768²–2048²，可能微调输出尺寸；有 bbox_list 而无专用 mask 字段。本次仅保留未来适配能力，不列为已验证不规则 mask 后端。 |

**结论**：这些阿里接口不是普遍只支持 1024×1024。Mask 的语义 Bounding Box 应由有效像素决定；尺寸要求影响的是后续上下文裁剪框和模型工作画布，不能为了凑尺寸修改原始 Mask 定义。

**能力配置拟包含**：`mask_mode`（binary_field / image_prompt / unsupported）、输入边长和字节上限、输出像素面积和比例范围、尺寸取整、固定尺寸候选、图像顺序、Mask 编码方式、输出尺寸容差及文档日期。provider 在送出前校验，不静默变形。正式调用确认实际 API model ID；2.0 历史名称与当前文档别名可能不同。

**官方来源**：
- [万相 2.1 API](https://help.aliyun.com/zh/model-studio/wanx-image-edit-api-reference)
- [Qwen 2.0 编辑 API](https://help.aliyun.com/en/model-studio/qwen-image-edit-api)
- [Qwen 2.1 / 3.0 API](https://www.alibabacloud.com/help/en/model-studio/qwen-image-generation-and-editing-api-reference)
- [Qwen 2.1 独立 Mask 能力说明](https://qwen.ai/blog?id=qwen-image-2.1)
- [万相 2.7 API](https://help.aliyun.com/zh/model-studio/wan-image-generation-and-editing-api-reference)

## 三、SAM 与手工 Mask

### SAM 2.1 默认方案

使用 `SAM2ImagePredictor`，以现有 Qwen 实体框作 box prompt，支持用户正/负点击细化；返回多个候选时显示选择，不自动将所有候选合并。用户确认后，可继续用画笔与套索修改。实体框用于提示 SAM，不作为最终编辑 Mask。

官方要求 Python >=3.10、PyTorch >=2.5.1、torchvision >=0.20.1，Windows 推荐 WSL。本项目维持 Python 3.11；先核对 RTX 5070 Ti Laptop GPU（本机报告约 12GB 显存）对应的 PyTorch/CUDA 支持和实际显存需求，再确定安装版本。GPU 名称和容量不等于兼容性或分割速度已验证。

优先评估 SAM 2.1 small，可调整 tiny/base-plus；权重通过包/官方地址管理，放 `data/models/` 且不提交。图像 embedding 可按 owner + artifact hash + 模型版本缓存，限制缓存体积，分割计算通过明确服务边界执行。

### SAM 3 方案

支持文本与视觉提示，可识别一个语义概念的多个实例；需让用户选择实例。官方仓库要求 Python >=3.12、PyTorch >=2.7、CUDA >=12.6，与本项目 Python 3.11 冲突。因此主后端只提供 SAM 3 HTTP 客户端适配器，连接用户指定的独立推理服务；不在当前 `.venv` 中强行安装、不升级项目 Python。独立服务运行环境和安装命令需另行明确授权。

SAM 3 adapter 属于本规划范围，但真实 SAM 3 验收依赖可用服务；未验证时界面显示不可用，不能把 mock 测试当真实支持。

参考：[SAM 2 官方仓库](https://github.com/facebookresearch/sam2)、[SAM 3 官方仓库](https://github.com/facebookresearch/sam3)。

### 手工编辑与坐标

所有 Mask 以 EXIF 校正后的源图 W×H 为基准；页面坐标通过实际图像显示区域（排除 contain 留白）、缩放和平移逆变换到源像素。支持闭合套索、多边形、画笔、橡皮、清空及撤销重做。Mask 使用单通道灰度 PNG 存储，白=编辑；预览覆盖色不写进 Mask。

## 四、Mask 预处理：生成 Mask 与融合 Mask 分离

拟定参数均在**原图像素坐标**定义，UI 显示处理结果；以下默认值是待实测的工程起点：threshold=0.5、fill_holes=false、dilate_px=8、feather_sigma_px=4、context_from_mask_extend_factor=2.0、工作画布约 1MP。

1. 归一化输入到 [0,1]，阈值过滤低强度像素。二值图中的高强度孤立点不是低强度噪声，另设可选最小连通域面积过滤，默认关闭以保留细线。
2. 可选填洞：仅填与图像边界不连通的封闭洞，不连接独立区域。
3. 膨胀得到硬编辑支持域 S；羽化不无限扩散到 S 外。
4. `generation_mask`：覆盖 S 的二值 Mask；万相使用最近邻缩放后重新二值化，保证纯黑白。
5. `blend_mask`：用 GaussianBlur(S) 并乘 S，严格裁定 S 外 alpha=0；极小值置零。默认向内羽化，既保留过渡又保证支持域外完全不变。S 内边缘是允许融合变化的区域，区别于原始圈选。
6. 算法保证 generation_mask 覆盖所有 blend_mask 非零像素。用户扩张编辑区时同步扩大模型可编辑范围；不能在模型未重绘的区域扩大融合权重。

空 Mask 应在调用模型前报可定位错误；多块 Mask 默认求整体联合框，保留中间黑区。多块距离远时显示上下文浪费提示，首版不自动拆成多次付费生成。

## 五、Inpaint Crop 与尺寸适配

### 计算顺序

`有效 Mask → 预处理硬支持域 → 最小联合框 → 上下文扩展 → 比例适配 → 边界处理 → 工作画布缩放`。

上下文系数 f>=1 表示宽高总量各乘 f，而不是每边额外增加 f 倍：200×200、f=2 得到约 400×400。另设最小上下文像素，避免 1 像素目标裁得过小。

先选合法目标尺寸及比例，再以框中心向外扩大 crop 到该比例，不裁掉任何支持域，不把宽高分别拉伸。可变尺寸后端按面积预算与比例选尺寸；固定尺寸后端按其候选比例扩框。边界附近优先整体平移 crop 保留尺寸；仍超界则记录 padding，图像采用边缘复制/反射，Mask padding=0。

例：4096×4096 源图，200×200 编辑区，经 f=2 扩到 400×400，送 1024×1024 工作画布，生成后恢复 400×400。细长区域可能因比例适配扩大上下文；UI 显示实际 crop 和有效编辑区，允许调整预算与上下文。

### Stitcher 数据契约

内部不可变 `Stitcher` 记录：schema_version、父版本与源 artifact/hash、源尺寸和模式、原始/处理后 Mask artifact、联合框、虚拟 crop_rect（半开像素坐标）、与原图相交的 paste_rect、padding 四边、未缩放 crop_canvas_size、模型输入尺寸、content_rect/缩放关系、目标与实际输出尺寸、预处理参数、融合 Mask artifact。

运行时可持有源图数组；持久化只存 artifact 引用和可序列化几何，不把大图字节塞入版本 JSON。不使用 Python pickle 或任意客户端提供的 Stitcher；后端生成并验证映射，客户端只提交父版本和 Mask/参数。

Crop 与 Stitch 是通用图像处理模块，不调用 Diffusion、不依赖 SAM 或万相 SDK。provider 不应再做未记录的裁剪或 resize。

## 六、局部生成与 Stitch

1. 默认只发送 crop 原图、同尺寸二值 Mask 和局部编辑指令；不发送整帧、身份锚点或其他图像。SAM 可对整图分割，但它与图像生成请求是不同步骤。
2. 局部指令不使用原图归一化实体框；转换成 crop 坐标或直接使用 Mask 描述。重试文本从实际验收失败原因构建，不能仅重复同一原始请求。
3. 读取输出真实宽高；允许记录的输出取整，先映射回完整 crop_canvas，再移除 padding，取 paste_rect。明显宽高比不符或内容重排时提示失败/重试，不能用无条件拉伸掩盖。
4. 生成与源局部转到一致颜色空间后按 alpha 混合；颜色管理和 EXIF 在源图基线建立时一次完成。输出以源图数组副本为底，alpha=0 位置直接保持源值，避免整图重编码颜色转换导致像素差异。
5. 采用传统 Alpha Blending：I_out = M*I_gen + (1-M)*I_orig；羽化使用源坐标融合 Mask，不从生成结果检测区域。
6. 输出 PNG，尺寸与校正后的原图一致；RGB/RGBA 原图需保持 Mask 外所有通道，RGBA 内部使用预乘 alpha 处理以减少透明边晕。像素不变指解码后的源图基线，不要求压缩文件字节相同。
7. 拼回后再执行完整图场景重解析/构图验收；Mask 外差异必须为 0，VLM 仅补充验证语义效果。坐标精确不能修复模型在 crop 内重新构图，Alpha Blending 也不能保证所有样例完全无缝，需要上下文和人工视觉验收。

新增显式 Mask 的 local 模式优先于旧 25% 自动规则；自然语言想改 Mask 外区域时提示调整 Mask 或选择整图，不能静默扩大。扩大区域与实体锁定框相交时沿用锁定冲突处理，需解锁或修正 Mask。旧无 Mask 请求仍使用兼容路径。

## 七、拟修改与新增文件

### 后端
- 新增 `backend/app/controlled_edit/masks.py`、`inpaint_crop.py`、`inpaint_stitch.py`：预处理、几何和融合纯函数。
- 新增 `backend/app/controlled_edit/segmentation.py`、`sam2_segmenter.py`、`sam3_client.py`：统一接口、本地 SAM 2.1 和远端 SAM 3 adapter。
- 新增 `backend/app/pipeline/image_providers/inpaint_capabilities.py`：按模型的尺寸和 Mask 能力。
- 修改 `schemas.py`、`api.py`、`service.py`、`prompt_compiler.py`、`region_ops.py`、`repository.py`：Mask artifact、父版本校验、turn mode、stitch 元信息与兼容加载。
- 修改 `backend/app/config.py`、`backend/app/system/capabilities.py` 与 `dashscope_wanx.py`：配置、可用能力、尺寸前置校验。Qwen 2.1 adapter 在确认启用后增加明确的 image-mask 模式。
- 按需新增 `backend/requirements-segmentation.txt`，不在通用启动路径强制导入 SAM。Memory/SQL 版本使用 JSON 数据列，优先新增可选序列化字段；若实现发现需迁移，再追加具体影响范围。
- 相关新增测试置于 `backend/tests/controlled_edit/` 与 provider 镜像测试目录。

### 前端与记录
- 新增 `frontend/src/studio/MaskEditor.tsx`、`mask-edit.ts`、`InpaintControls.tsx` 及对应测试。
- 修改 `VersionViewer.tsx`、`StudioWorkspace.tsx`、`EditComposer.tsx`、`VersionDetails.tsx` 与 `frontend/src/lib/controlled-edit-api.ts`；按需接入设置页。
- 更新 `docs/controlled_edit.md`（英文）与 `.cursor/task_plan.md`、`progress.md`、`findings.md`（中文）；实验归档至 `data/logs/20261012_local_inpaint_crop_stitch/`。

### API 契约草案
- `POST /sessions/{id}/versions/{version_id}/masks`：owner 保护的 Mask 上传，校验尺寸与父版本。
- `POST /sessions/{id}/versions/{version_id}/segment`：bbox / 正点 / 负点 / 可选文本，返回候选 Mask artifact 与分数。
- `POST /sessions/{id}/versions/{version_id}/inpaint-preview`：离线生成 crop 预览和处理后 Mask，不付费生成。
- 现有 `POST /sessions/{id}/turns` 增加可选 `edit_mode`、`mask_artifact_id`、`inpaint_options`；model 选择必须明确，不能被局部自动路由静默覆盖。
- 所有 Mask artifact 绑定 owner、父图 hash/版本；旧 Mask 不自动沿版本树复用，图像内容变化后须重新确认。

## 八、验证与质量门禁

- **预处理**：填洞开关、阈值、膨胀半径、有限支持羽化、多个连通域；参数边界与空 Mask。
- **几何**：非正方形、细长、四角、超界、奇数尺寸、工作图尺寸取整；图像与 Mask 同一变换；identity 模型与纯色模拟模型恢复定位。
- **不变性**：强制 mock 模型把整个 crop 染色，断言融合支持域外所有通道差异为 0；裁剪框内但 Mask 外也必须为 0；JPEG 输入按首次解码基线比较。
- **集成**：API owner/父版本/尺寸错误、手工 Mask、SAM 候选、失败重试和实际 prompt、Memory/SQL JSON 兼容、版本切换、历史恢复。
- **前端**：contain 留白、浏览器 zoom、画布缩放和平移、pointer capture、套索闭合、撤销、切换版本和过期分割响应。
- **真实图像**：方/横/竖 crop、返回尺寸、删除/换色/换形状、不同上下文与 feather；归档 Mask、输入 crop、模型输出、最终图、参数与延迟。减少输入面积提升局部像素密度，但不保证云 API 单价降低；按实际计费记录。
- Python 命令只使用 `backend/.venv/Scripts/python` 及该环境工具；相关 pytest、Ruff、前端 TypeScript/ESLint/Vitest 通过后进行 Review Gate，不无限扩大无关测试。

## 九、待确认事项

1. **批准范围**：推荐先完成 SAM 2.1 + 手工 Mask + 万相 Crop/Stitch 闭环，同时交付 SAM 3 adapter；SAM 3 真实联调待独立服务可用后追加完成记录。
2. **SAM 3 环境**：项目 Python 3.11 与官方 >=3.12 不兼容；是否已有可连接的 SAM 3 服务？无服务时先用 SAM 2.1，不安装不兼容环境。
3. **Qwen 2.1**：推荐先列为可选实验后端，获得 crop+mask 实测结果后再启用，不直接替换稳定路径。
4. **依赖与权重**：具体安装版本/下载体积在 Stage 1 检查后确认；本规划批准不等于授权未列明的环境升级。
5. **费用**：真实样例验收会产生云 API 调用；调用前列出模型、样例数与预估费用并确认。离线测试和预览先完成。

收到用户明确批准后开始实施。执行中以追加状态记录保留规划历史；完成后追加完成时间、实际结果和偏差，不删除历史内容。

## 2026-10-12 执行状态与范围补充

- 用户已批准逐阶段实施、SAM 2 与 Ruff 安装、SAM 2.1 small 权重下载，以及补齐前端已有依赖。
- Stage 1–5：实现已完成，复核中。包括模型能力配置、手工套索/多边形/画笔、SAM 候选、Mask 预处理、Crop/Stitch、显式局部请求与持久化。
- Stage 6：In Progress。后端相关测试 88 项通过，前端类型检查、相关 lint 与 10 项测试通过；SAM CPU 合成图推理已通过。
- SAM 3 交付可配置 HTTP adapter，真实服务未配置，暂不声称已完成 SAM 3 真实推理。
- 用户要求减少付费测试并同时比较 Qwen 2.1 与万相：改为同一盾牌改色任务，两模型各 1 张（北京单价合计约 ¥0.39），无自动重试；用户要求先打开网页，再测试。
- 新增 `scripts/cedit_crop_stitch_compare.py` 与 `scripts/templates/inpaint_compare.html`。先离线发布网页，再生成；展示共享输入、SAM Mask、模型原始输出、拼接滑动对比及非编辑区域像素差异。归档仍在 `data/logs/20261012_local_inpaint_crop_stitch/`，网页生成资源放 `frontend/public/inpaint-comparison/` 并忽略提交。
- Qwen 2.1 仅作为独立实验使用 Mask 参考图，不改当前稳定局部编辑模型选择。

## 完成记录（2026-10-12）

- Stage 1：Complete。能力表、局部请求与空间映射契约、可选依赖配置完成。
- Stage 2：Complete（当前批准范围）。手工 Mask、SAM 2.1 small CPU 分割和 SAM 3 adapter 完成。真实盾牌 SAM 分数 0.946；SAM 3 无独立服务，真实推理待配置后联调。
- Stage 3：Complete。阈值、可选填洞、膨胀、有限支持羽化、上下文扩展、边界 padding 与源坐标映射完成。
- Stage 4：Complete。显式局部模式仅传 crop 与 Mask；重试使用实际反馈；版本保存 Stitcher；拼接后整图验收与锁定检查完成。
- Stage 5：Complete。套索/多边形/画笔/橡皮/撤销重做、候选与历史 Mask、预处理参数、离线预览与版本切换清理完成。
- Stage 6：Complete（缩减的测试范围）。后端 90 passed、前端相关 11 passed；TypeScript、相关 ESLint 与 Ruff 检查通过。已用 Edge 截图核对对照网页显示。真实矩形输入 API 对照、删除/换形状等样例按用户减少测试数量的要求未调用。
- 付费实验共两次尝试，无自动重试：万相 116.60 秒成功，1024×1024 输出；Qwen 2.1 182.85 秒 ReadTimeout，未获得输出。预计费用按输出单价约 ¥0.39，实际扣费取决于服务端处理结果与免费额度。后续脚本 Qwen 等待上限改为 600 秒，仅影响未来明确授权的调用，本轮不重试。
- 万相最终 Mask 支持域外变化像素数与最大差值均为 0。但盾牌内部出现白色区域，风格偏离原画，本次编辑质量未通过人工验收。Qwen 超时不能证明其 Mask 效果优劣。
- 对照网页：`http://127.0.0.1:3000/inpaint-comparison/index.html`。包含共享原图、SAM Mask 叠加、模型输入、模型 Mask、原始输出、滑动对比、差异图、几何与实际提示词。结果与状态已发布，原有会话未改动。
- 执行偏差：最初前端服务未启动，打开网页失败后万相请求已提交，未严格实现用户要求的先打开再测试；已向用户明确说明，并立即启动服务、打开网页（HTTP 200）。Qwen 调用在网页成功打开后进行。

### Review Gate

## 2026-10-12 后续任务：整图对照与 Qwen 异步修复

用户明确要求万相使用原图重绘，以及尝试修复 Qwen 2.1 Pro 推理，授权在现有功能上继续实施。

### Stage 7：Qwen 2.1 异步推理
- 目标：增加官方异步 endpoint、任务 ID 保存、有限等待轮询与错误状态处理；Qwen 2.0 保持原路径。
- 影响范围：`dashscope_qwen_edit.py`、provider 测试与对照脚本。
- 成功标准：mock 覆盖提交、处理中、成功、失败与超时；真实调用取得可追踪任务 ID，不因原 180 秒同步等待丢失任务。
- 状态：Complete（代码 / mock）；**真实出图未完成**。
- **核实**：`submit_edit_task` / `wait_edit_task` / 可选 `upload_temporary_image` 与 `backend/tests/test_qwen_async.py` 在仓库中；Qwen 2.0 仍走同步。真实 Base64 异步提交曾 ReadTimeout 且无 task_id；临时存储上传按用户选择未启用、未验收。

### Stage 8：万相原图重绘与网页比较
- 目标：相同原图、源坐标处理后 Mask、指令与 seed，不裁剪传给万相；保留原始模型输出并测其 Mask 外差异，另展示统一融合后的结果。Qwen 继续原 crop+mask，新增一张异步测试。
- 影响范围：`scripts/cedit_crop_stitch_compare.py`、HTML 模板、实验归档与会话记录。
- 成功标准：网页明确区别裁剪/整图输入及原始/融合指标，保留上次失败历史。
- 状态：Complete（万相对照）；Qwen 异步真实输出仍失败（见 Stage 7）。
- 费用：新增万相 1 张 ¥0.14、Qwen 2.1 Pro 1 张 ¥0.25，共约 ¥0.39（前次已核对北京单价）；每模型只提交一次，轮询不重复生成，失败不自动新增任务。用户当前明确测试请求沿用已说明模型与单价。
- **核实**：脚本支持 `--followup`（`wanx_full` + `qwen_async`）；模板 `scripts/templates/inpaint_compare.html` 存在。对照页产物被 gitignore，当前工作区未见生成结果。

### Stage 7–8 执行记录与用户最新选择
- Stage 8：Complete。万相原图与同区域源坐标 Mask，seed=7、相同指令，143.30 秒成功。原始输出 Mask 外变化 613,919 像素，最大通道差值 104；统一融合后两项均为 0。整图输入无上次白色大块，仍需检查风格与形状变化。
- Stage 7：代码及离线测试完成，真实推理未成功。Base64 异步提交 62.24 秒 ReadTimeout，未返回任务 ID。相关后端 105 项测试通过，Ruff 通过。
- 诊断：空 messages、n=0 的小请求正常，异步诊断任务返回后因空消息 FAILED，无图像生成。约 500KB、1MB、2.3MB 的空消息诊断请求读取超时；TCP/TLS/发送阶段正常，问题与大请求相关，但不能确定阿里网关或中间网络的具体根因。诊断记录在 `qwen_diagnostics.json`。
- 提出官方免费临时存储 + URL 方案。自动审批拒绝验证上传，原因是缺少明确的临时存储授权；已向用户解释。这不是之前模型请求超时的原因。
- 用户明确选择不上传，要求先打开现有万相结果。临时上传与额外 ¥0.25 出图均未执行。provider 保持默认 Base64，不自动使用临时存储；可选上传代码不在默认调用路径。Qwen URL 方案真实验收未执行。
- 已发布并打开原网页（HTTP 200），展示裁剪与整图两种万相结果及 Qwen 失败历史，原有会话未改动。

- 正确性：源版本/哈希绑定、空 Mask 快速失败、锁定冲突优先返回 409、非法预处理返回 422、输出比例校验及 RGB/RGBA Mask 外逐像素不变通过测试。
- 规范一致性：源文件按前后端目录放置；Python 虚拟环境隔离；公开类/函数类型与 docstring；Ruff/格式化通过。FastAPI Depends 默认参数沿用项目惯例，忽略 B008；无新增依赖复制或二进制提交。
- 测试：几何、掩码、接口、编排、反馈重试、旧契约兼容、JSON 空间信息往返、SAM 3 mock 协议、前端请求与坐标映射覆盖。当前浏览器视觉验证针对实验页，画笔等交互尚未完成全面真人验收。
- 风险与限制：SAM CPU 速度、Mask 质量、生成区域内风格和内容重排仍需实际使用评估；Alpha Blending 不保证所有边缘无接缝。SAM 3 实服务及 Qwen 真实输出未验证，不宣称已完成。npm 补齐已有依赖时报告历史依赖漏洞，未在本任务升级整个依赖树。

## 2026-10-12 代码核实记录（只读，未改源码）

对照仓库源码、测试与文档，复核规划交付物。结论：**主闭环（手工/SAM2 Mask → 预处理 → Crop → 万相 → Stitch → Studio UI）已实现**；若干规划细则与真实联调项仍开放。

### 已实现（源码在仓库）

| 规划项 | 证据 |
|---|---|
| Mask / Crop / Stitch 纯函数 | `masks.py`、`inpaint_crop.py`、`inpaint_stitch.py`、`inpaint_types.py` |
| 模型能力表 | `pipeline/image_providers/inpaint_capabilities.py`（wanx binary / qwen2.0 unsupported / qwen2.1 experimental image_prompt / wan2.7 unsupported） |
| SAM 2.1 懒加载 + SAM 3 HTTP adapter | `sam2_segmenter.py`、`sam3_client.py`、`segmentation.py`、`requirements-segmentation.txt` |
| API：masks / segment / inpaint-preview / turns 局部字段 | `controlled_edit/api.py`、`schemas.py`、`service.py` |
| 前端 Mask 编辑 + 局部控件 | `MaskEditor.tsx`（套索/多边形/画笔/橡皮/清空/撤销重做/正负点）、`InpaintControls.tsx`、`controlled-edit-api.ts` |
| Studio 集成与版本元信息 | `StudioWorkspace.tsx`（显式 local turn）、`VersionDetails.tsx`（stitcher 摘要）、导入画布保留 |
| 重试反馈进入下一轮提示词 | `prompt_compiler.py` + `verifier.retry_feedback`；service 测试覆盖 |
| 文档 | `docs/controlled_edit.md` 已写 Local mask crop and stitch |
| 对照脚本 | `scripts/cedit_crop_stitch_compare.py`、`scripts/templates/inpaint_compare.html` |
| Qwen 2.1 异步 submit/poll（含可选临时上传代码） | `dashscope_qwen_edit.py`、`tests/test_qwen_async.py` |
| 几何 / 分割 / 局部编排测试 | `test_inpaint_geometry.py`、`test_segmentation.py`、`test_cedit_service.py` 等 |

### 部分实现 / 有偏差

| 规划项 | 现状 |
|---|---|
| 工作画布尺寸适配 | 万相首版固定扩到正方形再缩到 1024×1024；非「按模型面积预算选任意合法 W×H」的完整通用实现 |
| Stitcher 字段 | 有 crop/paste/padding/canvas/model/actual 等；规划草案中的独立 `content_rect` 名称未单独出现 |
| 预览「编辑区/羽化区/上下文区」 | 离线预览展示裁剪图、生成 Mask、融合 Mask；非原图叠加三分区标注 |
| 局部模型选择 | UI 写死万相；`InpaintOptions.model` Literal 仅 `wanx2.1-imageedit` |
| 万相 provider 内部短边放大 | `dashscope_wanx.py` 仍保留短边不足 512 时的放大；局部路径送 1024 时通常不触发，但非「Crop 层独占缩放」 |
| SAM 默认设备 | `cedit_sam2_device=cpu`；RTX 5070 Ti / CUDA 兼容性与速度未在本核实中验证 |
| Stage 6 样例矩阵 | 按用户要求缩减；盾牌改色 + 整图万相对照有记录；删除/换形状等未全覆盖 |
| 实验产物 | `data/logs/...`、`frontend/public/inpaint-comparison/`、`data/models/` 均 gitignore；**当前工作区目录缺失**，不能从仓库直接复开对照页或 SAM |

### 未实现或未验收

| 规划项 | 说明 |
|---|---|
| SAM embedding 按 owner+hash 缓存 | 代码中未见该缓存层 |
| 可选最小连通域面积过滤 | `prepare_mask` 无此步骤 |
| 远距离多块 Mask 的上下文浪费提示 | 前后端均无 |
| SAM 3 真实推理 | 仅 adapter；`cedit_sam3_base_url` 默认空 |
| Qwen 2.1 进入 Studio 局部稳定路径 | crop 拒绝非 binary_field；实验仅脚本 |
| Qwen 真实成功出图 / 可追踪 task_id | 两次真实尝试均超时失败 |
| Qwen 临时存储 URL 真实验收 | 代码可选，默认关闭；用户明确不上传 |
| 设置页 SAM/权重配置 UI | 无专项入口（靠环境/配置字段） |
| 画笔等交互全面真人验收 | Review Gate 已写明未完成 |
| GPU 版 SAM 安装与测速 | 未作为已交付项 |

### 阶段状态一览（核实后）

| Stage | 状态 |
|---|---|
| 1 能力与契约 | Complete（代码）；权重需本机 |
| 2 Mask / SAM | Complete（SAM3 仅 adapter） |
| 3 预处理 + Crop | Complete（万相方画布首版） |
| 4 生成 + Stitch | Complete（万相稳定路径） |
| 5 UI / 持久化 | Complete（见部分实现缺口） |
| 6 真实样例 + Review | Complete（缩减范围） |
| 7 Qwen 异步 | 代码 Complete；真实出图未完成 |
| 8 万相整图对照 | Complete（万相）；Qwen 侧仍失败 |

本核实轮次**未修改任何源代码**，仅更新本规划文件中的状态与上述记录。
