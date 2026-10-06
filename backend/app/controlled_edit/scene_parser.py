"""VLM scene parsing into a two-level entity tree."""

from __future__ import annotations

import io
import json
from typing import Any, Protocol

from PIL import Image
from pydantic import ValidationError

from app.controlled_edit.schemas import BBox, SceneEntity


class JsonVisionModel(Protocol):
    """Anything that can answer a prompt (plus images) with a JSON object."""

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_text: str,
        images: list[bytes] | None = None,
    ) -> dict[str, Any]: ...


class SceneParseError(ValueError):
    """Raised when the VLM output cannot be turned into a valid entity list."""


SCENE_SYSTEM_PROMPT = """\
You are a scene parser for an image editing tool. List the visually distinct, \
editable elements of the image as a two-level tree.

Rules:
- Top-level groups are broad parts such as "character", "character_2", "environment", \
"foreground", "text". Children are concrete parts such as "character.face", \
"character.hair", "character.sword", "environment.sky", "environment.castle".
- Ids are lowercase snake_case segments joined by dots; a child id starts with its \
parent id.
- For every person or creature, always list separate children for the face and the \
hair when visible (e.g. "character.face", "character.hair"), plus held items, \
headwear and main clothing.
- Use short English names; the description states visual traits (color, material, \
style) in one sentence, useful for keeping the element unchanged later.
- box_2d is [x_min, y_min, x_max, y_max] as integers on a 0-1000 grid relative to the \
image width and height; it must tightly enclose the whole element (e.g. the entire \
blade of a sword, not only the hand holding it).
- At most {max_entities} entities in total. Skip tiny or unimportant details.

Reply with JSON only:
{{"entities": [{{"id": "character", "name": "Character", "parent_id": null, \
"description": "...", "box_2d": [300, 100, 700, 950]}}, ...]}}"""

REPARSE_INSTRUCTIONS = """\
This image is a new version of an image that was previously parsed into the \
entities below. Reuse the same id for every element that is still present (even if \
it moved or changed slightly), add new ids for new elements, and omit elements that \
no longer exist.

Previous entities:
{previous}"""


async def parse_scene(
    model: JsonVisionModel,
    image_bytes: bytes,
    *,
    previous: list[SceneEntity] | None = None,
    max_entities: int = 30,
    box_format: str = "xyxy_1000",
) -> list[SceneEntity]:
    """Ask the VLM for the scene entity tree of ``image_bytes``.

    Args:
        model: Vision model client.
        image_bytes: Image to parse.
        previous: Entities of the parent version; when given, ids are reused.
        max_entities: Upper bound on returned entities.
        box_format: How ``box_2d`` values are interpreted.

    Returns:
        Validated entities with default (editable) status.

    Raises:
        SceneParseError: If the reply is structurally invalid.
    """
    user_text = "Parse this image."
    if previous:
        summary = [
            {"id": e.id, "name": e.name, "description": e.description} for e in previous
        ]
        user_text = REPARSE_INSTRUCTIONS.format(
            previous=json.dumps(summary, ensure_ascii=False, indent=1)
        )
    reply = await model.complete_json(
        system_prompt=SCENE_SYSTEM_PROMPT.format(max_entities=max_entities),
        user_text=user_text,
        images=[image_bytes],
    )
    return entities_from_reply(
        reply,
        max_entities=max_entities,
        box_format=box_format,
        image_size=_image_size(image_bytes),
    )


def entities_from_reply(
    reply: dict[str, Any],
    *,
    max_entities: int = 30,
    box_format: str = "xyxy_1000",
    image_size: tuple[int, int] | None = None,
) -> list[SceneEntity]:
    """Validate a raw VLM reply into entities.

    Raises:
        SceneParseError: With the offending entity index or id in the message.
    """
    raw_entities = reply.get("entities")
    if not isinstance(raw_entities, list) or not raw_entities:
        raise SceneParseError("scene reply must contain a non-empty 'entities' list")
    entities: list[SceneEntity] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_entities[:max_entities]):
        if not isinstance(raw, dict):
            raise SceneParseError(f"entity #{index} is not an object")
        label = raw.get("id", f"#{index}")
        try:
            entity = SceneEntity(
                id=raw.get("id"),
                name=raw.get("name") or raw.get("id"),
                parent_id=raw.get("parent_id") or None,
                description=str(raw.get("description") or "")[:400],
                bbox=_parse_box_2d(raw["box_2d"], box_format, image_size)
                if raw.get("box_2d") is not None
                else _parse_bbox(raw.get("bbox")),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise SceneParseError(f"entity {label!r} is invalid: {exc}") from exc
        if entity.id in seen:
            raise SceneParseError(f"duplicate entity id {entity.id!r}")
        seen.add(entity.id)
        entities.append(entity)
    return [
        e
        if e.parent_id is None or e.parent_id in seen
        else e.model_copy(update={"parent_id": None})
        for e in entities
    ]


def _image_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(image_bytes)) as image:
        return image.size


def _parse_box_2d(
    raw: Any,
    box_format: str = "xyxy_1000",
    image_size: tuple[int, int] | None = None,
) -> BBox:
    """Convert a model's ``box_2d`` list into a normalized BBox."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise ValueError("box_2d must be a list of four numbers")
    a, b, c, d = (float(v) for v in raw)
    if box_format == "xyxy_1000":
        x0, y0, x1, y1 = a / 1000, b / 1000, c / 1000, d / 1000
    elif box_format == "yxyx_1000":
        y0, x0, y1, x1 = a / 1000, b / 1000, c / 1000, d / 1000
    elif box_format == "xyxy_pixel":
        if image_size is None:
            raise ValueError("xyxy_pixel boxes need the image size")
        width, height = image_size
        if width <= 0 or height <= 0:
            raise ValueError("image size must be positive")
        x0, y0, x1, y1 = a / width, b / height, c / width, d / height
    else:
        raise ValueError(f"unknown box format: {box_format}")
    return BBox(x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def _parse_bbox(raw: Any) -> BBox | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return BBox(**raw)
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise ValueError("bbox must be [x, y, w, h]")
    x, y, w, h = (float(v) for v in raw)
    return BBox(x=x, y=y, w=w, h=h)
