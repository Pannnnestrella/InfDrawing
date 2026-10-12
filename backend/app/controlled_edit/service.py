"""Orchestration of controlled-edit sessions, turns, and entity locks."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import io
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

import httpx
from PIL import Image, ImageOps

from app.config import Settings, settings
from app.controlled_edit.anchors import crop_entity
from app.controlled_edit.entities import (
    InheritedLockError,
    find_lock_conflicts,
    merge_entities,
    with_manual_bbox,
    with_status,
)
from app.controlled_edit.inpaint_crop import CropResult, inpaint_crop
from app.controlled_edit.inpaint_stitch import inpaint_stitch
from app.controlled_edit.inpaint_types import (
    InpaintOptions,
    LocalTurnFields,
    MaskRecord,
)
from app.controlled_edit.intent_parser import parse_intent
from app.controlled_edit.masks import png_bytes, prepare_mask
from app.controlled_edit.prompt_compiler import compile_edit_prompt
from app.controlled_edit.region_ops import (
    build_edit_mask,
    framing_drift,
    lock_composite,
    mask_png_bytes,
    uses_local_mask,
)
from app.controlled_edit.repository import EditRepository, get_edit_repository
from app.controlled_edit.scene_parser import (
    JsonVisionModel,
    SceneParseError,
    parse_scene,
)
from app.controlled_edit.schemas import (
    BBox,
    EditSession,
    EditTurnRequest,
    EditVersion,
    EntityStatus,
    SceneEntity,
    SessionTree,
    VerificationResult,
    VersionStatus,
)
from app.controlled_edit.segmentation import SegmentRequest
from app.controlled_edit.sizing import pad_to_supported, restore_original_frame
from app.controlled_edit.verifier import retry_feedback, verify_edit
from app.controlled_edit.vision import VisionError
from app.pipeline.image_providers.base import ImageProviderError
from app.pipeline.image_validation import validate_upload_image
from app.production.artifacts import ArtifactService, get_artifact_service

logger = logging.getLogger(__name__)

Scheduler = Callable[[Coroutine[Any, Any, None]], None]


class ImageEditor(Protocol):
    """Image model able to edit one image with extra reference images."""

    async def multi_image_edit(
        self,
        *,
        image_bytes: bytes,
        reference_images: list[bytes],
        prompt: str,
        size: str = "1024x1024",
        input_fidelity: str | None = None,
    ) -> bytes: ...


class SessionNotFoundError(LookupError):
    """Raised when a session or version does not exist for the caller."""


class VersionNotReadyError(ValueError):
    """Raised when an operation needs a succeeded version."""


class LockConflictError(ValueError):
    """Raised when an instruction targets locked entities."""

    def __init__(self, entities: list[SceneEntity]) -> None:
        self.entities = entities
        names = "、".join(e.name for e in entities)
        super().__init__(f"指令会修改已锁定的实体：{names}。请先解锁再提交。")


class VersionNotDeletableError(ValueError):
    """Raised when a version cannot be deleted (root, busy, or unknown)."""


class EditorUnavailableError(ValueError):
    """Raised when the requested image editor cannot be constructed."""


def _subtree_version_ids(versions: list[EditVersion], root_id: str) -> set[str]:
    """Return ``root_id`` and every descendant version id."""
    children: dict[str | None, list[str]] = {}
    for version in versions:
        children.setdefault(version.parent_id, []).append(version.id)
    found = {root_id}
    stack = [root_id]
    while stack:
        current = stack.pop()
        for child_id in children.get(current, []):
            if child_id not in found:
                found.add(child_id)
                stack.append(child_id)
    return found


_background_tasks: set[asyncio.Task[None]] = set()


def _create_background_task(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


TRANSPORT_RETRIES = 2
TRANSPORT_BACKOFF_SECONDS = 2.0


async def _with_transport_retries(
    call: Callable[[], Coroutine[Any, Any, bytes]],
    *,
    retries: int = TRANSPORT_RETRIES,
    backoff: float = TRANSPORT_BACKOFF_SECONDS,
) -> bytes:
    """Retry an image call when it failed on a dropped connection (not on HTTP errors)."""
    for attempt in range(retries + 1):
        try:
            return await call()
        except ImageProviderError as exc:
            transient = isinstance(exc.__cause__, httpx.TransportError)
            if not transient or attempt == retries:
                raise
            logger.warning("image call transport error, retrying: %s", exc)
            await asyncio.sleep(backoff * (attempt + 1))
    raise RuntimeError("unreachable")


def _image_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(image_bytes)) as image:
        return image.size


class ControlledEditService:
    """Coordinate parsing, prompt compilation, generation, verification and storage."""

    def __init__(
        self,
        *,
        repository: EditRepository,
        artifacts: ArtifactService,
        vision_factory: Callable[[], JsonVisionModel],
        editor_factory: Callable[[str | None], ImageEditor],
        config: Settings = settings,
        scheduler: Scheduler | None = None,
        scene_vision_factory: Callable[[], JsonVisionModel] | None = None,
    ) -> None:
        self._repository = repository
        self._artifacts = artifacts
        self._vision_factory = vision_factory
        self._scene_vision_factory = scene_vision_factory or vision_factory
        self._editor_factory = editor_factory
        self._config = config
        self._schedule = scheduler or _create_background_task

    async def create_session(
        self,
        owner_key_id: str,
        image_bytes: bytes,
        media_type: str,
        title: str = "Untitled",
    ) -> SessionTree:
        """Store the uploaded image, parse its scene, and create the root version."""
        validate_upload_image(image_bytes, media_type)
        with Image.open(io.BytesIO(image_bytes)) as decoded:
            normalized = ImageOps.exif_transpose(decoded)
            normalized = normalized.convert("RGBA" if "A" in normalized.getbands() else "RGB")
            image_bytes = png_bytes(normalized)
        artifact = await self._artifacts.create_image(owner_key_id, image_bytes, "image/png")
        width, height = _image_size(image_bytes)
        entities = await parse_scene(
            self._scene_vision_factory(),
            image_bytes,
            max_entities=self._config.cedit_max_entities,
            box_format=self._config.cedit_scene_bbox_format,
        )
        session = EditSession(owner_key_id=owner_key_id, title=title[:120] or "Untitled")
        root = EditVersion(
            session_id=session.id,
            status=VersionStatus.SUCCEEDED,
            image_artifact_id=artifact.id,
            width=width,
            height=height,
            entities=entities,
        )
        session.root_version_id = root.id
        session.current_version_id = root.id
        await self._repository.create_session(session)
        await self._repository.add_version(root)
        return SessionTree(session=session, versions=[root])

    async def list_sessions(self, owner_key_id: str) -> list[EditSession]:
        """Return the caller's sessions, newest first."""
        return await self._repository.list_sessions(owner_key_id)

    async def get_tree(self, owner_key_id: str, session_id: str) -> SessionTree:
        """Return a session with all its versions."""
        session = await self._owned_session(owner_key_id, session_id)
        return SessionTree(
            session=session, versions=await self._repository.list_versions(session_id)
        )

    async def submit_turn(
        self,
        owner_key_id: str,
        session_id: str,
        request: EditTurnRequest,
    ) -> EditVersion:
        """Parse the instruction, reject lock conflicts, and schedule generation.

        Raises:
            SessionNotFoundError: Unknown session or parent version.
            VersionNotReadyError: The parent version has not succeeded.
            LockConflictError: The instruction targets locked entities.
        """
        session = await self._owned_session(owner_key_id, session_id)
        parent = await self._ready_version(session_id, request.parent_version_id)
        if request.edit_mode == "local":
            if request.image_provider == "openai":
                raise EditorUnavailableError("局部 Crop/Stitch 当前使用万相，请选择通义提供商")
            if self._config.dashscope_edit_model != request.inpaint_options.model:
                raise EditorUnavailableError("局部重绘模型与服务器配置不一致")
            await self.prepare_local_crop(
                owner_key_id,
                session_id,
                parent.id,
                request.mask_artifact_id or "",
                request.inpaint_options,
            )
        intent = await parse_intent(self._vision_factory(), request.instruction, parent.entities)
        known = {entity.id for entity in parent.entities}
        chosen = [entity_id for entity_id in request.target_entity_ids if entity_id in known]
        if chosen:
            intent = intent.model_copy(update={"target_entity_ids": chosen})
        conflicts = find_lock_conflicts(intent, parent.entities)
        if conflicts:
            raise LockConflictError(conflicts)
        prompt_style = request.prompt_style or self._config.cedit_prompt_style
        image_provider = (
            "dashscope"
            if request.edit_mode == "local"
            else request.image_provider or self._config.cedit_image_provider
        )
        _assert_editor_available(image_provider, self._config)
        child = EditVersion(
            session_id=session_id,
            parent_id=parent.id,
            progress_step="queued",
            instruction=request.instruction,
            intent=intent,
            prompt_style=prompt_style,
            image_provider=image_provider,
            width=parent.width,
            height=parent.height,
            entities=[e.model_copy() for e in parent.entities],
            local_edit=LocalTurnFields(
                edit_mode=request.edit_mode,
                mask_artifact_id=request.mask_artifact_id,
                inpaint_options=request.inpaint_options,
            ),
        )
        await self._repository.add_version(child)
        session.current_version_id = child.id
        await self._repository.save_session(session)
        self._schedule(self.run_turn(owner_key_id, session_id, child.id))
        return child

    async def run_turn(self, owner_key_id: str, session_id: str, version_id: str) -> None:
        """Generate, verify (with retries), and persist one pending version.

        Failures are recorded on the version node instead of propagating, because this
        runs as a detached background task.
        """
        version = await self._repository.get_version(session_id, version_id)
        if version is None or version.parent_id is None or version.intent is None:
            logger.error("controlled edit turn %s is missing or malformed", version_id)
            return
        try:
            await self._execute_turn(owner_key_id, version)
        except Exception as exc:
            logger.exception("controlled edit turn %s failed", version_id)
            version.status = VersionStatus.FAILED
            version.progress_step = None
            version.error = f"{type(exc).__name__}: {exc}"[:500]
            await self._repository.save_version(version)

    async def _execute_turn(self, owner_key_id: str, version: EditVersion) -> None:
        if version.parent_id is None or version.intent is None:
            raise VersionNotReadyError(f"version {version.id} has no parent or intent")
        parent = await self._ready_version(version.session_id, version.parent_id)
        await self._set_step(version, "preparing", VersionStatus.RUNNING)
        parent_bytes = await self._read_artifact(owner_key_id, parent.image_artifact_id)
        image_provider = version.image_provider or self._config.cedit_image_provider
        prompt_style = version.prompt_style or self._config.cedit_prompt_style
        explicit_local = bool(version.local_edit and version.local_edit.edit_mode == "local")
        editor = None if explicit_local else self._editor_factory(image_provider)
        vision = self._vision_factory()
        layout = getattr(editor, "prompt_image_layout", "primary_first")
        max_refs = self._max_references(layout)

        max_attempts = 1 + max(0, self._config.cedit_max_retries)
        feedback: str | None = None
        parsed_entities: list[SceneEntity] | None = None
        parse_warnings: list[str] = []
        crop = None
        if explicit_local and version.local_edit:
            crop = await self.prepare_local_crop(
                owner_key_id,
                version.session_id,
                parent.id,
                version.local_edit.mask_artifact_id or "",
                version.local_edit.inpaint_options,
            )
            crop_artifact = await self._artifacts.create_image(
                owner_key_id, crop.image, "image/png"
            )
            gen_mask = await self._artifacts.create_image(owner_key_id, crop.mask, "image/png")
            blend = await self._artifacts.create_image(owner_key_id, crop.blend, "image/png")
            version.stitcher = crop.stitcher.model_copy(
                update={
                    "source_artifact_id": parent.image_artifact_id,
                    "parent_version_id": parent.id,
                    "mask_artifact_id": version.local_edit.mask_artifact_id,
                    "crop_artifact_id": crop_artifact.id,
                    "generation_mask_artifact_id": gen_mask.id,
                    "blend_artifact_id": blend.id,
                }
            )
        for attempt in range(1, max_attempts + 1):
            compiled = compile_edit_prompt(
                version.intent,
                parent.entities,
                max_references=max_refs,
                retry_feedback=feedback,
                image_layout=layout,
                prompt_style=prompt_style,
            )
            references = [
                await self._read_artifact(owner_key_id, e.anchor_artifact_id)
                for e in compiled.reference_entities
            ]
            version.attempts = attempt
            version.compiled_prompt = compiled.prompt
            version.reference_artifact_ids = (
                []
                if explicit_local
                else [
                    e.anchor_artifact_id
                    for e in compiled.reference_entities
                    if e.anchor_artifact_id
                ]
            )
            await self._set_step(version, "generating" if attempt == 1 else "retrying")
            padded = pad_to_supported(parent_bytes)
            use_mask = explicit_local or (
                not (version.local_edit and version.local_edit.edit_mode == "full")
                and uses_local_mask(version.intent, parent.entities)
                and _wanx_mask_available(self._config)
            )
            if use_mask:
                if "local_mask:wanx" not in version.warnings:
                    version.warnings.append("local_mask:wanx")
                with Image.open(io.BytesIO(parent_bytes)) as parent_im:
                    size = parent_im.size
                mask = build_edit_mask(
                    size,
                    parent.entities,
                    version.intent.target_entity_ids,
                    unconstrained="keep",
                )
                from app.pipeline.image_providers.dashscope_wanx import (
                    DashScopeWanxProvider,
                )

                base_prompt = version.instruction or version.intent.change_description
                feedback_text = f"修正上次问题：{feedback[:300]}。" if feedback else ""
                wanx_prompt = (feedback_text + base_prompt)[:800]
                version.compiled_prompt = wanx_prompt
                raw = await _with_transport_retries(
                    functools.partial(
                        DashScopeWanxProvider(self._config).inpaint,
                        image_bytes=crop.image if crop else parent_bytes,
                        mask_bytes=crop.mask if crop else mask_png_bytes(mask),
                        prompt=wanx_prompt,
                    )
                )
            else:
                assert editor is not None
                raw = await _with_transport_retries(
                    functools.partial(
                        editor.multi_image_edit,
                        image_bytes=padded.png,
                        reference_images=references,
                        prompt=compiled.prompt,
                        size=padded.size,
                        input_fidelity=self._config.cedit_input_fidelity or None,
                    )
                )
            candidate = raw if use_mask else restore_original_frame(raw, padded)
            if crop and version.stitcher:
                candidate = await asyncio.to_thread(
                    inpaint_stitch, parent_bytes, raw, crop.blend, version.stitcher
                )
                version.stitcher = version.stitcher.model_copy(
                    update={"actual_output_size": _image_size(raw)}
                )
            if self._config.cedit_lock_paste and not use_mask:
                candidate = lock_composite(
                    parent_bytes,
                    candidate,
                    parent.entities,
                    set(version.intent.target_entity_ids),
                    feather=self._config.cedit_lock_feather,
                    anchored_only=True,
                )
            await self._set_step(version, "parsing")
            parse_warnings = []
            parsed_entities = None
            try:
                parsed = await parse_scene(
                    self._scene_vision_factory(),
                    candidate,
                    previous=parent.entities,
                    max_entities=self._config.cedit_max_entities,
                    box_format=self._config.cedit_scene_bbox_format,
                )
                parsed_entities, parse_warnings = merge_entities(parent.entities, parsed)
            except (VisionError, SceneParseError) as exc:
                parse_warnings = [f"新版本实体重解析失败，已沿用上一版实体：{exc}"[:300]]
            drift = (
                framing_drift(
                    parent.entities,
                    parsed_entities,
                    shift_threshold=self._config.cedit_subject_shift_threshold,
                    area_threshold=self._config.cedit_subject_area_threshold,
                )
                if parsed_entities is not None
                else None
            )
            await self._set_step(version, "verifying")
            if drift:
                verification = VerificationResult(
                    target_applied=True,
                    target_comment="skipped visual QA after framing drift",
                    passed=False,
                    warnings=[drift],
                )
            else:
                verification = await verify_edit(
                    vision,
                    before=parent_bytes,
                    after=candidate,
                    intent=version.intent,
                    entities=parent.entities,
                    threshold=self._config.cedit_preserve_threshold,
                    composition_threshold=self._config.cedit_composition_threshold,
                    anchors=list(zip(compiled.reference_entities, references, strict=True)),
                )
            version.verification = verification
            if verification.passed:
                break
            feedback = retry_feedback(
                verification,
                parent.entities,
                composition_threshold=self._config.cedit_composition_threshold,
            )

        artifact = await self._artifacts.create_image(owner_key_id, candidate, "image/png")
        version.image_artifact_id = artifact.id
        warnings = list(parse_warnings)
        version.entities = (
            parsed_entities
            if parsed_entities is not None
            else [e.model_copy() for e in parent.entities]
        )
        if version.verification is not None and not version.verification.passed:
            warnings.insert(0, f"验收未通过（共尝试 {version.attempts} 次），请检查或回退")
        if version.verification is not None:
            warnings += version.verification.warnings
        version.warnings = warnings
        version.status = VersionStatus.SUCCEEDED
        version.progress_step = None
        await self._repository.save_version(version)

    async def update_entity_status(
        self,
        owner_key_id: str,
        session_id: str,
        version_id: str,
        entity_id: str,
        status: EntityStatus,
    ) -> EditVersion:
        """Change one entity's status; locking stores an anchor crop of this version.

        Raises:
            SessionNotFoundError: Unknown session, version or entity.
            VersionNotReadyError: The version has not succeeded.
        """
        await self._owned_session(owner_key_id, session_id)
        version = await self._ready_version(session_id, version_id)
        entity = next((e for e in version.entities if e.id == entity_id), None)
        if entity is None:
            raise SessionNotFoundError(f"entity not found: {entity_id}")
        if entity.status == status:
            return version
        anchor_artifact_id: str | None = None
        if status == EntityStatus.LOCKED and entity.bbox is not None:
            image_bytes = await self._read_artifact(owner_key_id, version.image_artifact_id)
            crop = crop_entity(image_bytes, entity.bbox)
            anchor = await self._artifacts.create_image(owner_key_id, crop, "image/png")
            anchor_artifact_id = anchor.id
        try:
            version.entities = with_status(
                version.entities,
                entity_id,
                status,
                anchor_version_id=version.id if status == EntityStatus.LOCKED else None,
                anchor_artifact_id=anchor_artifact_id,
            )
        except InheritedLockError as exc:
            raise InheritedLockError(
                f"entity {entity_id} inherits a lock from its parent; unlock the parent first"
            ) from exc
        return await self._repository.save_version(version)

    async def save_mask(
        self,
        owner: str,
        session_id: str,
        version_id: str,
        data: bytes,
        source: str = "manual",
        score: float | None = None,
    ) -> MaskRecord:
        """Validate and persist a mask bound to this exact owned parent version."""
        await self._owned_session(owner, session_id)
        version = await self._ready_version(session_id, version_id)
        original = await self._read_artifact(owner, version.image_artifact_id)
        with Image.open(io.BytesIO(original)) as decoded:
            size = ImageOps.exif_transpose(decoded).size
        validate_upload_image(data, None)
        with Image.open(io.BytesIO(data)) as decoded:
            if decoded.size != size:
                raise ValueError("mask dimensions must match the source image")
            mask_image = decoded.convert("L")
        if mask_image.getbbox() is None:
            raise ValueError("mask is empty")
        artifact = await self._artifacts.create_image(owner, png_bytes(mask_image), "image/png")
        record = MaskRecord(
            artifact_id=artifact.id,
            source_artifact_id=version.image_artifact_id,
            source_sha256=hashlib.sha256(original).hexdigest(),
            width=size[0],
            height=size[1],
            source=source,
            score=score,
        )
        version.masks.append(record)
        await self._repository.save_version(version)
        return record

    async def prepare_local_crop(
        self,
        owner: str,
        session_id: str,
        version_id: str,
        mask_id: str,
        options: InpaintOptions,
    ) -> CropResult:
        """Prepare a crop and reject stale masks or spatial lock conflicts."""
        await self._owned_session(owner, session_id)
        parent = await self._ready_version(session_id, version_id)
        record = next((m for m in parent.masks if m.artifact_id == mask_id), None)
        if record is None:
            raise VersionNotReadyError("Mask 不属于当前父版本，请重新圈选或分割")
        original = await self._read_artifact(owner, parent.image_artifact_id)
        if hashlib.sha256(original).hexdigest() != record.source_sha256:
            raise VersionNotReadyError("Mask 的源图已变化，请重新确认")
        mask = await self._read_artifact(owner, mask_id)
        crop = await asyncio.to_thread(inpaint_crop, original, mask, options)
        prepared = prepare_mask(mask, crop.stitcher.source_size, options)
        width, height = crop.stitcher.source_size
        conflicts = []
        for entity in parent.entities:
            if entity.status != EntityStatus.LOCKED or entity.bbox is None:
                continue
            b = entity.bbox
            region = (
                int(b.x * width),
                int(b.y * height),
                int((b.x + b.w) * width + 0.999),
                int((b.y + b.h) * height + 0.999),
            )
            if prepared.hard.crop(region).getbbox():
                conflicts.append(entity)
        if conflicts:
            raise LockConflictError(conflicts)
        return crop

    async def segment_mask(
        self,
        owner: str,
        session_id: str,
        version_id: str,
        prompt: SegmentRequest,
    ) -> list[MaskRecord]:
        """Generate and persist candidate masks with an optional segmenter."""
        from app.controlled_edit.sam2_segmenter import segment_sam2
        from app.controlled_edit.sam3_client import segment_sam3

        await self._owned_session(owner, session_id)
        parent = await self._ready_version(session_id, version_id)
        image = await self._read_artifact(owner, parent.image_artifact_id)
        if prompt.provider == "sam2":
            candidates = await asyncio.to_thread(segment_sam2, image, prompt, self._config)
        else:
            candidates = await segment_sam3(image, prompt, self._config)
        records = []
        for data, score in candidates:
            with Image.open(io.BytesIO(data)) as decoded:
                if decoded.convert("L").getbbox() is None:
                    continue
            records.append(
                await self.save_mask(owner, session_id, version_id, data, prompt.provider, score)
            )
        if not records:
            raise ValueError("分割未产生有效 Mask，请调整框或提示点")
        return records

    async def preview_local_crop(
        self,
        owner: str,
        session_id: str,
        version_id: str,
        mask_id: str,
        options: InpaintOptions,
    ) -> dict[str, Any]:
        """Create owned preview artifacts without making a generation request."""
        crop = await self.prepare_local_crop(owner, session_id, version_id, mask_id, options)
        artifacts = [
            await self._artifacts.create_image(owner, data, "image/png")
            for data in (crop.image, crop.mask, crop.blend)
        ]
        return {
            "crop_artifact_id": artifacts[0].id,
            "mask_artifact_id": artifacts[1].id,
            "blend_artifact_id": artifacts[2].id,
            "stitcher": crop.stitcher.model_dump(mode="json"),
        }

    async def update_entity_bbox(
        self,
        owner_key_id: str,
        session_id: str,
        version_id: str,
        entity_id: str,
        bbox: BBox,
    ) -> EditVersion:
        """Replace one entity's box with a manual correction.

        A locked entity's anchor crop is re-cut with the new box from the version where
        it was locked, so prompt references and verification use the corrected region.

        Raises:
            SessionNotFoundError: Unknown session, version or entity.
            VersionNotReadyError: The version has not succeeded.
        """
        await self._owned_session(owner_key_id, session_id)
        version = await self._ready_version(session_id, version_id)
        entity = next((e for e in version.entities if e.id == entity_id), None)
        if entity is None:
            raise SessionNotFoundError(f"entity not found: {entity_id}")
        anchor_artifact_id: str | None = None
        if entity.status == EntityStatus.LOCKED:
            source = version
            if entity.anchor_version_id and entity.anchor_version_id != version.id:
                anchor_version = await self._repository.get_version(
                    session_id, entity.anchor_version_id
                )
                if anchor_version is not None and anchor_version.image_artifact_id:
                    source = anchor_version
            image_bytes = await self._read_artifact(owner_key_id, source.image_artifact_id)
            anchor = await self._artifacts.create_image(
                owner_key_id, crop_entity(image_bytes, bbox), "image/png"
            )
            anchor_artifact_id = anchor.id
        version.entities = with_manual_bbox(
            version.entities, entity_id, bbox, anchor_artifact_id=anchor_artifact_id
        )
        return await self._repository.save_version(version)

    async def checkout(self, owner_key_id: str, session_id: str, version_id: str) -> EditSession:
        """Move the session cursor to ``version_id`` without deleting anything."""
        session = await self._owned_session(owner_key_id, session_id)
        if await self._repository.get_version(session_id, version_id) is None:
            raise SessionNotFoundError(f"version not found: {version_id}")
        session.current_version_id = version_id
        return await self._repository.save_session(session)

    async def delete_version(
        self, owner_key_id: str, session_id: str, version_id: str
    ) -> SessionTree:
        """Delete a version and all of its descendants.

        The root (original image) cannot be deleted. Pending or running nodes in the
        subtree block deletion. When the session cursor lies inside the removed
        subtree, it moves to the deleted node's parent.

        Raises:
            SessionNotFoundError: Unknown session or version.
            VersionNotDeletableError: Root, busy subtree, or missing parent fallback.
        """
        session = await self._owned_session(owner_key_id, session_id)
        version = await self._repository.get_version(session_id, version_id)
        if version is None:
            raise SessionNotFoundError(f"version not found: {version_id}")
        if version.parent_id is None:
            raise VersionNotDeletableError("不能删除原图根节点")
        versions = await self._repository.list_versions(session_id)
        to_delete = _subtree_version_ids(versions, version_id)
        by_id = {item.id: item for item in versions}
        for deleted_id in to_delete:
            node = by_id.get(deleted_id)
            if node is not None and node.status in {
                VersionStatus.PENDING,
                VersionStatus.RUNNING,
            }:
                raise VersionNotDeletableError("生成中的版本不能删除，请等待完成或失败后再删")
        parent_id = version.parent_id
        if parent_id not in by_id or parent_id in to_delete:
            raise VersionNotDeletableError("找不到可回退的父节点")
        if session.current_version_id in to_delete:
            session.current_version_id = parent_id
            await self._repository.save_session(session)
        await self._repository.delete_versions(session_id, to_delete)
        return await self.get_tree(owner_key_id, session_id)

    async def read_owned_artifact(
        self, owner_key_id: str, artifact_id: str
    ) -> tuple[str, bytes] | None:
        """Return (media type, bytes) of an artifact owned by the caller."""
        found = await self._artifacts.read_owned(artifact_id, owner_key_id)
        if found is None:
            return None
        record, data = found
        return record.media_type, data

    async def _owned_session(self, owner_key_id: str, session_id: str) -> EditSession:
        session = await self._repository.get_session(session_id, owner_key_id)
        if session is None:
            raise SessionNotFoundError(f"session not found: {session_id}")
        return session

    async def _ready_version(self, session_id: str, version_id: str) -> EditVersion:
        version = await self._repository.get_version(session_id, version_id)
        if version is None:
            raise SessionNotFoundError(f"version not found: {version_id}")
        if version.status != VersionStatus.SUCCEEDED or version.image_artifact_id is None:
            raise VersionNotReadyError(
                f"version {version_id} is not ready ({version.status.value})"
            )
        return version

    async def _read_artifact(self, owner_key_id: str, artifact_id: str | None) -> bytes:
        if artifact_id is None:
            raise SessionNotFoundError("artifact id is missing")
        found = await self._artifacts.read_owned(artifact_id, owner_key_id)
        if found is None:
            raise SessionNotFoundError(f"artifact not found: {artifact_id}")
        return found[1]

    def _max_references(self, layout: str) -> int:
        """Qwen accepts at most two references plus the image being edited."""
        limit = self._config.cedit_max_reference_images
        if layout == "primary_last":
            return min(2, limit)
        return limit

    async def _set_step(
        self,
        version: EditVersion,
        step: str,
        status: VersionStatus | None = None,
    ) -> None:
        version.progress_step = step
        if status is not None:
            version.status = status
        await self._repository.save_version(version)


