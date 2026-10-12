"""Prompt templates for Qwen multi-image edits that may preserve or emit alpha."""

from __future__ import annotations


def wants_transparency(instruction: str, *, parent_has_alpha: bool) -> bool:
    """Detect cutout / keep-alpha intent from the user text or parent PNG."""
    if parent_has_alpha:
        return True
    text = instruction.lower()
    keys = (
        "透明",
        "抠图",
        "去背",
        "去背景",
        "alpha",
        "transparent",
        "png素材",
        "透明通道",
        "transparent png",
    )
    return any(key in instruction or key in text for key in keys)


def qwen_fullframe_alpha_clause(*, allow_alpha: bool) -> str:
    """Appended to compiled full-frame prompts when alpha handling matters."""
    if allow_alpha:
        return (
            " If the source has a transparent background, keep a transparent PNG alpha "
            "channel; do not fill the background with a solid color. "
            "若原图或目标需要透明底，输出带透明通道的 PNG，不要铺纯色背景。"
        )
    return (
        " Output a complete opaque RGB scene matching the source framing; "
        "do not return a cutout or transparent matte. "
        "输出完整不透明场景，不要抠图或透明底。"
    )


def qwen_mask_edit_prompt(instruction: str, *, allow_alpha: bool = True) -> str:
    """Dual-image rough-mask prompt for Qwen 2.1+ (guide + clean primary).

    Image1 is a same-scene guide with a rough edit wash; image2 is the clean parent
    (primary last). When ``allow_alpha`` is True, transparent PNG output is allowed.
    """
    alpha_rule = (
        "若遮罩内需要去掉背景或原图本身透明，允许输出带透明通道的 PNG；"
        "透明区域应干净、边缘锐利，不要发光或过度羽化。"
        if allow_alpha
        else (
            "输出完整不透明的图二同构图 RGB 成品；"
            "不要透明通道、不要抠图、不要纯色背景、不要只输出素材层。"
        )
    )
    return (
        "图一和图二是同一张图。"
        "图一在需要修改的区域上画了潦草遮罩（遮罩偏大、边缘不精确）；"
        "图二是干净原图，用于对照风格、材质、边缘与光照。"
        "请根据图一的遮罩范围，在图二上完成编辑："
        f"{instruction}"
        "遮罩可能比真实目标略大，请结合图二内容收缩到物体本身，并对保留区域边缘按图二修补，"
        "边缘清晰锐利，不要发光、不要过度羽化。"
        "未遮罩区域必须与图二保持一致；遮罩内可见内容均取自图二的风格与光照，禁止自行创造无关物体。"
        f"{alpha_rule}"
    )
