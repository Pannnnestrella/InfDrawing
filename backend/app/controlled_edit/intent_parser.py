"""LLM parsing of an edit instruction into a structured intent."""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.controlled_edit.entities import known_target_ids
from app.controlled_edit.scene_parser import JsonVisionModel
from app.controlled_edit.schemas import EditIntent, SceneEntity


class IntentParseError(ValueError):
    """Raised when the LLM output is not a valid intent."""


INTENT_SYSTEM_PROMPT = """\
You translate a user's image-edit instruction (any language) into a structured \
intent for an image editing model. You are given the scene entities with ids.

Fields:
- operation: one of add, remove, replace, restyle, recolor, other.
- target_entity_ids: ids of EXISTING entities that will be directly changed, \
replaced or removed. For "add" operations list only entities that get replaced or \
covered on purpose; usually this is empty. Never list entities that merely stay \
nearby.
- new_entity_name: short English name of a newly added element, else null.
- location_hint: where the change happens in the image (English), else null.
- change_description: one or two concise English imperative sentences describing \
ONLY the requested change, with concrete visual details from the instruction.

Reply with JSON only:
{"operation": "add", "target_entity_ids": [], "new_entity_name": "witch hat", \
"location_hint": "on the character's head", "change_description": "Put a black \
Halloween witch hat on the character's head."}"""


async def parse_intent(
    model: JsonVisionModel,
    instruction: str,
    entities: list[SceneEntity],
) -> EditIntent:
    """Parse ``instruction`` against the current entity list.

    Unknown target ids invented by the model are dropped.

    Raises:
        IntentParseError: If the reply does not match the intent schema.
    """
    summary = [
        {"id": e.id, "name": e.name, "description": e.description, "status": e.status.value}
        for e in entities
    ]
    user_text = (
        f"Scene entities:\n{json.dumps(summary, ensure_ascii=False, indent=1)}\n\n"
        f"User instruction:\n{instruction}"
    )
    reply = await model.complete_json(system_prompt=INTENT_SYSTEM_PROMPT, user_text=user_text)
    try:
        intent = EditIntent.model_validate(
            {
                "operation": reply.get("operation", "other"),
                "target_entity_ids": reply.get("target_entity_ids") or [],
                "new_entity_name": reply.get("new_entity_name") or None,
                "location_hint": reply.get("location_hint") or None,
                "change_description": reply.get("change_description") or instruction,
            }
        )
    except ValidationError as exc:
        raise IntentParseError(f"intent reply is invalid: {exc}") from exc
    return known_target_ids(intent, entities)