_service: ControlledEditService | None = None


def get_controlled_edit_service() -> ControlledEditService:
    """Return the process-wide service wired to the configured vision and image models."""
    global _service
    if _service is None:
        from app.controlled_edit.vision import VisionClient, scene_vision_client

        _service = ControlledEditService(
            repository=get_edit_repository(),
            artifacts=get_artifact_service(),
            vision_factory=VisionClient,
            editor_factory=_cedit_editor_factory,
            scene_vision_factory=scene_vision_client,
        )
    return _service


def _wanx_mask_available(config: Settings) -> bool:
    return bool(config.dashscope_api_key.strip())


def _assert_editor_available(provider: str, config: Settings) -> None:
    """Raise when the chosen image editor cannot run with current credentials."""
    if provider == "dashscope":
        if not config.dashscope_api_key.strip():
            raise EditorUnavailableError("未配置阿里云 API Key，无法使用通义改图")
        return
    if provider == "openai":
        if not config.openai_api_key.strip():
            raise EditorUnavailableError("未配置 OpenAI API Key，无法使用 gpt-image 改图")
        return
    raise EditorUnavailableError(f"不支持的生图后端：{provider}")


def _cedit_editor_factory(provider: str | None = None) -> ImageEditor:
    """Build an image editor for ``provider``, or the settings default."""
    from app.pipeline.image_providers.dashscope_qwen_edit import (
        DashScopeQwenEditProvider,
    )
    from app.pipeline.image_providers.openai_images import OpenAIImageProvider

    chosen = provider or settings.cedit_image_provider
    _assert_editor_available(chosen, settings)
    if chosen == "dashscope":
        return DashScopeQwenEditProvider()
    return OpenAIImageProvider()
