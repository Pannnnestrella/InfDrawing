"""End-to-end service tests with fake vision and image models."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from app.config import Settings
from app.controlled_edit.entities import InheritedLockError
from app.controlled_edit.intent_parser import INTENT_SYSTEM_PROMPT
from app.controlled_edit.repository import MemoryEditRepository
from app.controlled_edit.schemas import (
    BBox,
    BBoxSource,
    EditTurnRequest,
    EntityStatus,
    VersionStatus,
)
from app.controlled_edit.service import (
    ControlledEditService,
    LockConflictError,
    SessionNotFoundError,
    VersionNotDeletableError,
    VersionNotReadyError,
    _with_transport_retries,
)
from app.controlled_edit.verifier import VERIFY_SYSTEM_PROMPT
from app.pipeline.image_providers.base import ImageProviderError
from app.production.artifacts import ArtifactService, MemoryArtifactRepository
from app.production.infrastructure import LocalArtifactStorage

OWNER = "owner-1"


def _png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


SCENE = {
    "entities": [
        {"id": "character", "name": "Character", "bbox": [0.3, 0.1, 0.4, 0.8]},
        {
            "id": "character.face",
            "name": "Face",
            "parent_id": "character",
            "bbox": [0.45, 0.15, 0.1, 0.1],
        },
        {"id": "environment", "name": "Environment"},
        {"id": "environment.sky", "name": "Sky", "parent_id": "environment"},
    ]
}
SCENE_AFTER = {
    "entities": [
        *SCENE["entities"],
        {"id": "environment.moon", "name": "Moon", "parent_id": "environment"},
    ]
}


class FakeVision:
    """Routes calls by system prompt and replays queued verifier replies."""

    def __init__(self, verify_replies: list[dict[str, Any]], intent: dict[str, Any]) -> None:
        self.verify_replies = list(verify_replies)
        self.intent = intent
        self.scene_calls = 0
        self.verify_calls = 0
        self.verify_image_counts: list[int] = []

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_text: str,
        images: list[bytes] | None = None,
    ) -> dict[str, Any]:
        if system_prompt == INTENT_SYSTEM_PROMPT:
            return self.intent
        if system_prompt == VERIFY_SYSTEM_PROMPT:
            self.verify_calls += 1
            self.verify_image_counts.append(len(images or []))
            return self.verify_replies.pop(0)
        self.scene_calls += 1
        return SCENE if self.scene_calls == 1 else SCENE_AFTER


class FakeEditor:
    """Returns a solid image at the requested OpenAI size."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def multi_image_edit(self, **kwargs: Any) -> bytes:
        self.calls.append(kwargs)
        width, height = (int(v) for v in kwargs["size"].split("x"))
        return _png(width, height, (20, 0, 60))


SKY_INTENT = {
    "operation": "replace",
    "target_entity_ids": ["environment.sky"],
    "change_description": "Turn the sky into a Halloween night with a full moon.",
}
PASS = {
    "target_applied": True,
    "composition_score": 0.95,
    "entities": [{"entity_id": "character.face", "score": 0.95, "comment": "same"}],
}
FAIL = {
    "target_applied": True,
    "composition_score": 0.95,
    "entities": [{"entity_id": "character.face", "score": 0.4, "comment": "eyes changed"}],
}


def _build(
    tmp_path: Path,
    verify_replies: list[dict[str, Any]],
    intent: dict[str, Any] = SKY_INTENT,
) -> tuple[ControlledEditService, FakeVision, FakeEditor, list[Coroutine[Any, Any, None]]]:
    vision = FakeVision(verify_replies, intent)
    editor = FakeEditor()
    scheduled: list[Coroutine[Any, Any, None]] = []
    service = ControlledEditService(
        repository=MemoryEditRepository(),
        artifacts=ArtifactService(MemoryArtifactRepository(), LocalArtifactStorage(tmp_path)),
        vision_factory=lambda: vision,
        editor_factory=lambda _provider=None: editor,
        config=Settings(
            cedit_max_retries=1,
            cedit_preserve_threshold=0.7,
            openai_api_key="sk-test",
            dashscope_api_key="sk-ali",
        ),  # type: ignore[call-arg]
        scheduler=scheduled.append,
    )
    return service, vision, editor, scheduled


async def _session_with_locked_face(service: ControlledEditService) -> tuple[str, str]:
    tree = await service.create_session(OWNER, _png(1920, 1080, (200, 180, 160)), "image/png")
    session_id = tree.session.id
    root_id = tree.versions[0].id
    await service.update_entity_status(
        OWNER, session_id, root_id, "character.face", EntityStatus.LOCKED
    )
    return session_id, root_id


