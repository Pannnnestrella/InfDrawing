"""Deterministic edit-prompt compilation from intent and entity states."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.controlled_edit.region_ops import bbox_prompt_lines
from app.controlled_edit.schemas import EditIntent, EntityStatus, SceneEntity

PROMPT_STYLE_PRESERVE = "preserve"
PROMPT_STYLE_TARGET_ONLY = "target_only"


@dataclass(frozen=True)
class CompiledEdit:
    """A ready-to-send edit prompt and the anchors it references.

    Attributes:
        prompt: Full prompt text for the image model.
        reference_entities: Locked entities whose anchor crops are sent as images
            2..N, in this order.
    """

    prompt: str
    reference_entities: list[SceneEntity] = field(default_factory=list)


def _label(entity: SceneEntity) -> str:
    detail = f" — {entity.description}" if entity.description else ""
    return f"{entity.name} ({entity.id}){detail}"


def compile_edit_prompt(
    intent: EditIntent,
    entities: list[SceneEntity],
    *,
    max_references: int = 4,
    retry_feedback: str | None = None,
    image_layout: str = "primary_first",
    prompt_style: str = PROMPT_STYLE_PRESERVE,
) -> CompiledEdit:
    """Build the edit prompt.

    ``preserve`` (default) lists locked and approved entities to leave alone.
    ``target_only`` describes only the requested change and target boxes, plus short
    pointers for attached identity reference images.

    Args:
        intent: Parsed user intent.
        entities: Entities of the version being edited.
        max_references: Maximum number of anchor crops to attach.
        retry_feedback: Verifier feedback from a failed previous attempt.
        image_layout: ``primary_first`` (OpenAI) or ``primary_last`` (Qwen).
        prompt_style: ``preserve`` or ``target_only``.

    Returns:
        The compiled prompt and the ordered reference entities.
    """
    targets = set(intent.target_entity_ids)
    locked = [e for e in entities if e.status == EntityStatus.LOCKED and e.id not in targets]
    approved = [
        e for e in entities if e.status == EntityStatus.APPROVED and e.id not in targets
    ]
    references = [e for e in locked if e.anchor_artifact_id][:max_references]
    if image_layout == "primary_last":
        primary = f"the last image (image {len(references) + 1})"
        reference_index = {e.id: index + 1 for index, e in enumerate(references)}
    else:
        primary = "image 1"
        reference_index = {e.id: index + 2 for index, e in enumerate(references)}
    by_id = {e.id: e for e in entities}

    if prompt_style == PROMPT_STYLE_TARGET_ONLY:
        lines = _target_only_lines(
            intent, by_id, entities, primary, references, reference_index, image_layout
        )
    else:
        lines = _preserve_lines(
            intent,
            by_id,
            entities,
            primary,
            locked,
            approved,
            references,
            reference_index,
            image_layout,
        )
    if retry_feedback:
        lines += ["", f"The previous attempt was rejected: {retry_feedback} Fix this."]
    return CompiledEdit(prompt="\n".join(lines), reference_entities=references)


def _change_header(
    intent: EditIntent,
    by_id: dict[str, SceneEntity],
    entities: list[SceneEntity],
    primary: str,
) -> list[str]:
    lines = [
        (
            f"Edit {primary} (the current version of the artwork). Output an edited "
            f"version of {primary} with the same framing, composition, camera angle "
            "and art style."
        ),
        "",
        f"Requested change: {intent.change_description}",
    ]
    if intent.location_hint:
        lines.append(f"Where: {intent.location_hint}")
    target_names = [by_id[t].name for t in intent.target_entity_ids if t in by_id]
    if target_names:
        lines.append(f"Elements to change: {', '.join(target_names)}")
    lines += bbox_prompt_lines(entities, intent.target_entity_ids)
    return lines


def _reference_note(image_layout: str) -> str:
    if image_layout == "primary_last":
        return (
            "Images before the last one are identity references only: do not paste "
            "them into the output and do not add extra copies of them."
        )
    return (
        "Reference images 2 and later are identity references only: do not paste "
        "them into the output and do not add extra copies of them."
    )


def _preserve_lines(
    intent: EditIntent,
    by_id: dict[str, SceneEntity],
    entities: list[SceneEntity],
    primary: str,
    locked: list[SceneEntity],
    approved: list[SceneEntity],
    references: list[SceneEntity],
    reference_index: dict[str, int],
    image_layout: str,
) -> list[str]:
    lines = _change_header(intent, by_id, entities, primary)
    if locked:
        lines += ["", "Preserve exactly — identity, shape, colors, pose and position unchanged:"]
        for entity in locked:
            ref = reference_index.get(entity.id)
            suffix = f" Must match reference image {ref}." if ref else ""
            lines.append(f"- {_label(entity)}.{suffix}")
    if approved:
        lines += ["", "Keep unchanged unless the requested change requires it:"]
        lines += [f"- {_label(entity)}." for entity in approved]
    lines += [
        "",
        (
            f"Edit the full frame of {primary}. Keep the exact framing: same camera "
            "distance and crop; every element keeps its position and size in the frame. "
            "Do not zoom in, zoom out, crop or re-center."
        ),
        (
            "Do not add, remove, move or restyle anything that is not part of the requested "
            f"change. Keep facial expressions unchanged. Keep lighting and color grading "
            f"consistent with {primary} unless the requested change is about them."
        ),
    ]
    if references:
        lines.append(_reference_note(image_layout))
    return lines


def _target_only_lines(
    intent: EditIntent,
    by_id: dict[str, SceneEntity],
    entities: list[SceneEntity],
    primary: str,
    references: list[SceneEntity],
    reference_index: dict[str, int],
    image_layout: str,
) -> list[str]:
    """Describe only the change; identity refs get a short pointer when attached."""
    lines = _change_header(intent, by_id, entities, primary)
    if references:
        lines += ["", "Identity references (match appearance only, do not paste into the scene):"]
        for entity in references:
            ref = reference_index[entity.id]
            lines.append(f"- Reference image {ref}: {_label(entity)}.")
        lines.append(_reference_note(image_layout))
    lines += [
        "",
        (
            f"Apply the requested change on {primary} and leave everything else as it "
            "already appears in that image."
        ),
    ]
    return lines
