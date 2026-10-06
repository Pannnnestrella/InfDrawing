"""Tests for verifier scoring rules."""

from __future__ import annotations

import asyncio

from app.controlled_edit.schemas import (
    EditIntent,
    EditOperation,
    EntityStatus,
    SceneEntity,
)
from app.controlled_edit.verifier import retry_feedback, score_reply, verify_edit

LOCKED = SceneEntity(id="character.face", name="Face", status=EntityStatus.LOCKED)
APPROVED = SceneEntity(id="character.costume", name="Costume", status=EntityStatus.APPROVED)


def test_approved_drift_only_warns() -> None:
    result = score_reply(
        {
            "target_applied": True,
            "composition_score": 0.9,
            "entities": [
                {"entity_id": "character.face", "score": 0.9},
                {"entity_id": "character.costume", "score": 0.3, "comment": "color shift"},
            ],
        },
        [LOCKED, APPROVED],
        threshold=0.7,
    )
    assert result.passed
    assert len(result.warnings) == 1 and "Costume" in result.warnings[0]


def test_locked_drift_fails_and_feeds_back() -> None:
    result = score_reply(
        {
            "target_applied": True,
            "entities": [{"entity_id": "character.face", "score": 0.2, "comment": "new face"}],
        },
        [LOCKED],
        threshold=0.7,
    )
    assert not result.passed
    assert "Face changed (new face)." in retry_feedback(result, [LOCKED])


def test_missing_score_warns_and_target_not_applied_fails() -> None:
    result = score_reply({"target_applied": False, "entities": []}, [LOCKED], threshold=0.7)
    assert not result.passed
    assert any("未被验收模型评分" in w for w in result.warnings)
    assert "not visible" in retry_feedback(result, [LOCKED])


def test_reference_score_lowers_effective_score() -> None:
    result = score_reply(
        {
            "target_applied": True,
            "composition_score": 0.95,
            "entities": [
                {"entity_id": "character.face", "score": 1.0, "reference_score": 0.5},
            ],
        },
        [LOCKED],
        threshold=0.7,
        composition_threshold=0.75,
    )
    assert not result.passed
    assert result.preserved[0].score == 0.5


def test_composition_drift_fails_and_feeds_back() -> None:
    result = score_reply(
        {
            "target_applied": True,
            "composition_score": 0.4,
            "composition_comment": "zoomed in, legs cropped",
            "entities": [{"entity_id": "character.face", "score": 0.95}],
        },
        [LOCKED],
        threshold=0.7,
        composition_threshold=0.75,
    )
    assert not result.passed
    assert any("构图" in w for w in result.warnings)
    feedback = retry_feedback(result, [LOCKED], composition_threshold=0.75)
    assert "framing changed (zoomed in, legs cropped)" in feedback


def test_verify_edit_sends_anchor_images_with_checklist_indices() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.images: list[bytes] = []
            self.user_text = ""

        async def complete_json(self, *, system_prompt, user_text, images=None):  # type: ignore[no-untyped-def]
            self.images = images or []
            self.user_text = user_text
            return {"target_applied": True, "composition_score": 1.0, "entities": []}

    recorder = Recorder()
    intent = EditIntent(operation=EditOperation.ADD, change_description="Add a hat.")
    asyncio.run(
        verify_edit(
            recorder,
            before=b"before",
            after=b"after",
            intent=intent,
            entities=[LOCKED, APPROVED],
            threshold=0.7,
            composition_threshold=0.75,
            anchors=[(LOCKED, b"face-crop")],
        )
    )
    assert recorder.images == [b"before", b"after", b"face-crop"]
    assert '"reference_image": 3' in recorder.user_text


def test_scores_are_clamped_and_garbage_ignored() -> None:
    result = score_reply(
        {
            "target_applied": True,
            "entities": [
                {"entity_id": "character.face", "score": 7},
                {"entity_id": 3, "score": 0.1},
                "junk",
            ],
        },
        [LOCKED],
        threshold=0.7,
    )
    assert result.passed and result.preserved[0].score == 1.0
