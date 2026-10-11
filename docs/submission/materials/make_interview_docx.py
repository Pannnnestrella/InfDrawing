# -*- coding: utf-8 -*-
"""Generate InfDrawing interview Q&A Word document (stdlib only)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / "InfDrawing_interview_qa_two_rounds.docx"

SECTIONS: list[tuple[str, str]] = []


def add(style: str, text: str) -> None:
    """Append a paragraph to the document body."""
    SECTIONS.append((style, text))


add("Title", "InfDrawing 面试对练稿（两轮追问版）")
add(
    "Normal",
    "用途：技术 / 产品面试口述对练。结构固定为「面试官 → 你 → 追问 → 你」。"
    "答案按仓库可运行现状撰写，边界主动说明。",
)
add(
    "Normal",
    "仓库：InfDrawing（Next.js + tldraw 画布 / FastAPI 意图路由 / ComfyUI 与云端执行）。"
    "核心验证单元：素材库（Search）与多轮可控编辑（Edit）。",
)
add("Normal", "生成说明：本文档由会话整理导出，便于单独打印对练或粘贴进作业 Word。")

add("Heading1", "0. 开场：项目一句话与边界")
add("QA_Q", "面试官：用一分钟介绍 InfDrawing 是什么，你解决了什么问题？")
add(
    "QA_A",
    "你：InfDrawing 是一个类似 Lovart 的 AI 创意画布 demo。交互层是 Next.js + tldraw "
    "无限画布；中控是 FastAPI 意图路由；执行层是 ComfyUI 或云端改图。我真正卡住、也做成"
    "验证单元的是两件事：生成后素材找不到（Search），以及多轮改图后角色漂掉且回不去"
    "中间态（Edit）。所以做了素材库和带验收的多轮可控编辑。生图、拆解、inpaint 是底座，"
    "不是这次作业的核心卖点。",
)
add("QA_F", "追问：那和「接几个生图 API 的聊天机器人」差在哪？")
add(
    "QA_FA",
    "你：差在三样必须留下的生产物——结构化资产记录、带验收分数的版本节点、可从中间分叉"
    "的历史。约束是叠层的：提示词 preserve 列表、锁定时裁的参考图、几何构图检查、VLM "
    "质检；任何一层单独都不够。早期只靠提示词时，镜头会逐轮推近、表情会漂。",
)

add("Heading1", "1. 总体架构：为什么是三层")
add("QA_Q", "面试官：为什么拆成交互 / 中控 / 执行三层，而不是前端直接调模型？")
add(
    "QA_A",
    "你：职责不同、失败模式不同、替换成本也不同。画布管空间与图层，不应嵌生图逻辑；"
    "意图识别要结构化校验和兜底，适合放后端；执行器（Comfy / OpenAI / 万相）要能热换。"
    "前端只认「能力开关 + 任务进度 + 贴回画布」。",
)
add("QA_F", "追问：中控层看起来只是个 router，有必要单独一层吗？")
add(
    "QA_FA",
    "你：有。plan_intent 不只是分类：有 TOOL_REGISTRY 一致性、capabilities 门禁、缺 "
    "image_id / mask_id / bbox 时的 clarification、confidence 阈值。LLM 挂了走关键词"
    "确定性路由；用户点模式芯片时走 intent_override。没有这一层，前端会散落一堆 "
    "if-else，本地/云切换也会撕开。",
)

add("Heading1", "2. 画布：为什么用 tldraw")
add("QA_Q", "面试官：无限画布为什么选 tldraw，不自己写？")
add(
    "QA_A",
    "你：缩放、平移、page↔screen、图片 shape、本地 persistence 都是非 trivial。"
    "阶段一目标是可演示 demo，自研坐标系性价比低。我们用 @tldraw/tldraw，业务经 "
    "canvas-bridge 单例桥接 Editor：取选中图、贴结果、拿选区锚点。Mask、AI 右键菜单、"
    "浮窗是自研叠在上面的。",
)
add("QA_F", "追问：tldraw 的图层模型和你们「拆解多层 / 入库取顶层」怎么对齐？")
add(
    "QA_FA",
    "你：我们没有自研图层系统，「图层」就是 tldraw 的 image shapes + z-index。"
    "拆解后前景背景常同时 selected；入库时按 z-index 取最上层，避免把背景标签写到"
    "角色 PNG 上。这是真实踩过的坑：看起来像静默失败，其实选中了错误那张。",
)

add("Heading1", "3. 交互设计：入口怎么分")
add("QA_Q", "面试官：右键、侧栏聊天、多轮编辑浮窗，职责怎么划分？")
add(
    "QA_A",
    "你：右键是就地操作——生图、拆解、入库，贴在内容上。侧栏是自然语言 + 模式覆盖 + "
    "能力状态 + 打开工具入口。多轮编辑 / 素材库是可拖浮窗，不跳页；/studio 重定向到"
    "首页坞。首页是「一个工作台」，不是多页面后台。",
)
add("QA_F", "追问：浮窗和 tldraw 自带 UI 冲突过吗？怎么处理？")
add(
    "QA_FA",
    "你：处理过 z-index。FloatingPanel 约 500，DraggableWindow 约 600，刻意低于 "
    "tldraw blocking overlay（约 10000），否则拖窗会被挡住或点不到。侧栏收起成「AI」"
    "胶囊，也是为了避开 StylePanel。",
)

add("Heading1", "4. 意图路由：LLM + 确定性兜底")
add("QA_Q", "面试官：意图识别具体怎么实现？失败怎么办？")
add(
    "QA_A",
    "你：POST /agent/plan → plan_intent：（1）有 intent_override 直接确定性计划；"
    "（2）否则 LLM（DeepSeek/OpenAI/Ollama）按 schema 吐 IntentPlan；（3）ProviderError "
    "时关键词路由（「拆」「蒙版」「改图」等）；（4）validate_plan 查工具表、能力、"
    "上下文，缺参则 clarification_required。意图集合：txt2img / inpaint / image_edit / "
    "decompose / text_edit。",
)
add("QA_F", "追问：关键词兜底会不会误路由？confidence 低怎么处理？")
add(
    "QA_FA",
    "你：会，所以兜底 confidence 刻意压到约 0.55，且低于阈值阈值时强制澄清，不直接执行。"
    "演示场景里用户常点模式芯片（override），那条路径 confidence=1.0。生产上 durable "
    "路径还有 agent_route job，但本机 demo 多用同步 generate。",
)

add("Heading1", "5. 执行层：本地与云怎么切")
add("QA_Q", "面试官：生图和改图本地/云怎么选？")
add(
    "QA_A",
    "你：Capabilities 探测 Comfy、GPU、各 API key。前端可记引擎偏好 auto/local/cloud。"
    "Orchestrator 按 intent + backend 分支：本地 Comfy 工作流 JSON（txt2img/inpaint）；"
    "云端 OpenAI Images / 万相。image_edit 走 instruction-edit；拆解优先千问分层，"
    "失败 rembg + Comfy 补背景。",
)
add("QA_F", "追问：为什么不把所有编辑都丢给一个最强模型？")
add(
    "QA_FA",
    "你：因为失败模式不同。整图指令适合换背景/发型，但小物件（剑、盾）容易连带改脸；"
    "万相 mask（白改黑留）对中等色块有效，但对细金线几乎无效，也不能带锁定参考图。"
    "所以路由是：小 character.* 且面积 ≤25% 走 mask；背景/整主体/大框走整图 + 脸部 "
    "crop 锚定。",
)

add("Heading1", "6. Inpaint Mask：前端怎么做")
add("QA_Q", "面试官：局部重绘的 mask 怎么从画布到后端？")
add(
    "QA_A",
    "你：MaskTool 用固定尺寸双 canvas：底图 + 笔刷层，刷白为可改区域，导出 PNG 作为 "
    "mask_id 上下文。坐标通过选中图片的 page bounds 映射。侧栏 inpaint flow 要求已有"
    "图和 mask，否则路由会要 clarification。",
)
add("QA_F", "追问：和多轮编辑里的「自动 mask」是一回事吗？")
add(
    "QA_FA",
    "你：不是。画布 inpaint 是用户手刷；cedit 的 mask 由实体 bbox 自动生成 RGB mask"
    "（白目标、黑保留），只服务小物件万相路径。早期还试过 crop-edit-paste，因背景"
    "误判留下矩形残影已取消。",
)

add("Heading1", "7. 多轮编辑：核心管线（必考）")
add("QA_Q", "面试官：多轮可控编辑一轮完整走什么？")
add(
    "QA_A",
    "你：固定顺序——（1）意图解析（同步）：操作类型 + target_entity_ids；锁冲突立即 "
    "409；（2）建 pending 子节点，后台跑 preparing → generating → verifying → "
    "parsing；（3）letterbox 到支持尺寸，生成后再 restore；（4）编译 prompt"
    "（preserve / target_only）+ 锁定锚点参考图；（5）生成（整图或 wanx mask）；可选 "
    "lock paste（默认关）；（6）构图几何检查（主体中心偏移 / 面积变化阈值）；"
    "（7）VLM 验收；失败带原因重试（默认 1 次）；（8）增量重解析实体，写入版本树。"
    "前端约 2s 轮询 session tree。",
)
add("QA_F", "追问：为什么「Preserve 列表不让 LLM 决定」？")
add(
    "QA_FA",
    "你：保护是产品语义，不能交给同一轮里的创作模型自由发挥。实体有 locked / "
    "approved / editable 三态，程序确定性生成「必须保留 / 尽量不变」。锁定时裁 "
    "anchor crop；验收时锁定实体有效分 = min(相对上一帧, 相对锚点)。指令打到锁实体"
    "或其子孙 → lock_conflict，UI 可解锁重试。",
)

add("Heading1", "8. 实体锁定与级联")
add("QA_Q", "面试官：锁父节点和锁子节点有什么区别？")
add(
    "QA_A",
    "你：锁父会级联锁所有后代；只有用户点击的那个节点裁 anchor，子节点显示 locked "
    "但无独立参考图，且父锁时子不能单独解锁。这样「锁角色」= 整棵身份树受保护，"
    "同时避免每个子节点都裁一张参考图撑爆多图上限（默认最多 4 张参考）。",
)
add("QA_F", "追问：新图重解析后，锁定实体丢了怎么办？手动改过的框呢？")
add(
    "QA_FA",
    "你：merge_entities 按 id 继承 status/anchor；锁定且 bbox_source=manual 的保留"
    "手改框；若锁定实体在新图未被识别，整条保留并 warning，绝不静默丢锁。这是防"
    "身份保护被解析噪声冲掉。",
)

add("Heading1", "9. 为什么定位用 Qwen、验收用 GPT")
add("QA_Q", "面试官：模型怎么分工？为什么不一个模型打天下？")
add(
    "QA_A",
    "你：对照实验——同一骑士图上 gpt-4o 的脸/剑/盾框明显偏；qwen3-vl-plus 等框落得"
    "更准，约 14 实体、约 22 秒。所以 grounding 默认 Qwen（xyxy_1000）；意图与验收"
    "仍用 OpenAI 视觉。改图默认 qwen-image-edit-plus。作者和考官分开，避免同一套"
    "权重自评。",
)
add("QA_F", "追问：验收你自己说偏松，怎么补的？还有哪些检不出？")
add(
    "QA_FA",
    "你：加了主体框几何门槛：中心偏移超约 0.08 或面积变化超约 0.15，在 VLM 之前直接"
    "失败——专门抓「逐轮推近」。仍检不出的是渐进纹理变脏；长链要靠从较早节点分支，"
    "而不是在脏图上继续叠。分组框（整个 character）仍偏大，点选局部时主要靠 face / "
    "sword / shield 这类紧框。",
)

add("Heading1", "10. 版本树：为什么是树不是线性 undo")
add("QA_Q", "面试官：为什么要版本树？")
add(
    "QA_A",
    "你：创意编辑是探索：同一根上走出装备线与外观/场景线。每个节点存图、指令、"
    "intent、compiled prompt、参考、实体快照、验收、重试与 warnings。Checkout 只移"
    "指针；从任意节点再 edit 即分支；删节点会删子树，禁删根与 busy。双分支骑士六轮"
    "实验可复现，重启后 data/cedit/ 仍在。",
)
add("QA_F", "追问：失败的节点怎么处理？会不会丢掉用户可见结果？")
add(
    "QA_FA",
    "你：最后一次仍失败时，图仍保存，节点带 warning，让人决定留还是回退——比静默丢"
    "结果友好。Turn 在 API 进程内跑，进程重启会打断进行中的 turn；树与 artifact "
    "元数据已落盘。这是原型边界，生产应迁到 worker。",
)

add("Heading1", "11. 失败假设：你改过什么错设计")
add("QA_Q", "面试官：实现里推翻过哪些假设？")
add(
    "QA_A",
    "你：四个。（1）crop-edit-paste 保周边 → 大背景误判局部，骑士角上矩形残影 → "
    "生成侧统一整图，硬贴回默认关。（2）gpt-4o 兼定位+验收 → 框粗且构图打满分 → "
    "定位换 Qwen，加几何检查。（3）拆解后「当前选中」直接入库 → 多选+面板不刷新像"
    "失败 → 取顶层 + 广播刷新。（4）万相 mask 通吃局部 → 细金线无效、无身份参考 → "
    "mask 仅小物件，身份走整图+脸 crop。",
)
add("QA_F", "追问：硬贴回为什么默认关而不是修算法？")
add(
    "QA_FA",
    "你：误贴的视觉代价高（矩形残影），正确贴的收益在「语义锁 + 参考图 + 验收」路径上"
    "已大部分覆盖。用 INFD_CEDIT_LOCK_PASTE 开关，只在有锚点的锁定框上 feather "
    "paste，默认 false 是风险偏好：宁可偶发语义漂，也不要明显几何伤疤。",
)

add("Heading1", "12. 素材库：为什么不做向量检索")
add("QA_Q", "面试官：素材库怎么做的？为什么不用 embedding？")
add(
    "QA_A",
    "你：选中图导出 PNG → Artifact → VLM 填闭合字段（类型/视角/题材/背景/姿态 + "
    "主色/材质）拼 search_blob → 子串/分词检索 → 贴回。闭合词表前后端对齐，非法值"
    "归一。标注失败仍存图（caption_failed）。不做 embedding，是为了把「标注字段是否"
    "可检索」和「向量召回好不好」拆开验证——游戏资产问法（全身/奇幻/女剑士）打闭合"
    "字段就够演示。",
)
add("QA_F", "追问：去重怎么做？和多用户权限呢？")
add(
    "QA_FA",
    "你：owner 范围内内容 SHA-256 去重，冲突 409，可 force。明确未做：形状搜、向量库、"
    "质量 QC、多人权限。索引在 data/assets/library.json，是作者本机原型，不是资产"
    "中台。下一步若做，会在拆解前景上加轮廓描述或轻量 embedding，解决「侧向持剑」"
    "这类构图检索。",
)

add("Heading1", "13. 鉴权与能力门禁")
add("QA_Q", "面试官：安全和多租户做到什么程度？")
add(
    "QA_A",
    "你：X-API-Key（infd_{locator}_{secret}），HMAC + pepper，按 scope（agent、"
    "generate、controlled_edit、assets…）和 owner 隔离 jobs/artifacts/sessions。"
    "前端 sessionStorage 存 key；任务事件经 Next 同源代理注入。无完整账号体系。"
    "Capabilities 把缺 key/缺引擎的功能在 UI 灰掉。阶段一原型不以安全为约束，但生产"
    "文档有 threat model。",
)
add("QA_F", "追问：浏览器里的 key 泄露怎么办？")
add(
    "QA_FA",
    "你：Demo 风险如实承认：sessionStorage 防不了 XSS。生产应短 TTL、按 scope 最小"
    "权限、经 BFF 注入、HTTPS + CSP。当前价值是「接口层已有 owner 隔离与 scope」，"
    "不是「前端密钥方案已完备」。",
)

add("Heading1", "14. 生产化双轨")
add("QA_Q", "面试官：Demo 和生产路径怎么共存？")
add(
    "QA_A",
    "你：Demo 是进程内 TaskState + WS/SSE，generate 同步编排。Production 是 Postgres "
    "jobs、Redis/arq（api/gpu 队列）、S3/MinIO artifacts、lease/幂等、Nginx、可选 "
    "Prometheus。Compose 已写；真实 GPU 容器联调仍待目标主机验证。Cedit turn 目前仍"
    "偏进程内，是已知差距。",
)
add("QA_F", "追问：为什么不一开始就全上 durable jobs？")
add(
    "QA_FA",
    "你：阶段一要先打通可录屏路径。Jobs 状态机、lease、worker 并发会拉长反馈环。"
    "架构上预留了 agent_route 与四类图像 handler，等交互稳定再迁——符合「先能跑通、"
    "再加深约束」。",
)

add("Heading1", "15. 工程协作与质量")
add("QA_Q", "面试官：你怎么保证这种多模块项目不失控？")
add(
    "QA_A",
    "你：.planning/ 先规划后批准再写代码；Agent 规则同步；后端 pytest 镜像目录；"
    "关键路径有 e2e/对照脚本（cedit_e2e、grounding compare、mask 对照）。语言约定："
    "对用户中文、代码注释英文、commit 英文。Python 固定 3.11 venv。",
)
add("QA_F", "追问：测试策略的边界？")
add(
    "QA_FA",
    "你：路由校验、实体 merge/lock、region_ops、caption 解析、API schema 有单测；"
    "真实模型效果靠对照实验落 data/logs/，不装成「单测保证画质」。面试里我会主动说："
    "画质与定位是实验结论，不是 CI 绿灯。",
)

add("Heading1", "16. 产品取舍（设计师向）")
add("QA_Q", "面试官：若只能保留一个模块给投资人看，留哪个？")
add(
    "QA_A",
    "你：留多轮编辑 + 版本树。它同时展示：结构化场景理解、约束生成、自动验收、可回退"
    "探索——最像「可控创作工具」而不像聊天套皮。素材库是 Search 闭环，演示短、好懂，"
    "适合开场 30 秒，但差异化深度不如 cedit。",
)
add("QA_F", "追问：若用户根本不想看实体树，只要「聊天改图」？")
add(
    "QA_FA",
    "你：可以默认收起实体面板，只暴露「锁脸」一键和对话；树与验收仍在背后跑。产品上"
    "我不会删树——那是失败时的恢复面。UI 可以渐进披露，领域模型不能退化成纯线性 "
    "chat。",
)

add("Heading1", "17. 压力题：最怕被问穿的点")
add("QA_Q", "面试官：这个系统现在最不诚实的地方在哪？")
add(
    "QA_A",
    "你：三点主动说。（1）VLM 验收对纹理退化不敏感，分数好看不等于越改越干净；"
    "（2）public main 若未推送，GitHub 和本机 demo 可能不一致——以可运行工作区为准；"
    "（3）单机 JSON 持久化不是多人生产库。我证明的是：锁定脸后双分支改装备/场景，"
    "脸分 0.8–1.0、树可重启恢复；以及拆解前景可入库检索贴回。不是「已解决 AIGC "
    "生产审核」。",
)
add("QA_F", "追问：那你下一步最小的一步是什么？")
add(
    "QA_FA",
    "你：两条小步——素材侧给拆解前景加轮廓/轻量 embedding；验收侧加分辨率或噪声指标"
    "抓长链变脏。都不改已跑通主路径。",
)

add("Heading1", "附录 A. 速记卡片（上场前 30 秒）")
add("Normal", "架构：画布皮囊 / 意图中控 / 可换执行器。")
add("Normal", "Agent：LLM 结构化计划 + 关键词兜底 + 缺参澄清。")
add("Normal", "Cedit：语义锁 + 确定性 preserve + 几何门槛 + VLM + 版本树。")
add("Normal", "路由改图：小物件 mask，大改整图 + 脸参考。")
add("Normal", "素材库：VLM 闭合字段 + 子串检索，无向量是刻意。")
add("Normal", "踩坑：crop 残影、框偏、多选入库、细线 mask 无效。")
add("Normal", "边界：验收偏松、纹理脏靠分支、单机原型。")

add("Heading1", "附录 B. 代码与文档索引")
add("Normal", "首页组装：frontend/src/app/HomeWorkspace.tsx")
add("Normal", "画布与桥接：frontend/src/canvas/、frontend/src/lib/canvas-bridge.ts")
add("Normal", "Agent UI：frontend/src/agent-panel/")
add("Normal", "多轮编辑 UI：frontend/src/studio/")
add("Normal", "素材库 UI：frontend/src/library/")
add("Normal", "意图路由：backend/app/agent/router.py")
add("Normal", "图像管线：backend/app/pipeline/")
add("Normal", "可控编辑：backend/app/controlled_edit/（文档 docs/controlled_edit.md）")
add("Normal", "素材库后端：backend/app/assets/")
add("Normal", "生产化：backend/app/production/、compose.production.yaml")
add("Normal", "面试事实卡：docs/submission/materials/06_面试事实卡.md")


def p_run(
    text: str,
    *,
    bold: bool = False,
    color: str | None = None,
    size: int | None = None,
) -> str:
    """Build a single Word run."""
    rpr: list[str] = [
        '<w:rFonts w:ascii="Microsoft YaHei" w:hAnsi="Microsoft YaHei" '
        'w:eastAsia="Microsoft YaHei"/>'
    ]
    if bold:
        rpr.append("<w:b/>")
    if color:
        rpr.append(f'<w:color w:val="{color}"/>')
    if size is not None:
        rpr.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    rpr_xml = f"<w:rPr>{''.join(rpr)}</w:rPr>"
    return f'<w:r>{rpr_xml}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def paragraph(style: str, text: str) -> str:
    """Build a Word paragraph for a logical style."""
    if style == "Title":
        ppr = (
            '<w:pPr><w:spacing w:before="0" w:after="240"/>'
            '<w:jc w:val="center"/></w:pPr>'
        )
        return f"<w:p>{ppr}{p_run(text, bold=True, size=36)}</w:p>"
    if style == "Heading1":
        ppr = (
            '<w:pPr><w:spacing w:before="360" w:after="120"/>'
            '<w:outlineLvl w:val="0"/></w:pPr>'
        )
        return f"<w:p>{ppr}{p_run(text, bold=True, size=28, color='1F4E79')}</w:p>"
    if style == "QA_Q":
        ppr = (
            '<w:pPr><w:spacing w:before="160" w:after="60"/>'
            '<w:shd w:val="clear" w:color="auto" w:fill="FFF2CC"/></w:pPr>'
        )
        return f"<w:p>{ppr}{p_run(text, bold=True, size=22)}</w:p>"
    if style == "QA_A":
        ppr = (
            '<w:pPr><w:spacing w:before="40" w:after="80"/>'
            '<w:ind w:left="200"/></w:pPr>'
        )
        return f"<w:p>{ppr}{p_run(text, size=21)}</w:p>"
    if style == "QA_F":
        ppr = (
            '<w:pPr><w:spacing w:before="80" w:after="60"/>'
            '<w:shd w:val="clear" w:color="auto" w:fill="DEEBF7"/></w:pPr>'
        )
        return f"<w:p>{ppr}{p_run(text, bold=True, size=21, color='2F5496')}</w:p>"
    if style == "QA_FA":
        ppr = (
            '<w:pPr><w:spacing w:before="40" w:after="160"/>'
            '<w:ind w:left="200"/></w:pPr>'
        )
        return f"<w:p>{ppr}{p_run(text, size=21)}</w:p>"
    ppr = '<w:pPr><w:spacing w:before="60" w:after="60"/></w:pPr>'
    return f"<w:p>{ppr}{p_run(text, size=21)}</w:p>"


def main() -> None:
    """Write the .docx package."""
    body_paras = "\n".join(paragraph(s, t) for s, t in SECTIONS)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body_paras}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"
               w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:rPr>
      <w:rFonts w:ascii="Microsoft YaHei" w:hAnsi="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/>
      <w:sz w:val="21"/>
    </w:rPr>
  </w:style>
</w:styles>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml.encode("utf-8"))
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("word/styles.xml", styles_xml)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, {len(SECTIONS)} paragraphs)")


if __name__ == "__main__":
    main()
