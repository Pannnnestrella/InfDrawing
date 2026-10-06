"""Tests for controlled-edit domain models, repository, and entity rules."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.controlled_edit.entities import (
    find_lock_conflicts,
    known_target_ids,
    merge_entities,
    with_manual_bbox,
    with_status,
)
from app.controlled_edit.repository import JsonEditRepository, MemoryEditRepository
from app.controlled_edit.schemas import (
    BBox,
    BBoxSource,
    EditIntent,
    EditOperation,
    EditSession,
    EditVersion,
    EntityStatus,
    SceneEntity,
)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _entity(entity_id: str, status: EntityStatus = EntityStatus.EDITABLE, **kw) -> SceneEntity:  # type: ignore[no-untyped-def]
    return SceneEntity(id=entity_id, name=entity_id.split(".")[-1], status=status, **kw)


def test_bbox_clips_small_overflow_and_rejects_large() -> None:
    box = BBox(x=-0.01, y=0.5, w=0.5, h=0.51)
    assert box.x == 0.0
    assert box.y + box.h == pytest.approx(1.0)
    with pytest.raises(ValidationError):
        BBox(x=0.8, y=0.0, w=0.5, h=0.5)
    with pytest.raises(ValidationError):
        BBox(x=0.1, y=0.1, w=0.0, h=0.5)


def test_entity_id_must_be_dotted_snake_case() -> None:
    assert _entity("character.face").id == "character.face"
    with pytest.raises(ValidationError):
        SceneEntity(id="Character Face", name="x")


def test_repository_tree_with_branching() -> None:
    async def scenario() -> None:
        repo = MemoryEditRepository()
        session = await repo.create_session(EditSession(owner_key_id="owner"))
        root = await repo.add_version(EditVersion(session_id=session.id))
        child_a = await repo.add_version(EditVersion(session_id=session.id, parent_id=root.id))
        child_b = await repo.add_version(EditVersion(session_id=session.id, parent_id=root.id))
        await repo.add_version(EditVersion(session_id=session.id, parent_id=child_a.id))

        versions = await repo.list_versions(session.id)
        assert len(versions) == 4
        children = [v.id for v in versions if v.parent_id == root.id]
        assert children == [child_a.id, child_b.id]

        with pytest.raises(KeyError):
            await repo.add_version(EditVersion(session_id=session.id, parent_id="missing"))

    _run(scenario())


def test_repository_is_owner_scoped_and_copies() -> None:
    async def scenario() -> None:
        repo = MemoryEditRepository()
        session = await repo.create_session(EditSession(owner_key_id="owner"))
        assert await repo.get_session(session.id, "intruder") is None
        assert [s.id for s in await repo.list_sessions("owner")] == [session.id]

        version = await repo.add_version(EditVersion(session_id=session.id))
        fetched = await repo.get_version(session.id, version.id)
        assert fetched is not None
        fetched.instruction = "mutated locally"
        again = await repo.get_version(session.id, version.id)
        assert again is not None and again.instruction is None

        fetched.instruction = "saved"
        await repo.save_version(fetched)
        saved = await repo.get_version(session.id, version.id)
        assert saved is not None and saved.instruction == "saved"

    _run(scenario())


def test_json_repository_reloads_after_new_instance(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def scenario() -> None:
        path = tmp_path / "sessions.json"
        first = JsonEditRepository(path)
        session = await first.create_session(EditSession(owner_key_id="owner", title="kept"))
        root = await first.add_version(EditVersion(session_id=session.id, instruction="root"))
        child = await first.add_version(
            EditVersion(session_id=session.id, parent_id=root.id, instruction="branch")
        )
        session.current_version_id = child.id
        await first.save_session(session)

        second = JsonEditRepository(path)
        loaded = await second.get_session(session.id, "owner")
        assert loaded is not None and loaded.title == "kept"
        assert loaded.current_version_id == child.id
        versions = await second.list_versions(session.id)
        assert [v.instruction for v in versions] == ["root", "branch"]

    _run(scenario())


def test_merge_entities_inherits_state_and_keeps_missing_locks() -> None:
    previous = [
        _entity("character", EntityStatus.APPROVED),
        _entity(
            "character.face",
            EntityStatus.LOCKED,
            parent_id="character",
            anchor_version_id="v0",
            anchor_artifact_id="a0",
        ),
        _entity("character.hair", parent_id="character"),
        _entity("environment.sky"),
    ]
    parsed = [
        _entity("character"),
        _entity("character.hair", parent_id="character"),
        _entity("character.hat", parent_id="character"),
        _entity("environment.moon", parent_id="environment"),
    ]
    merged, warnings = merge_entities(previous, parsed)
    by_id = {e.id: e for e in merged}

    assert by_id["character"].status == EntityStatus.APPROVED
    assert by_id["character.hat"].status == EntityStatus.EDITABLE
    assert by_id["character.face"].status == EntityStatus.LOCKED
    assert by_id["character.face"].anchor_artifact_id == "a0"
    assert "environment.sky" not in by_id
    assert by_id["environment.moon"].parent_id is None
    assert len(warnings) == 1 and "face" in warnings[0]


def test_lock_conflicts_include_locked_ancestors() -> None:
    entities = [
        _entity("character", EntityStatus.LOCKED),
        _entity("character.hair", parent_id="character"),
        _entity("environment.sky"),
    ]
    intent = EditIntent(
        operation=EditOperation.RECOLOR,
        target_entity_ids=["character.hair", "environment.sky"],
        change_description="Make the hair red and the sky purple.",
    )
    conflicts = find_lock_conflicts(intent, entities)
    assert [c.id for c in conflicts] == ["character"]


def test_known_target_ids_drops_unknown_and_duplicates() -> None:
    entities = [_entity("environment.sky")]
    intent = EditIntent(
        operation=EditOperation.REPLACE,
        target_entity_ids=["environment.sky", "made.up", "environment.sky"],
        change_description="Night sky.",
    )
    assert known_target_ids(intent, entities).target_entity_ids == ["environment.sky"]


def test_with_status_sets_and_clears_anchor() -> None:
    entities = [_entity("character.face")]
    locked = with_status(
        entities,
        "character.face",
        EntityStatus.LOCKED,
        anchor_version_id="v1",
        anchor_artifact_id="a1",
    )
    assert locked[0].anchor_artifact_id == "a1"
    unlocked = with_status(locked, "character.face", EntityStatus.EDITABLE)
    assert unlocked[0].anchor_artifact_id is None
    with pytest.raises(KeyError):
        with_status(entities, "missing", EntityStatus.LOCKED)


def test_with_status_cascades_lock_and_blocks_child_unlock() -> None:
    from app.controlled_edit.entities import InheritedLockError

    entities = [
        _entity("character"),
        _entity("character.face", parent_id="character"),
        _entity("character.sword", parent_id="character"),
        _entity("environment.sky"),
    ]
    locked = with_status(
        entities,
        "character",
        EntityStatus.LOCKED,
        anchor_version_id="v1",
        anchor_artifact_id="a-char",
    )
    by_id = {e.id: e for e in locked}
    assert by_id["character"].anchor_artifact_id == "a-char"
    assert by_id["character.face"].status == EntityStatus.LOCKED
    assert by_id["character.face"].anchor_artifact_id is None
    assert by_id["character.sword"].status == EntityStatus.LOCKED
    assert by_id["environment.sky"].status == EntityStatus.EDITABLE
    with pytest.raises(InheritedLockError):
        with_status(locked, "character.face", EntityStatus.EDITABLE)
    unlocked = with_status(locked, "character", EntityStatus.EDITABLE)
    assert all(e.status == EntityStatus.EDITABLE for e in unlocked)


def test_with_manual_bbox_marks_source_and_optionally_replaces_anchor() -> None:
    entities = [_entity("character.face", EntityStatus.LOCKED, anchor_artifact_id="old")]
    box = BBox(x=0.4, y=0.05, w=0.15, h=0.12)

    kept = with_manual_bbox(entities, "character.face", box)
    assert kept[0].bbox == box
    assert kept[0].bbox_source == BBoxSource.MANUAL
    assert kept[0].anchor_artifact_id == "old"
    assert entities[0].bbox_source == BBoxSource.MODEL

    replaced = with_manual_bbox(entities, "character.face", box, anchor_artifact_id="new")
    assert replaced[0].anchor_artifact_id == "new"
    with pytest.raises(KeyError):
        with_manual_bbox(entities, "missing", box)


def test_merge_keeps_manual_box_only_for_locked_entities() -> None:
    manual = BBox(x=0.4, y=0.05, w=0.15, h=0.12)
    parsed_box = BBox(x=0.1, y=0.1, w=0.2, h=0.2)
    previous = [
        _entity(
            "character.face", EntityStatus.LOCKED, bbox=manual, bbox_source=BBoxSource.MANUAL
        ),
        _entity("character.hat", bbox=manual, bbox_source=BBoxSource.MANUAL),
    ]
    parsed = [
        _entity("character.face", bbox=parsed_box),
        _entity("character.hat", bbox=parsed_box),
    ]

    merged, _ = merge_entities(previous, parsed)
    by_id = {e.id: e for e in merged}
    assert by_id["character.face"].bbox == manual
    assert by_id["character.face"].bbox_source == BBoxSource.MANUAL
    assert by_id["character.hat"].bbox == parsed_box
    assert by_id["character.hat"].bbox_source == BBoxSource.MODEL
