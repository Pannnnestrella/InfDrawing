"""Compose submission figures from real experiment artifacts and simple diagrams."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"D:\Desktop\Fan_Files\Codes\infDrawing")
ART = ROOT / "data" / "artifacts" / "artifacts"
OUT = ROOT / "docs" / "submission" / "materials" / "figures"
FONT_REG = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BD = Path(r"C:\Windows\Fonts\msyhbd.ttc")

PAPER = (247, 245, 240)
INK = (28, 25, 23)
MUTED = (92, 84, 76)
LINE = (214, 206, 195)
ACCENT = (61, 90, 128)
ACCENT2 = (196, 92, 38)
GREEN = (47, 122, 88)
WHITE = (255, 255, 255)

IDS = {
    "root": "56b8e2df-b36a-49c8-8f9c-3c30ce78ef25",
    "a1": "804d801f-6afe-4170-9246-1780475c0fd0",
    "a2": "ce681b9e-cdd7-4027-91a8-567e0cb0ac88",
    "a3": "b1faa28c-d735-40b0-87ee-95169d4a64c2",
    "b1": "10bbdefd-fe88-4358-9b1a-7853018d28ce",
    "b2": "c9ff1966-6c46-44bc-896b-2ac4500c6be3",
    "b3": "82416c4d-3b3e-4d0c-b8d2-68afb24594e4",
    "face": "dcb2c00c-542f-4cde-9727-7797554e1e33",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BD if bold and FONT_BD.exists() else FONT_REG
    return ImageFont.truetype(str(path), size=size, index=0)


def load_art(key: str) -> Image.Image:
    return Image.open(ART / f"{IDS[key]}.png").convert("RGBA")


def fit(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA")
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (236, 232, 224, 255))
    x = (size - img.width) // 2
    y = (size - img.height) // 2
    canvas.paste(img, (x, y), img)
    return canvas


def labeled_tile(img: Image.Image, title: str, sub: str, size: int = 420) -> Image.Image:
    thumb = fit(img, size)
    h = size + 72
    card = Image.new("RGB", (size, h), PAPER)
    card.paste(thumb.convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, size, size, h), fill=WHITE)
    draw.line((0, size, size, size), fill=LINE, width=1)
    draw.text((12, size + 10), title, font=font(18, True), fill=INK)
    draw.text((12, size + 38), sub, font=font(14), fill=MUTED)
    return card


def hstack(cards: list[Image.Image], gap: int = 16, pad: int = 28, title: str = "") -> Image.Image:
    title_h = 56 if title else 0
    w = pad * 2 + sum(c.width for c in cards) + gap * (len(cards) - 1)
    h = pad * 2 + max(c.height for c in cards) + title_h
    sheet = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(sheet)
    if title:
        draw.text((pad, 16), title, font=font(24, True), fill=INK)
    x = pad
    y = pad + title_h
    for card in cards:
        sheet.paste(card, (x, y))
        x += card.width + gap
    return sheet


def vstack(rows: list[Image.Image], gap: int = 18, pad: int = 24) -> Image.Image:
    w = max(r.width for r in rows) + pad * 2
    h = pad * 2 + sum(r.height for r in rows) + gap * (len(rows) - 1)
    sheet = Image.new("RGB", (w, h), PAPER)
    y = pad
    for row in rows:
        x = (w - row.width) // 2
        sheet.paste(row, (x, y))
        y += row.height + gap
    return sheet


def save(img: Image.Image, name: str) -> None:
    path = OUT / name
    img.convert("RGB").save(path, "PNG", optimize=True)
    print(f"wrote {path.name} {img.size}")


def make_two_branch_end() -> None:
    cards = [
        labeled_tile(load_art("root"), "根节点 v1", "锁定面部 · 原始骑士"),
        labeled_tile(load_art("a3"), "A 线终点", "弯刀 + 骷髅盾 + 暗金甲"),
        labeled_tile(load_art("b3"), "B 线终点", "金发 + 羽帽 + 海边悬崖"),
    ]
    save(hstack(cards, title="同一张脸，两条产品线"), "fig11_two_branch_ends.png")


def make_strips() -> None:
    a = [
        labeled_tile(load_art("root"), "A0 根", "银甲 · 长剑 · 蓝盾", 320),
        labeled_tile(load_art("a1"), "A1 换剑", "火焰弯刀", 320),
        labeled_tile(load_art("a2"), "A2 换盾", "骷髅黑铁圆盾", 320),
        labeled_tile(load_art("a3"), "A3 换甲", "暗金哥特板甲", 320),
    ]
    save(hstack(a, title="A 线：只改装备（脸锁定）"), "fig12_branch_a.png")
    b = [
        labeled_tile(load_art("root"), "B0 根", "肩长红发 · 草地城堡", 320),
        labeled_tile(load_art("b1"), "B1 发型", "及腰金色长卷", 320),
        labeled_tile(load_art("b2"), "B2 加帽", "红羽宽檐帽", 320),
        labeled_tile(load_art("b3"), "B3 换背景", "黄昏海边悬崖", 320),
    ]
    save(hstack(b, title="B 线：从根节点另开（发型 / 帽 / 场景）"), "fig13_branch_b.png")


def make_decompose() -> None:
    src = load_art("root")
    fg = Image.open(ROOT / "data/logs/20261006_decompose_cloud/fg.png")
    bg = Image.open(ROOT / "data/logs/20261006_decompose_cloud/bg.png")
    checker = Image.new("RGBA", (420, 420), (236, 232, 224, 255))
    for y in range(0, 420, 16):
        for x in range(0, 420, 16):
            if (x // 16 + y // 16) % 2 == 0:
                ImageDraw.Draw(checker).rectangle((x, y, x + 16, y + 16), fill=(220, 216, 208, 255))
    fg_fit = fg.convert("RGBA")
    fg_fit.thumbnail((420, 420), Image.Resampling.LANCZOS)
    checker.paste(fg_fit, ((420 - fg_fit.width) // 2, (420 - fg_fit.height) // 2), fg_fit)
    cards = [
        labeled_tile(src, "原图", "画布上的整图候选"),
        labeled_tile(checker, "前景层", "拆解得到的角色 PNG"),
        labeled_tile(bg, "背景层", "去掉主体后补全的场景"),
    ]
    save(hstack(cards, title="元素拆解：一条生成结果变成两条可入库资产"), "fig14_decompose_layers.png")


def make_boxes() -> None:
    src = load_art("root").convert("RGB")
    src = src.resize((720, 720), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(src, "RGBA")
    boxes = [
        ("character.sword", 0.08, 0.05, 0.23, 0.53, ACCENT, "left"),
        ("character.shield", 0.59, 0.40, 0.20, 0.295, GREEN, "right"),
        ("character.hair", 0.38, 0.006, 0.21, 0.164, (120, 80, 160), "right"),
        ("character.face", 0.43, 0.03, 0.11, 0.13, ACCENT2, "below"),
    ]
    for name, x, y, w, h, color, place in boxes:
        x0, y0 = int(x * 720), int(y * 720)
        x1, y1 = int((x + w) * 720), int((y + h) * 720)
        draw.rectangle((x0, y0, x1, y1), outline=color + (255,), width=4)
        tw = int(font(16, True).getlength(name)) + 12
        th = 26
        if place == "left":
            lx, ly = max(0, x0 - tw - 4), max(0, y0)
        elif place == "right":
            lx, ly = min(720 - tw, x1 + 4), max(0, y0)
        else:
            lx, ly = x0, min(720 - th, y1 + 4)
        draw.rectangle((lx, ly, lx + tw, ly + th), fill=color + (230,))
        draw.text((lx + 6, ly + 2), name, font=font(16, True), fill=WHITE)
    card = Image.new("RGB", (720 + 56, 720 + 120), PAPER)
    card.paste(src, (28, 64))
    d = ImageDraw.Draw(card)
    d.text((28, 18), "实体定位（Qwen-VL）· 点选即本轮目标", font=font(24, True), fill=INK)
    d.text((28, 800), "脸 / 剑 / 盾框用于锁定与局部改；分组框（整个人物、环境）偏大，演示时不拿来点选。", font=font(15), fill=MUTED)
    save(card, "fig15_entity_boxes.png")


def make_mask_sheet() -> None:
    compare = Image.open(ROOT / "data/logs/20261006_cedit_mask_small/compare.png").convert("RGB")
    compare.thumbnail((1400, 900), Image.Resampling.LANCZOS)
    sheet = Image.new("RGB", (compare.width + 56, compare.height + 100), PAPER)
    d = ImageDraw.Draw(sheet)
    d.text((28, 18), "小物件 mask 三轮：剑→木杖，盾→南瓜，手套金线", font=font(24, True), fill=INK)
    d.text((28, 50), "前两轮改动可见；手套金线过细，几乎无变化，故不作为演示高潮。", font=font(15), fill=MUTED)
    sheet.paste(compare, (28, 80))
    save(sheet, "fig16_mask_small.png")


def make_face_anchor() -> None:
    crop_path = ART / f"{IDS['face']}.png"
    if not crop_path.exists():
        print("skip face crop")
        return
    crop = Image.open(crop_path)
    root = fit(load_art("root"), 420)
    face = fit(crop, 420)
    save(
        hstack(
            [
                labeled_tile(root, "锁定时刻的整图", "character.face → locked"),
                labeled_tile(face, "脸部锚点 crop", "后续每轮作为身份参考图"),
            ],
            title="锁定时裁出脸部参考图，供后续轮次锚定身份",
        ),
        "fig17_face_anchor.png",
    )


def rounded_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill, outline=None, r: int = 16) -> None:
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=2)


def make_pipeline_diagram() -> None:
    w, h = 1480, 520
    im = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    d.text((40, 24), "游戏概念图生产环节，与本次切入点", font=font(26, True), fill=INK)
    steps = [
        ("Search", "检索已有资产", True, "痛点 A 素材失控"),
        ("Create", "草图 / AI 生图", False, "已有工具覆盖"),
        ("Edit", "抠图 / 多轮改图", True, "痛点 B 版本失控"),
        ("Review", "质检 / 验收", False, "本次做成自动验收"),
        ("Adapt", "多尺寸多平台", False, "发行侧，本次不做"),
    ]
    box_w, box_h = 240, 170
    gap = 28
    x0 = 40
    y0 = 160
    for i, (name, desc, core, note) in enumerate(steps):
        x = x0 + i * (box_w + gap)
        fill = (255, 244, 236) if core else WHITE
        outline = ACCENT2 if core else LINE
        rounded_rect(d, (x, y0, x + box_w, y0 + box_h), fill, outline, 18)
        d.text((x + 18, y0 + 18), name, font=font(22, True), fill=ACCENT2 if core else INK)
        d.text((x + 18, y0 + 58), desc, font=font(16), fill=MUTED)
        d.text((x + 18, y0 + 110), note, font=font(15, True), fill=ACCENT2 if core else MUTED)
        if i < len(steps) - 1:
            ax = x + box_w + 4
            d.polygon([(ax, y0 + 80), (ax + 16, y0 + 88), (ax, y0 + 96)], fill=ACCENT)
    d.text((40, 370), "Create 已有大量生图工具。自己做概念图时，工时消耗在出图之后找不到、改完对不上且回不去。", font=font(16), fill=INK)
    d.text((40, 404), "因此原型做两件事：VLM 标注入库（Search），实体锁定 + 修改树（Edit）。Review 只做到自动验收。", font=font(16), fill=INK)
    save(im, "fig18_production_pipeline.png")


def make_arch_diagram() -> None:
    w, h = 1480, 720
    im = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    d.text((40, 24), "两个模块如何接在已有画布上", font=font(26, True), fill=INK)

    def panel(x, y, pw, ph, title, lines, accent=ACCENT):
        rounded_rect(d, (x, y, x + pw, y + ph), WHITE, LINE, 18)
        d.rectangle((x, y, x + 10, y + ph), fill=accent)
        d.text((x + 28, y + 16), title, font=font(20, True), fill=INK)
        yy = y + 56
        for line in lines:
            d.text((x + 28, yy), line, font=font(15), fill=MUTED)
            yy += 28

    panel(40, 90, 430, 280, "无限画布底座", [
        "Next.js + tldraw",
        "生图 / 拆解 / 局部重绘",
        "图层可拖拽缩放",
        "产出：整图、前景、碎片",
    ])
    panel(520, 90, 430, 280, "模块一 素材库", [
        "导出 PNG → Artifact",
        "Qwen-VL 结构化 JSON",
        "闭合词表 + 自由文本",
        "关键词检索，贴回画布",
    ], ACCENT2)
    panel(1000, 90, 440, 280, "模块二 多轮编辑", [
        "实体树 + 三态锁定",
        "整图改图 / 小物件 mask",
        "几何构图检查 + VLM 验收",
        "版本 DAG，可回退可分支",
    ], GREEN)
    panel(40, 410, 1400, 260, "模型分工（生成器与质检分开）", [
        "定位 / 素材标注：qwen3-vl-plus（同一张骑士图上，脸剑盾框明显优于 gpt-4o）",
        "整图改图：qwen-image-edit-plus　　小物件：wanx2.1-imageedit + mask（白改黑留）",
        "意图解析与验收：gpt-4o　　Preserve 列表由程序根据锁定状态生成，不交给语言模型决定",
        "接口：/api/v1/assets/*　　/api/v1/controlled-edit/*",
    ], ACCENT)
    save(im, "fig19_module_architecture.png")


def make_turn_flow() -> None:
    w, h = 1480, 420
    im = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    d.text((40, 22), "一轮编辑的固定顺序", font=font(26, True), fill=INK)
    steps = [
        "意图解析",
        "编译 prompt\n与参考图",
        "生图",
        "构图检查",
        "VLM 验收",
        "重试 / 落盘",
        "写入\n修改树",
    ]
    bw, bh = 170, 120
    y = 160
    for i, name in enumerate(steps):
        x = 36 + i * (bw + 28)
        rounded_rect(d, (x, y, x + bw, y + bh), WHITE, ACCENT, 16)
        d.text((x + 16, y + 36), name, font=font(18, True), fill=INK)
        if i < len(steps) - 1:
            ax = x + bw + 6
            d.polygon([(ax, y + 54), (ax + 14, y + 62), (ax, y + 70)], fill=ACCENT)
    d.text((40, 320), "指令打到已锁定实体 → 409，前端提示先解锁。验收失败则把原因写回 prompt，默认重试 1 次；仍失败也落盘并打警告。", font=font(16), fill=MUTED)
    save(im, "fig20_edit_turn_flow.png")


def make_tree_diagram() -> None:
    w, h = 1480, 620
    im = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    d.text((40, 22), "修改树：回退是切指针，继续编辑即分支", font=font(26, True), fill=INK)

    def node(x, y, text, fill=WHITE, outline=ACCENT):
        rounded_rect(d, (x, y, x + 220, y + 88), fill, outline, 14)
        d.text((x + 16, y + 28), text, font=font(16, True), fill=INK)

    def line(a, b):
        d.line(a + b, fill=ACCENT, width=3)

    node(630, 90, "v1 根\n锁定面部", (255, 244, 236), ACCENT2)
    node(250, 260, "A1 火焰弯刀")
    node(250, 390, "A2 骷髅盾")
    node(250, 520, "A3 暗金甲", (232, 244, 236), GREEN)
    node(1010, 260, "B1 金色长卷")
    node(1010, 390, "B2 红羽帽")
    node(1010, 520, "B3 海边悬崖", (232, 244, 236), GREEN)
    line((740, 178), (360, 260))
    line((360, 348), (360, 390))
    line((360, 478), (360, 520))
    line((740, 178), (1120, 260))
    line((1120, 348), (1120, 390))
    line((1120, 478), (1120, 520))
    d.text((250, 220), "A 装备线", font=font(16, True), fill=GREEN)
    d.text((1010, 220), "B 外观 / 场景线", font=font(16, True), fill=GREEN)
    save(im, "fig21_version_tree.png")


def make_caption_schema() -> None:
    w, h = 1480, 560
    im = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    d.text((40, 22), "入库标注的两层字段", font=font(26, True), fill=INK)
    rounded_rect(d, (40, 90, 710, 500), WHITE, ACCENT, 18)
    d.text((64, 112), "结构标签（闭合词表）", font=font(20, True), fill=ACCENT)
    left = [
        "类型  角色 / 武器 / 场景 / 图标 …",
        "视角  全身 / 半身 / 侧面 / 特写 …",
        "题材  奇幻 / 科幻 / 历史 …",
        "背景  实景 / 透明底 / 纯色底 …",
        "姿态  站立 / 动作 / 无（非角色）",
        "主色、材质",
        "用途：筛选、去重、避免各模型自创标签",
    ]
    yy = 160
    for line in left:
        d.text((64, yy), line, font=font(16), fill=INK)
        yy += 42
    rounded_rect(d, (770, 90, 1440, 500), WHITE, ACCENT2, 18)
    d.text((794, 112), "自由文本（写入 search_blob）", font=font(20, True), fill=ACCENT2)
    right = [
        "标题  2–12 字，如「女剑士」",
        "物体  少女、长剑、盾牌、城堡 …",
        "标签  奇幻、油画、史诗 …",
        "描述  1–3 句画面内容",
        "风格  媒介、光线、构图",
        "用途：自然语言搜索",
        "标注失败仍保存图像，状态 caption_failed",
    ]
    yy = 160
    for line in right:
        d.text((794, yy), line, font=font(16), fill=INK)
        yy += 42
    save(im, "fig22_caption_schema.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_two_branch_end()
    make_strips()
    make_decompose()
    make_boxes()
    make_mask_sheet()
    make_face_anchor()
    make_pipeline_diagram()
    make_arch_diagram()
    make_turn_flow()
    make_tree_diagram()
    make_caption_schema()


if __name__ == "__main__":
    main()
