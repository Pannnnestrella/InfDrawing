"""Pure helpers for entity-state inheritance and lock rules."""

from __future__ import annotations

from app.controlled_edit.schemas import (
    BBox,
    BBoxSource,
    EditIntent,
    EntityStatus,
    SceneEntity,
)


def merge_entities(
    previous: list[SceneEntity],
    parsed: list[SceneEntity],
) -> tuple[list[SceneEntity], list[str]]:
    """Carry protection state from the parent version onto a re-parsed entity list.

    Entities are matched by id. Locked entities missing from the re-parse are kept
    with their previous geometry so a lock can never be silently dropped. A locked
    entity with a manually corrected box keeps that box, because its region is not
    supposed to change; every other entity takes the freshly parsed box.

    Args:
        previous: Entities of the parent version, including statuses and anchors.
        parsed: Entities detected on the new image (statuses are ignored).

    Returns:
        The merged entity list and human-readable warnings.
    """
    by_id = {entity.id: entity for entity in previous}
    merged: list[SceneEntity] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for entity in parsed:
        prior = by_id.get(entity.id)
        if prior is None:
            merged.append(
                entity.model_copy(
                    update={
                        "status": EntityStatus.EDITABLE,
                        "anchor_version_id": None,
                        "anchor_artifact_id": None,
                    }
                )
            )
        else:
            changes: dict[str, object] = {
                "status": prior.status,
                "anchor_version_id": prior.anchor_version_id,
                "anchor_artifact_id": prior.anchor_artifact_id,
            }
            if prior.status == EntityStatus.LOCKED and prior.bbox_source == BBoxSource.MANUAL:
                changes["bbox"] = prior.bbox
                changes["bbox_source"] = BBoxSource.MANUAL
            merged.append(entity.model_copy(update=changes))
        seen.add(entity.id)
    for prior in previous:
        if prior.id in seen or prior.status != EntityStatus.LOCKED:
            continue
        merged.append(prior.model_copy())
        warnings.append(f"锁定实体「{prior.name}」在新图中未被识别，已保留原状态")
    known = {entity.id for entity in merged}
    for index, entity in enumerate(merged):
        if entity.parent_id is not None and entity.parent_id not in known:
            merged[index] = entity.model_copy(update={"parent_id": None})
    return merged, warnings


def find_lock_conflicts(intent: EditIntent, entities: list[SceneEntity]) -> list[SceneEntity]:
    """Return locked entities that the intent would directly modify.

    A locked parent also protects its descendants, so targeting ``character.hair``
    conflicts with a locked ``character``.
    """
    by_id = {entity.id: entity for entity in entities}
    conflicts: dict[str, SceneEntity] = {}
    for target_id in intent.target_entity_ids:
        current = by_id.get(target_id)
        while current is not None:
            if current.status == EntityStatus.LOCKED:
                conflicts[current.id] = current
            current = by_id.get(current.parent_id) if current.parent_id else None
    return list(conflicts.values())


def known_target_ids(intent: EditIntent, entities: list[SceneEntity]) -> EditIntent:
    """Drop target ids the parser invented that do not exist in the entity list."""
    known = {entity.id for entity in entities}
    targets = [target for target in intent.target_entity_ids if target in known]
    return intent.model_copy(update={"target_entity_ids": list(dict.fromkeys(targets))})


class InheritedLockError(ValueError):
    """Raised when unlocking (or re-statusing) a child while an ancestor is locked."""


def ancestor_is_locked(entities: list[SceneEntity], entity_id: str) -> bool:
    """Return True when a parent (or higher) of ``entity_id`` is locked."""
    by_id = {entity.id: entity for entity in entities}
    current = by_id.get(entity_id)
    while current is not None and current.parent_id:
        parent = by_id.get(current.parent_id)
        if parent is None:
            break
        if parent.status == EntityStatus.LOCKED:
            return True
        current = parent
    return False


def descendant_ids(entities: list[SceneEntity], root_id: str) -> set[str]:
    """Return every entity id under ``root_id`` (not including ``root_id``)."""
    children: dict[str | None, list[str]] = {}
    for entity in entities:
        children.setdefault(entity.parent_id, []).append(entity.id)
    found: set[str] = set()
    stack = list(children.get(root_id, []))
    while stack:
        entity_id = stack.pop()
        if entity_id in found:
            continue
        found.add(entity_id)
        stack.extend(children.get(entity_id, []))
    return found


def with_status(
    entities: list[SceneEntity],
    entity_id: str,
    status: EntityStatus,
    *,
    anchor_version_id: str | None = None,
    anchor_artifact_id: str | None = None,
) -> list[SceneEntity]:
    """Return a copy with ``entity_id`` and its descendants updated.

    Locking a parent also locks every descendant. Only ``entity_id`` receives the
    optional anchor crop; cascaded children stay locked without their own anchors.
    Unlocking (or approving) a parent clears the lock on all descendants. A child
    cannot leave the locked state while an ancestor is still locked.

    Raises:
        KeyError: If ``entity_id`` is not present.
        InheritedLockError: If changing a descendant away from locked under a
            locked ancestor.
    """
    by_id = {entity.id: entity for entity in entities}
    if entity_id not in by_id:
        raise KeyError(f"entity not found: {entity_id}")
    if status != EntityStatus.LOCKED and ancestor_is_locked(entities, entity_id):
        raise InheritedLockError(entity_id)

    cascade = descendant_ids(entities, entity_id)
    updated: list[SceneEntity] = []
    for entity in entities:
        if entity.id == entity_id:
            if status == EntityStatus.LOCKED:
                changes: dict[str, object] = {
                    "status": status,
                    "anchor_version_id": anchor_version_id,
                    "anchor_artifact_id": anchor_artifact_id,
                }
            else:
                changes = {
                    "status": status,
                    "anchor_version_id": None,
                    "anchor_artifact_id": None,
                }
            updated.append(entity.model_copy(update=changes))
            continue
        if entity.id not in cascade:
            updated.append(entity)
            continue
        if status == EntityStatus.LOCKED:
            updated.append(
                entity.model_copy(
                    update={
                        "status": EntityStatus.LOCKED,
                        "anchor_version_id": None,
                        "anchor_artifact_id": None,
                    }
                )
            )
        else:
            updated.append(
                entity.model_copy(
                    update={
                        "status": EntityStatus.EDITABLE,
                        "anchor_version_id": None,
                        "anchor_artifact_id": None,
                    }
                )
            )
    return updated


def with_manual_bbox(
    entities: list[SceneEntity],
    entity_id: str,
    bbox: BBox,
    *,
    anchor_artifact_id: str | None = None,
) -> list[SceneEntity]:
    """Return a copy of ``entities`` with one entity's box replaced by a manual box.

    Args:
        entities: Entities of one version.
        entity_id: Entity to update.
        bbox: Corrected box.
        anchor_artifact_id: New anchor crop; when given it replaces the current anchor.

    Raises:
        KeyError: If ``entity_id`` is not present.
    """
    updated: list[SceneEntity] = []
    found = False
    for entity in entities:
        if entity.id != entity_id:
            updated.append(entity)
            continue
        found = True
        changes: dict[str, object] = {"bbox": bbox, "bbox_source": BBoxSource.MANUAL}
        if anchor_artifact_id is not None:
            changes["anchor_artifact_id"] = anchor_artifact_id
        updated.append(entity.model_copy(update=changes))
    if not found:
        raise KeyError(f"entity not found: {entity_id}")
    return updated