async def _submit_and_run(
    service: ControlledEditService,
    scheduled: list[Coroutine[Any, Any, None]],
    session_id: str,
    parent_id: str,
) -> str:
    child = await service.submit_turn(
        OWNER,
        session_id,
        EditTurnRequest(parent_version_id=parent_id, instruction="换成万圣夜"),
    )
    await scheduled.pop()
    return child.id


def test_turn_passes_first_try_and_records_node(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, vision, editor, scheduled = _build(tmp_path, [PASS])
        session_id, root_id = await _session_with_locked_face(service)
        root = (await service.get_tree(OWNER, session_id)).versions[0]
        face = next(e for e in root.entities if e.id == "character.face")
        assert face.anchor_artifact_id is not None and face.anchor_version_id == root_id

        child_id = await _submit_and_run(service, scheduled, session_id, root_id)
        tree = await service.get_tree(OWNER, session_id)
        child = next(v for v in tree.versions if v.id == child_id)

        assert tree.session.current_version_id == child_id
        assert child.status == VersionStatus.SUCCEEDED
        assert child.attempts == 1
        assert child.verification is not None and child.verification.passed
        assert child.reference_artifact_ids == [face.anchor_artifact_id]
        assert (child.width, child.height) == (1920, 1080)
        assert len(editor.calls) == 1
        assert editor.calls[0]["size"] == "1536x1024"
        assert len(editor.calls[0]["reference_images"]) == 1
        assert "Must match reference image 2" in editor.calls[0]["prompt"]
        assert vision.verify_image_counts == [3]
        by_id = {e.id: e for e in child.entities}
        assert by_id["character.face"].status == EntityStatus.LOCKED
        assert by_id["environment.moon"].status == EntityStatus.EDITABLE
        assert child.warnings == []

    asyncio.run(scenario())


def test_scene_parsing_uses_dedicated_vision_model(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, vision, _, scheduled = _build(tmp_path, [PASS])
        scene_vision = FakeVision([], {})
        service._scene_vision_factory = lambda: scene_vision
        session_id, root_id = await _session_with_locked_face(service)
        await _submit_and_run(service, scheduled, session_id, root_id)

        assert scene_vision.scene_calls == 2
        assert vision.scene_calls == 0
        assert vision.verify_calls == 1

    asyncio.run(scenario())


def _center_color(image_bytes: bytes) -> tuple[int, int, int]:
    with Image.open(io.BytesIO(image_bytes)) as image:
        rgb = image.convert("RGB")
        return rgb.getpixel((rgb.width // 2, rgb.height // 2))  # type: ignore[return-value]


def test_manual_bbox_recrops_anchor_from_lock_version_and_survives_reparse(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service, _, _, scheduled = _build(tmp_path, [PASS])
        session_id, root_id = await _session_with_locked_face(service)
        root = (await service.get_tree(OWNER, session_id)).versions[0]
        old_anchor = next(e for e in root.entities if e.id == "character.face").anchor_artifact_id

        manual = BBox(x=0.4, y=0.05, w=0.2, h=0.2)
        updated = await service.update_entity_bbox(
            OWNER, session_id, root_id, "character.face", manual
        )
        face = next(e for e in updated.entities if e.id == "character.face")
        assert face.bbox == manual and face.bbox_source == BBoxSource.MANUAL
        assert face.anchor_artifact_id not in {None, old_anchor}

        sky = await service.update_entity_bbox(
            OWNER, session_id, root_id, "environment.sky", BBox(x=0, y=0, w=1, h=0.3)
        )
        assert next(e for e in sky.entities if e.id == "environment.sky").anchor_artifact_id is None

        child_id = await _submit_and_run(service, scheduled, session_id, root_id)
        child = next(
            v for v in (await service.get_tree(OWNER, session_id)).versions if v.id == child_id
        )
        child_face = next(e for e in child.entities if e.id == "character.face")
        assert child_face.bbox == manual
        assert child_face.anchor_version_id == root_id

        corrected = BBox(x=0.42, y=0.06, w=0.18, h=0.18)
        recut = await service.update_entity_bbox(
            OWNER, session_id, child_id, "character.face", corrected
        )
        anchor_id = next(e for e in recut.entities if e.id == "character.face").anchor_artifact_id
        assert anchor_id is not None
        found = await service.read_owned_artifact(OWNER, anchor_id)
        assert found is not None
        assert _center_color(found[1]) == (200, 180, 160)

    asyncio.run(scenario())


def test_manual_bbox_unknown_entity_is_not_found(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, _, _ = _build(tmp_path, [])
        session_id, root_id = await _session_with_locked_face(service)
        with pytest.raises(SessionNotFoundError):
            await service.update_entity_bbox(
                OWNER, session_id, root_id, "missing", BBox(x=0, y=0, w=0.5, h=0.5)
            )

    asyncio.run(scenario())


def test_turn_retries_once_then_passes(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _vision, editor, scheduled = _build(tmp_path, [FAIL, PASS])
        session_id, root_id = await _session_with_locked_face(service)
        child_id = await _submit_and_run(service, scheduled, session_id, root_id)
        child = next(
            v for v in (await service.get_tree(OWNER, session_id)).versions if v.id == child_id
        )
        assert child.attempts == 2
        assert child.verification is not None and child.verification.passed
        assert "previous attempt was rejected" in editor.calls[1]["prompt"]
        assert "eyes changed" in editor.calls[1]["prompt"]
        assert child.warnings == []

    asyncio.run(scenario())


def test_turn_keeps_result_with_warning_when_retry_fails(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _vision, editor, scheduled = _build(tmp_path, [FAIL, FAIL])
        session_id, root_id = await _session_with_locked_face(service)
        child_id = await _submit_and_run(service, scheduled, session_id, root_id)
        child = next(
            v for v in (await service.get_tree(OWNER, session_id)).versions if v.id == child_id
        )
        assert child.status == VersionStatus.SUCCEEDED
        assert child.image_artifact_id is not None
        assert child.attempts == 2 and len(editor.calls) == 2
        assert child.verification is not None and not child.verification.passed
        assert child.warnings[0].startswith("验收未通过")
        assert any("Face" in w for w in child.warnings)

    asyncio.run(scenario())


def test_lock_conflict_is_rejected_before_generation(tmp_path: Path) -> None:
    async def scenario() -> None:
        face_intent = {
            "operation": "restyle",
            "target_entity_ids": ["character.face"],
            "change_description": "Add zombie makeup to the face.",
        }
        service, _, editor, scheduled = _build(tmp_path, [], intent=face_intent)
        session_id, root_id = await _session_with_locked_face(service)
        with pytest.raises(LockConflictError) as exc_info:
            await service.submit_turn(
                OWNER,
                session_id,
                EditTurnRequest(parent_version_id=root_id, instruction="给脸化僵尸妆"),
            )
        assert [e.id for e in exc_info.value.entities] == ["character.face"]
        assert scheduled == [] and editor.calls == []
        assert len((await service.get_tree(OWNER, session_id)).versions) == 1

    asyncio.run(scenario())


def test_branching_and_checkout(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, _, scheduled = _build(tmp_path, [PASS, PASS])
        session_id, root_id = await _session_with_locked_face(service)
        first = await _submit_and_run(service, scheduled, session_id, root_id)
        second = await _submit_and_run(service, scheduled, session_id, root_id)
        tree = await service.get_tree(OWNER, session_id)
        assert {v.parent_id for v in tree.versions if v.id in {first, second}} == {root_id}

        session = await service.checkout(OWNER, session_id, first)
        assert session.current_version_id == first

    asyncio.run(scenario())


def test_delete_version_removes_subtree_and_moves_cursor(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, _, scheduled = _build(tmp_path, [PASS, PASS, PASS])
        session_id, root_id = await _session_with_locked_face(service)
        branch = await _submit_and_run(service, scheduled, session_id, root_id)
        child = await _submit_and_run(service, scheduled, session_id, branch)
        sibling = await _submit_and_run(service, scheduled, session_id, root_id)
        assert (await service.get_tree(OWNER, session_id)).session.current_version_id == sibling

        await service.checkout(OWNER, session_id, child)
        tree = await service.delete_version(OWNER, session_id, branch)
        ids = {version.id for version in tree.versions}
        assert branch not in ids and child not in ids
        assert root_id in ids and sibling in ids
        assert tree.session.current_version_id == root_id

        with pytest.raises(VersionNotDeletableError):
            await service.delete_version(OWNER, session_id, root_id)

    asyncio.run(scenario())


def test_delete_busy_version_is_rejected(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, _, scheduled = _build(tmp_path, [PASS])
        session_id, root_id = await _session_with_locked_face(service)
        child = await service.submit_turn(
            OWNER, session_id, EditTurnRequest(parent_version_id=root_id, instruction="x")
        )
        with pytest.raises(VersionNotDeletableError):
            await service.delete_version(OWNER, session_id, child.id)
        scheduled.pop().close()

    asyncio.run(scenario())


def test_cannot_edit_from_pending_version(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, _, scheduled = _build(tmp_path, [PASS])
        session_id, root_id = await _session_with_locked_face(service)
        child = await service.submit_turn(
            OWNER, session_id, EditTurnRequest(parent_version_id=root_id, instruction="x")
        )
        with pytest.raises(VersionNotReadyError):
            await service.submit_turn(
                OWNER, session_id, EditTurnRequest(parent_version_id=child.id, instruction="y")
            )
        scheduled.pop().close()

    asyncio.run(scenario())


def test_transport_errors_are_retried_but_http_errors_are_not() -> None:
    async def scenario() -> None:
        calls = {"n": 0}

        async def flaky() -> bytes:
            calls["n"] += 1
            if calls["n"] == 1:
                raise ImageProviderError("request failed") from httpx.ReadError("reset")
            return b"ok"

        assert await _with_transport_retries(flaky, backoff=0) == b"ok"
        assert calls["n"] == 2

        async def rejected() -> bytes:
            calls["n"] += 1
            raise ImageProviderError("OpenAI Images error (400): bad prompt")

        calls["n"] = 0
        with pytest.raises(ImageProviderError):
            await _with_transport_retries(rejected, backoff=0)
        assert calls["n"] == 1

    asyncio.run(scenario())


def test_editor_failure_marks_node_failed(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, editor, scheduled = _build(tmp_path, [PASS])

        async def boom(**_: Any) -> bytes:
            raise RuntimeError("provider down")

        editor.multi_image_edit = boom  # type: ignore[method-assign]
        session_id, root_id = await _session_with_locked_face(service)
        child_id = await _submit_and_run(service, scheduled, session_id, root_id)
        child = next(
            v for v in (await service.get_tree(OWNER, session_id)).versions if v.id == child_id
        )
        assert child.status == VersionStatus.FAILED
        assert child.error is not None and "provider down" in child.error

    asyncio.run(scenario())


def test_turn_stores_prompt_style_and_image_provider(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, _, scheduled = _build(tmp_path, [PASS])
        session_id, root_id = await _session_with_locked_face(service)
        child = await service.submit_turn(
            OWNER,
            session_id,
            EditTurnRequest(
                parent_version_id=root_id,
                instruction="换成万圣夜",
                prompt_style="target_only",
                image_provider="openai",
            ),
        )
        assert child.prompt_style == "target_only"
        assert child.image_provider == "openai"
        await scheduled.pop()
        stored = next(
            v for v in (await service.get_tree(OWNER, session_id)).versions if v.id == child.id
        )
        assert stored.prompt_style == "target_only"
        assert "leave everything else as it already appears" in (stored.compiled_prompt or "")

    asyncio.run(scenario())


def test_clicked_targets_override_parsed_intent(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, editor, scheduled = _build(tmp_path, [PASS])
        session_id, root_id = await _session_with_locked_face(service)
        await service.update_entity_bbox(
            OWNER,
            session_id,
            root_id,
            "environment.sky",
            BBox(x=0.0, y=0.0, w=1.0, h=0.35),
        )
        child = await service.submit_turn(
            OWNER,
            session_id,
            EditTurnRequest(
                parent_version_id=root_id,
                instruction="换成万圣夜",
                target_entity_ids=["environment.sky"],
            ),
        )
        await scheduled.pop()
        stored = next(
            v for v in (await service.get_tree(OWNER, session_id)).versions if v.id == child.id
        )
        assert stored.intent is not None
        assert stored.intent.target_entity_ids == ["environment.sky"]
        assert "occupies x=" in editor.calls[0]["prompt"]

    asyncio.run(scenario())


def test_clicked_locked_target_conflicts(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, editor, scheduled = _build(tmp_path, [])
        session_id, root_id = await _session_with_locked_face(service)
        with pytest.raises(LockConflictError):
            await service.submit_turn(
                OWNER,
                session_id,
                EditTurnRequest(
                    parent_version_id=root_id,
                    instruction="换成万圣夜",
                    target_entity_ids=["character.face"],
                ),
            )
        assert scheduled == [] and editor.calls == []

    asyncio.run(scenario())


def test_locking_parent_cascades_and_blocks_child_unlock(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, _, _, _ = _build(tmp_path, [PASS])
        tree = await service.create_session(OWNER, _png(1920, 1080, (200, 180, 160)), "image/png")
        session_id = tree.session.id
        root_id = tree.versions[0].id
        updated = await service.update_entity_status(
            OWNER, session_id, root_id, "character", EntityStatus.LOCKED
        )
        by_id = {e.id: e for e in updated.entities}
        assert by_id["character"].status == EntityStatus.LOCKED
        assert by_id["character"].anchor_artifact_id is not None
        assert by_id["character.face"].status == EntityStatus.LOCKED
        assert by_id["character.face"].anchor_artifact_id is None
        with pytest.raises(InheritedLockError):
            await service.update_entity_status(
                OWNER, session_id, root_id, "character.face", EntityStatus.EDITABLE
            )
        cleared = await service.update_entity_status(
            OWNER, session_id, root_id, "character", EntityStatus.EDITABLE
        )
        assert all(e.status == EntityStatus.EDITABLE for e in cleared.entities)

    asyncio.run(scenario())
