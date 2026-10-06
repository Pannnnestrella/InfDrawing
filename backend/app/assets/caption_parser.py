"""Ask a vision model to label an image for library search."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import ValidationError

from app.assets.schemas import CaptionDraft

CAPTION_SYSTEM_PROMPT = """\
You catalog a single image for a game art asset library so it can be found later.

Write title, objects, tags, description, style, palette, and materials in \
Simplified Chinese. Closed-set fields must use the English codes listed below.

Rules:
- title: 2–12 characters naming the main subject.
- objects: concrete things visible (people, props, places).
- tags: searchable labels (genre, medium, mood).
- description: 1–3 sentences covering what is in the picture.
- style: 1–2 sentences on medium, lighting, composition, and color.
- asset_type: one of character, creature, weapon, armor, prop, item, \
environment, architecture, vehicle, ui, icon, vfx, concept, other.
- view: one of full_body, bust, face, three_quarter, side, back, isometric, \
top_down, close_up, scene, other.
- genre: one of fantasy, scifi, modern, historical, eastern, horror, anime, other.
- background: one of environment, studio, transparent, solid, sky, other.
- pose: one of standing, action, idle, sitting, flying, none, other. Use none \
for weapons, props, UI, and scenes without a posed figure.
- palette: 2–6 dominant color names in Chinese.
- materials: visible materials in Chinese (金属, 布料, 皮革, 石头, 木头, 皮肤…).

Reply with JSON only:
{"title":"...","objects":["..."],"tags":["..."],"description":"...",\
"style":"...","asset_type":"character","view":"full_body","genre":"fantasy",\
"background":"environment","pose":"standing","palette":["..."],"materials":["..."]}"""

CAPTION_USER_TEXT = "Catalog this image for a game asset library."


class JsonVisionModel(Protocol):
    """Anything that can answer a prompt (plus images) with a JSON object."""

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_text: str,
        images: list[bytes] | None = None,
    ) -> dict[str, Any]: ...


class CaptionParseError(ValueError):
    """Raised when the VLM output cannot be turned into a caption."""


async def parse_caption(model: JsonVisionModel, image_bytes: bytes) -> CaptionDraft:
    """Ask the VLM to caption ``image_bytes``.

    Args:
        model: Vision model client.
        image_bytes: Image to catalog.

    Returns:
        Validated caption fields.

    Raises:
        CaptionParseError: If the reply is structurally invalid.
    """
    reply = await model.complete_json(
        system_prompt=CAPTION_SYSTEM_PROMPT,
        user_text=CAPTION_USER_TEXT,
        images=[image_bytes],
    )
    return caption_from_reply(reply)


def caption_from_reply(reply: dict[str, Any]) -> CaptionDraft:
    """Validate a raw VLM reply into a caption draft.

    Args:
        reply: JSON object from the vision model.

    Returns:
        CaptionDraft with trimmed lists and strings.

    Raises:
        CaptionParseError: If required structure is missing.
    """
    if not isinstance(reply, dict):
        raise CaptionParseError("caption reply must be a JSON object")
    try:
        draft = CaptionDraft.model_validate(reply)
    except ValidationError as exc:
        raise CaptionParseError(f"caption reply is invalid: {exc}") from exc
    filled = (
        draft.title,
        draft.objects,
        draft.tags,
        draft.description,
        draft.style,
        draft.asset_type,
        draft.view,
        draft.genre,
        draft.background,
        draft.pose,
        draft.palette,
        draft.materials,
    )
    if not any(filled):
        raise CaptionParseError("caption reply is empty")
    return draft
