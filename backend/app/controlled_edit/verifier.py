"""VLM verification of an edit candidate against the previous version and lock anchors."""

from __future__ import annotations

import json
from typing import Any

from app.controlled_edit.scene_parser import JsonVisionModel
from app.controlled_edit.schemas import (
    EditIntent,
    EntityPreservation,
    EntityStatus,
    SceneEntity,
    VerificationResult,
)

VERIFY_SYSTEM_PROMPT = """\
You are a strict QA reviewer for an image editing tool. Image 1 is BEFORE, image 2 \
is AFTER an edit. Images 3 and later (if any) are reference crops of locked elements, \
captured when the user locked them; the checklist says which image belongs to which \
element.

1. target_applied: true if the requested change is clearly visible in image 2.
2. composition_score: does image 2 keep the framing of image 1? Compare camera \
distance, zoom, crop, and the position and size of the main subject in the frame, \
ignoring the requested change itself. 1.0 = same framing, 0.7 = slightly shifted or \
scaled, 0.4 = clearly zoomed, cropped or re-centered, 0.0 = different shot.
3. For every listed entity, score how well it is preserved from image 1 to image 2 \
(score). For entities with a reference image, also score image 2 against that \
reference (reference_score). Scale: 1.0 = identical (ignore tiny resampling noise), \
0.8 = same identity with minor detail drift, 0.5 = noticeably different (shape, \
color, facial features, expression, age or pose changed), 0.0 = gone or replaced. \
If the requested change intentionally covers part of an entity, judge only the \
visible remainder. Be strict about faces.

Reply with JSON only:
{"target_applied": true, "target_comment": "...", "composition_score": 0.95, \
"composition_comment": "...", "entities": [{"entity_id": "...", "score": 0.95, \
"reference_score": 0.9, "comment": "..."}]}"""


async def verify_edit(
    model: JsonVisionModel,
    *,
    before: bytes,
    after: bytes,
    intent: EditIntent,
    entities: list[SceneEntity],
    threshold: float,
    composition_threshold: float,
    anchors: list[tuple[SceneEntity, bytes]] | None = None,
) -> VerificationResult:
    """Score an edit candidate.

    The candidate passes when the change is applied, the framing is kept, and every
    locked entity scores at least ``threshold`` against both the previous version and
    its lock-time anchor crop (which catches drift accumulated over several turns).
    Approved entities below the threshold only add warnings.

    Args:
        model: Vision model client.
        before: Parent version image.
        after: Candidate image.
        intent: Parsed intent; its targets are excluded from preservation checks.
        entities: Entities of the parent version.
        threshold: Minimum preservation score for locked entities.
        composition_threshold: Minimum framing score.
        anchors: Locked entities with their lock-time crops, sent as images 3..N.
    """
    targets = set(intent.target_entity_ids)
    protected = [
        e
        for e in entities
        if e.status in {EntityStatus.LOCKED, EntityStatus.APPROVED} and e.id not in targets
    ]
    usable_anchors = [(e, data) for e, data in anchors or [] if e.id not in targets]
    reference_image = {e.id: index + 3 for index, (e, _) in enumerate(usable_anchors)}
    checklist = [
        {
            "entity_id": e.id,
            "name": e.name,
            "description": e.description,
            "reference_image": reference_image.get(e.id),
        }
        for e in protected
    ]
    user_text = (
        f"Requested change: {intent.change_description}\n"
        f"Entities to check:\n{json.dumps(checklist, ensure_ascii=False, indent=1)}"
    )
    reply = await model.complete_json(
        system_prompt=VERIFY_SYSTEM_PROMPT,
        user_text=user_text,
        images=[before, after, *(data for _, data in usable_anchors)],
    )
    return score_reply(reply, protected, threshold, composition_threshold)


def _clamped(value: Any) -> float | None:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return None


def score_reply(
    reply: dict[str, Any],
    protected: list[SceneEntity],
    threshold: float,
    composition_threshold: float = 0.0,
) -> VerificationResult:
    """Turn a raw verifier reply into a pass/fail decision.

    An entity's effective score is the lower of its previous-version score and its
    reference score. A missing composition score is treated as unverified (warning).
    """
    target_applied = bool(reply.get("target_applied", False))
    scores: dict[str, EntityPreservation] = {}
    for raw in reply.get("entities") or []:
        if not isinstance(raw, dict) or not isinstance(raw.get("entity_id"), str):
            continue
        candidates = [_clamped(raw.get("score")), _clamped(raw.get("reference_score"))]
        valid = [score for score in candidates if score is not None]
        if not valid:
            continue
        scores[raw["entity_id"]] = EntityPreservation(
            entity_id=raw["entity_id"], score=min(valid), comment=str(raw.get("comment") or "")
        )

    warnings: list[str] = []
    passed = target_applied
    if not target_applied:
        warnings.append(f"改动未生效：{reply.get('target_comment') or '验收模型未检测到改动'}")

    composition = _clamped(reply.get("composition_score"))
    composition_comment = str(reply.get("composition_comment") or "")
    if composition is None:
        warnings.append("构图未被验收模型评分")
    elif composition < composition_threshold:
        passed = False
        warnings.append(f"构图发生变化（{composition:.2f}）：{composition_comment}")

    preserved: list[EntityPreservation] = []
    for entity in protected:
        found = scores.get(entity.id)
        if found is None:
            warnings.append(f"「{entity.name}」未被验收模型评分")
            continue
        preserved.append(found)
        if found.score >= threshold:
            continue
        if entity.status == EntityStatus.LOCKED:
            passed = False
            warnings.append(
                f"锁定实体「{entity.name}」发生变化（{found.score:.2f}）：{found.comment}"
            )
        else:
            warnings.append(
                f"已确认实体「{entity.name}」有变化（{found.score:.2f}）：{found.comment}"
            )
    return VerificationResult(
        target_applied=target_applied,
        target_comment=str(reply.get("target_comment") or ""),
        composition_score=composition,
        composition_comment=composition_comment,
        preserved=preserved,
        passed=passed,
        warnings=warnings,
    )


def retry_feedback(
    result: VerificationResult,
    entities: list[SceneEntity],
    *,
    composition_threshold: float = 0.0,
) -> str:
    """Summarize a failed verification as English feedback for the next prompt."""
    names = {e.id: e.name for e in entities}
    parts: list[str] = []
    if not result.target_applied:
        parts.append("the requested change was not visible.")
    if result.composition_score is not None and result.composition_score < composition_threshold:
        detail = f" ({result.composition_comment})" if result.composition_comment else ""
        parts.append(
            f"the framing changed{detail}; keep the exact camera distance, crop and subject "
            "position of image 1."
        )
    drifted = [p for p in result.preserved if p.score < 1.0 and p.comment]
    for item in sorted(drifted, key=lambda p: p.score)[:3]:
        parts.append(f"{names.get(item.entity_id, item.entity_id)} changed ({item.comment}).")
    return " ".join(parts) or "protected elements changed."
