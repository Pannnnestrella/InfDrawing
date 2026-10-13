"""Orchestration of controlled-edit sessions, turns, and entity locks."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import io
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Literal, Protocol

import httpx
from PIL import Image, ImageDraw, ImageOps

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
from app.controlled_edit.masks import PreparedMask, png_bytes, prepare_mask
from app.controlled_edit.prompt_compiler import compile_edit_prompt
from app.controlled_edit.alpha import (
    flatten_for_model,
    has_meaningful_alpha,
    match_source_size,
    reattach_alpha,
)
from app.controlled_edit.image_models import QWEN_EDIT_MODELS, WAN27_MODELS
from app.controlled_edit.qwen_mask_prompt import (
    qwen_fullframe_alpha_clause,
    wants_transparency,
)
from app.controlled_edit.region_ops import (
    build_edit_mask,
    framing_drift,
    lock_composite,
    mask_png_bytes,
    target_pixel_bboxes,
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
    SentImage,
    SessionTree,
    VerificationResult,
    VersionStatus,
)
from app.controlled_edit.segmentation import SegmentRequest
from app.controlled_edit.sizing import pad_to_supported, restore_original_frame
# match_source_size lives in alpha.py (RGBA-aware)
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


class SessionNotDeletableError(ValueError):
    """Raised when a session cannot be deleted (busy versions)."""


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
        editor_factory: Callable[..., ImageEditor],
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
        *,
        run_in_background: bool = True,
        extra_reference_artifact_ids: list[str] | None = None,
    ) -> EditVersion:
        """Parse the instruction, reject lock conflicts, and schedule generation.

        When ``run_in_background`` is False the turn is awaited and the returned
        version reflects the final status (used by workflow runner).

        Raises:
            SessionNotFoundError: Unknown session or parent version.
            VersionNotReadyError: The parent version has not succeeded.
            LockConflictError: The instruction targets locked entities.
        """
        session = await self._owned_session(owner_key_id, session_id)
        parent = await self._ready_version(session_id, request.parent_version_id)
        if request.edit_mode == "local":
            if request.image_provider == "openai":
                raise EditorUnavailableError("局部 Mask 编辑当前使用万相，请选择通义提供商")
            if self._config.dashscope_edit_model != request.inpaint_options.model:
                raise EditorUnavailableError("局部重绘模型与服务器配置不一致")
            mask_id = request.mask_artifact_id or ""
            if request.inpaint_options.placement == "fullframe":
                await self.prepare_local_fullframe(
                    owner_key_id, session_id, parent.id, mask_id, request.inpaint_options
                )
            else:
                await self.prepare_local_crop(
                    owner_key_id, session_id, parent.id, mask_id, request.inpaint_options
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
        image_model = None if request.edit_mode == "local" else _resolve_image_model(
            image_provider, request.image_model, self._config
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
            image_model=image_model,
            width=parent.width,
            height=parent.height,
            entities=[e.model_copy() for e in parent.entities],
            reference_artifact_ids=list(extra_reference_artifact_ids or []),
            local_edit=LocalTurnFields(
                edit_mode=request.edit_mode,
                mask_artifact_id=request.mask_artifact_id,
                inpaint_options=request.inpaint_options,
            ),
        )
        await self._repository.add_version(child)
        session.current_version_id = child.id
        await self._repository.save_session(session)
        if run_in_background:
            self._schedule(self.run_turn(owner_key_id, session_id, child.id))
            return child
        await self.run_turn(owner_key_id, session_id, child.id)
        finished = await self._repository.get_version(session_id, child.id)
        return finished if finished is not None else child

    async def create_passthrough_version(
        self,
        owner_key_id: str,
        session_id: str,
        *,
        parent_version_id: str,
        input_version_ids: list[str],
        reference_artifact_ids: list[str] | None = None,
        instruction: str = "[workflow:merge]",
    ) -> EditVersion:
        """Create a succeeded version that reuses the primary parent's image.

        Used by workflow merge nodes so the version tree stays singly-parented
        while ``input_version_ids`` records every merge source.
        """
        session = await self._owned_session(owner_key_id, session_id)
        parent = await self._ready_version(session_id, parent_version_id)
        child = EditVersion(
            session_id=session_id,
            parent_id=parent.id,
            input_version_ids=list(input_version_ids),
            status=VersionStatus.SUCCEEDED,
            image_artifact_id=parent.image_artifact_id,
            width=parent.width,
            height=parent.height,
            instruction=instruction,
            prompt_style=parent.prompt_style,
            image_provider=parent.image_provider,
            image_model=parent.image_model,
            reference_artifact_ids=list(reference_artifact_ids or []),
            entities=[e.model_copy(deep=True) for e in parent.entities],
        )
        await self._repository.add_version(child)
        session.current_version_id = child.id
        await self._repository.save_session(session)
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
        image_model = version.image_model or (
            self._config.cedit_image_model if image_provider == "dashscope" else None
        )
        prompt_style = version.prompt_style or self._config.cedit_prompt_style
        explicit_local = bool(version.local_edit and version.local_edit.edit_mode == "local")
        auto_local = bool(
            not explicit_local
            and not (version.local_edit and version.local_edit.edit_mode == "full")
            and uses_local_mask(version.intent, parent.entities)
            and _wanx_mask_available(self._config)
        )
        auto_engine = (self._config.cedit_auto_local_engine or "wan27_bbox").strip()
        use_wan27_bbox = auto_local and auto_engine == "wan27_bbox"
        use_wanx_mask = explicit_local or (auto_local and auto_engine == "wanx21_mask")
        editor = (
            None
            if explicit_local or use_wan27_bbox
            else self._editor_factory(image_provider, image_model)
        )
        vision = self._vision_factory()
        layout = getattr(editor, "prompt_image_layout", "primary_first")
        max_refs = self._max_references(layout)

        max_attempts = 1 + max(0, self._config.cedit_max_retries)
        feedback: str | None = None
        parsed_entities: list[SceneEntity] | None = None
        parse_warnings: list[str] = []
        crop = None
        fullframe_mask_bytes: bytes | None = None
        fullframe_mask_id: str | None = None
        if explicit_local and version.local_edit:
            options = version.local_edit.inpaint_options
            if options.placement == "fullframe":
                prepared = await self.prepare_local_fullframe(
                    owner_key_id,
                    version.session_id,
                    parent.id,
                    version.local_edit.mask_artifact_id or "",
                    options,
                )
                gen_mask = await self._artifacts.create_image(
                    owner_key_id, mask_png_bytes(prepared.hard), "image/png"
                )
                fullframe_mask_bytes = mask_png_bytes(prepared.hard)
                fullframe_mask_id = gen_mask.id
            else:
                crop = await self.prepare_local_crop(
                    owner_key_id,
                    version.session_id,
                    parent.id,
                    version.local_edit.mask_artifact_id or "",
                    options,
                )
                crop_artifact = await self._artifacts.create_image(
                    owner_key_id, crop.image, "image/png"
                )
                gen_mask = await self._artifacts.create_image(
                    owner_key_id, crop.mask, "image/png"
                )
                blend = await self._artifacts.create_image(
                    owner_key_id, crop.blend, "image/png"
                )
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
            lock_refs = [
                e
                for e in compiled.reference_entities
                if e.anchor_artifact_id
            ]
            version.reference_artifact_ids = (
                []
                if explicit_local
                else [e.anchor_artifact_id for e in lock_refs if e.anchor_artifact_id]
            )
            await self._set_step(version, "generating" if attempt == 1 else "retrying")
            parent_has_alpha = has_meaningful_alpha(parent_bytes)
            instruction_text = version.instruction or (
                version.intent.change_description if version.intent else ""
            )
            allow_alpha = wants_transparency(
                instruction_text, parent_has_alpha=parent_has_alpha
            )
            use_qwen_editor = (
                image_provider == "dashscope"
                and image_model is not None
                and image_model in QWEN_EDIT_MODELS
            )
            padded = pad_to_supported(
                parent_bytes, keep_alpha=allow_alpha if use_qwen_editor else False
            )
            alpha_support: bytes | None = None
            if use_wanx_mask:
                if "local_mask:wanx" not in version.warnings:
                    version.warnings.append("local_mask:wanx")
                from app.pipeline.image_providers.dashscope_wanx import (
                    DashScopeWanxProvider,
                )

                base_prompt = instruction_text
                feedback_text = f"修正上次问题：{feedback[:300]}。" if feedback else ""
                wanx_prompt = (feedback_text + base_prompt)[:800]
                version.compiled_prompt = wanx_prompt
                if crop and version.stitcher:
                    mask_bytes = crop.mask
                    image_bytes = (
                        flatten_for_model(crop.image)
                        if has_meaningful_alpha(crop.image)
                        else crop.image
                    )
                    primary_id = version.stitcher.crop_artifact_id or parent.image_artifact_id
                    mask_id = version.stitcher.generation_mask_artifact_id
                    primary_role_lit: Literal["primary", "crop"] = "crop"
                    primary_label = "裁剪图（发给万相 2.1 Legacy）"
                    alpha_support = crop.blend
                elif fullframe_mask_bytes and fullframe_mask_id:
                    mask_bytes = fullframe_mask_bytes
                    image_bytes = flatten_for_model(parent_bytes)
                    primary_id = parent.image_artifact_id
                    mask_id = fullframe_mask_id
                    primary_role_lit = "primary"
                    primary_label = "整图 + Mask（万相 2.1 Legacy，不裁剪）"
                    alpha_support = fullframe_mask_bytes
                else:
                    with Image.open(io.BytesIO(parent_bytes)) as parent_im:
                        size = parent_im.size
                    mask = build_edit_mask(
                        size,
                        parent.entities,
                        version.intent.target_entity_ids,
                        unconstrained="keep",
                    )
                    mask_bytes = mask_png_bytes(mask)
                    image_bytes = flatten_for_model(parent_bytes)
                    mask_artifact = await self._artifacts.create_image(
                        owner_key_id, mask_bytes, "image/png"
                    )
                    primary_id = parent.image_artifact_id
                    mask_id = mask_artifact.id
                    primary_role_lit = "primary"
                    primary_label = "整图 + 矩形 Mask（万相 2.1 Legacy）"
                    alpha_support = mask_bytes
                if parent_has_alpha:
                    primary_label += " · 区外保留透明"
                version.sent_images = _wanx_sent_images(
                    primary_id=primary_id or "",
                    primary_role=primary_role_lit,
                    primary_label=primary_label,
                    mask_id=mask_id or "",
                    lock_refs=lock_refs,
                )
                raw = await _with_transport_retries(
                    functools.partial(
                        DashScopeWanxProvider(self._config).inpaint,
                        image_bytes=image_bytes,
                        mask_bytes=mask_bytes,
                        prompt=wanx_prompt,
                    )
                )
                candidate = raw
            elif use_wan27_bbox:
                if "local_bbox:wan27" not in version.warnings:
                    version.warnings.append("local_bbox:wan27")
                from app.pipeline.image_providers.dashscope_wan27_edit import (
                    DashScopeWan27EditProvider,
                )

                with Image.open(io.BytesIO(parent_bytes)) as parent_im:
                    size = parent_im.size
                boxes = target_pixel_bboxes(
                    size, parent.entities, version.intent.target_entity_ids, max_boxes=2
                )
                if not boxes:
                    raise EditorUnavailableError("自动局部缺少有效目标框，请改用整图或 Mask")
                base_prompt = instruction_text
                feedback_text = f"修正上次问题：{feedback[:300]}。" if feedback else ""
                wan_prompt = (
                    feedback_text
                    + base_prompt
                    + "仅修改框选区域，保持其余像素、油画笔触与光照一致。"
                )[:5000]
                version.compiled_prompt = wan_prompt
                label = (
                    f"整图 + Wan 2.7 bbox "
                    f"({self._config.cedit_auto_local_model}; {boxes})"
                )
                if parent_has_alpha:
                    label += " · 区外保留透明"
                version.sent_images = [
                    SentImage(
                        role="primary",
                        artifact_id=parent.image_artifact_id or "",
                        index=1,
                        label=label,
                        sent=True,
                    )
                ]
                for entity in lock_refs:
                    if not entity.anchor_artifact_id:
                        continue
                    version.sent_images.append(
                        SentImage(
                            role="reference",
                            artifact_id=entity.anchor_artifact_id,
                            label=f"锁定锚点 {entity.name}（未发送）",
                            sent=False,
                        )
                    )
                wan27 = DashScopeWan27EditProvider(
                    self._config, model=self._config.cedit_auto_local_model
                )
                send_bytes = (
                    flatten_for_model(parent_bytes) if parent_has_alpha else parent_bytes
                )
                raw = await _with_transport_retries(
                    functools.partial(
                        wan27.multi_image_edit,
                        image_bytes=send_bytes,
                        reference_images=[],
                        prompt=wan_prompt,
                        size="2K",
                        bbox_list=[boxes],
                    )
                )
                candidate = match_source_size(raw, parent_bytes)
                alpha_support = _boxes_to_support_mask(size, boxes)
            else:
                assert editor is not None
                full_prompt = compiled.prompt
                if use_qwen_editor:
                    full_prompt = compiled.prompt + qwen_fullframe_alpha_clause(
                        allow_alpha=allow_alpha
                    )
                    version.compiled_prompt = full_prompt
                version.sent_images = _fullframe_sent_images(
                    parent_image_id=parent.image_artifact_id or "",
                    lock_refs=lock_refs,
                    image_layout=layout,
                )
                if allow_alpha and use_qwen_editor:
                    for item in version.sent_images:
                        if item.role == "primary":
                            item.label = (item.label or "整图") + " · 允许透明 PNG"
                edit_kwargs: dict[str, Any] = {
                    "image_bytes": padded.png,
                    "reference_images": references,
                    "prompt": full_prompt,
                    "size": padded.size if image_model not in WAN27_MODELS else "2K",
                    "input_fidelity": self._config.cedit_input_fidelity or None,
                }
                if image_model in WAN27_MODELS:
                    edit_kwargs["image_bytes"] = (
                        flatten_for_model(parent_bytes)
                        if parent_has_alpha
                        else parent_bytes
                    )
                    edit_kwargs["size"] = "2K"
                raw = await _with_transport_retries(
                    functools.partial(editor.multi_image_edit, **edit_kwargs)
                )
                candidate = (
                    match_source_size(raw, parent_bytes)
                    if image_model in WAN27_MODELS
                    else restore_original_frame(raw, padded)
                )
                if image_model in WAN27_MODELS and parent_has_alpha:
                    alpha_support = None  # full-frame wan: reattach parent alpha everywhere
            if crop and version.stitcher:
                candidate = await asyncio.to_thread(
                    inpaint_stitch, parent_bytes, raw, crop.blend, version.stitcher
                )
                version.stitcher = version.stitcher.model_copy(
                    update={"actual_output_size": _image_size(raw)}
                )
            elif parent_has_alpha and not (
                use_qwen_editor and has_meaningful_alpha(candidate)
            ):
                # Wan/Wanx (and opaque Qwen outputs): restore parent alpha outside support.
                candidate = reattach_alpha(parent_bytes, candidate, alpha_support)
            elif parent_has_alpha and use_qwen_editor and has_meaningful_alpha(candidate):
                if "rgba:qwen" not in version.warnings:
                    version.warnings.append("rgba:qwen")
            if self._config.cedit_lock_paste and not use_wanx_mask and not use_wan27_bbox:
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

    async def _bound_prepared_mask(
        self,
        owner: str,
        session_id: str,
        version_id: str,
        mask_id: str,
        options: InpaintOptions,
    ) -> tuple[bytes, bytes, PreparedMask]:
        """Load a version-bound mask, prepare it, and reject lock overlaps."""
        await self._owned_session(owner, session_id)
        parent = await self._ready_version(session_id, version_id)
        record = next((m for m in parent.masks if m.artifact_id == mask_id), None)
        if record is None:
            raise VersionNotReadyError("Mask 不属于当前父版本，请重新圈选或分割")
        original = await self._read_artifact(owner, parent.image_artifact_id)
        if hashlib.sha256(original).hexdigest() != record.source_sha256:
            raise VersionNotReadyError("Mask 的源图已变化，请重新确认")
        mask = await self._read_artifact(owner, mask_id)
        with Image.open(io.BytesIO(original)) as source:
            size = source.size
        prepared = await asyncio.to_thread(prepare_mask, mask, size, options)
        width, height = size
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
        return original, mask, prepared

    async def prepare_local_crop(
        self,
        owner: str,
        session_id: str,
        version_id: str,
        mask_id: str,
        options: InpaintOptions,
    ) -> CropResult:
        """Prepare a crop and reject stale masks or spatial lock conflicts."""
        original, mask, _prepared = await self._bound_prepared_mask(
            owner, session_id, version_id, mask_id, options
        )
        return await asyncio.to_thread(inpaint_crop, original, mask, options)

    async def prepare_local_fullframe(
        self,
        owner: str,
        session_id: str,
        version_id: str,
        mask_id: str,
        options: InpaintOptions,
    ) -> PreparedMask:
        """Prepare a source-space mask for full-frame Wanx without cropping."""
        _original, _mask, prepared = await self._bound_prepared_mask(
            owner, session_id, version_id, mask_id, options
        )
        return prepared

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
        if options.placement == "fullframe":
            original, _mask, prepared = await self._bound_prepared_mask(
                owner, session_id, version_id, mask_id, options
            )
            with Image.open(io.BytesIO(original)) as source:
                rgb = source.convert("RGB")
                size = rgb.size
                tint = Image.blend(rgb, Image.new("RGB", size, (50, 150, 255)), 0.55)
                overlay = Image.composite(tint, rgb, prepared.hard)
            artifacts = [
                await self._artifacts.create_image(owner, data, "image/png")
                for data in (
                    png_bytes(overlay),
                    mask_png_bytes(prepared.hard),
                    png_bytes(prepared.blend),
                )
            ]
            width, height = size
            return {
                "crop_artifact_id": artifacts[0].id,
                "mask_artifact_id": artifacts[1].id,
                "blend_artifact_id": artifacts[2].id,
                "placement": "fullframe",
                "stitcher": {
                    "crop_rect": [0, 0, width, height],
                    "model_size": [width, height],
                    "mask_bbox": list(prepared.bbox),
                },
            }
        crop = await self.prepare_local_crop(owner, session_id, version_id, mask_id, options)
        artifacts = [
            await self._artifacts.create_image(owner, data, "image/png")
            for data in (crop.image, crop.mask, crop.blend)
        ]
        return {
            "crop_artifact_id": artifacts[0].id,
            "mask_artifact_id": artifacts[1].id,
            "blend_artifact_id": artifacts[2].id,
            "placement": "crop",
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

    async def rename_version(
        self, owner_key_id: str, session_id: str, version_id: str, title: str
    ) -> EditVersion:
        """Set or clear the display title of one version node.

        Empty / whitespace titles clear the custom name so the UI falls back to
        ``原图`` or the instruction summary.
        """
        await self._owned_session(owner_key_id, session_id)
        version = await self._repository.get_version(session_id, version_id)
        if version is None:
            raise SessionNotFoundError(f"version not found: {version_id}")
        cleaned = title.strip()[:40]
        version.title = cleaned or None
        return await self._repository.save_version(version)

    async def rename_session(self, owner_key_id: str, session_id: str, title: str) -> EditSession:
        """Rename an owned session."""
        session = await self._owned_session(owner_key_id, session_id)
        cleaned = title.strip()[:120]
        if not cleaned:
            raise ValueError("会话标题不能为空")
        session.title = cleaned
        return await self._repository.save_session(session)

    async def delete_session(self, owner_key_id: str, session_id: str) -> None:
        """Delete a session and all of its version records.

        Image artifacts on disk are kept (same policy as version deletion).
        Pending or running versions block deletion.

        Raises:
            SessionNotFoundError: Unknown session.
            SessionNotDeletableError: A version is still pending or running.
        """
        await self._owned_session(owner_key_id, session_id)
        versions = await self._repository.list_versions(session_id)
        for version in versions:
            if version.status in {VersionStatus.PENDING, VersionStatus.RUNNING}:
                raise SessionNotDeletableError("生成中的会话不能删除，请等待完成或失败后再删")
        await self._repository.delete_session(session_id)

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


def _boxes_to_support_mask(
    size: tuple[int, int], boxes: list[list[int]]
) -> bytes:
    """Build a binary PNG mask covering pixel bboxes (white = editable support)."""
    width, height = size
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for box in boxes:
        if len(box) != 4:
            continue
        x0, y0, x1, y1 = (int(v) for v in box)
        x0, x1 = max(0, min(x0, x1)), min(width, max(x0, x1))
        y0, y1 = max(0, min(y0, y1)), min(height, max(y0, y1))
        if x1 > x0 and y1 > y0:
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)
    return png_bytes(mask)


def _wanx_sent_images(
    *,
    primary_id: str,
    primary_role: Literal["primary", "crop"],
    primary_label: str,
    mask_id: str,
    lock_refs: list[SceneEntity],
) -> list[SentImage]:
    """Describe the Wanx payload plus lock anchors that were not sent."""
    images = [
        SentImage(
            role=primary_role,
            artifact_id=primary_id,
            index=1,
            label=primary_label,
            sent=True,
        ),
        SentImage(
            role="mask",
            artifact_id=mask_id,
            label="Mask（白=改 / 黑=留，发给万相）",
            sent=True,
        ),
    ]
    for entity in lock_refs:
        if not entity.anchor_artifact_id:
            continue
        images.append(
            SentImage(
                role="reference",
                artifact_id=entity.anchor_artifact_id,
                label=f"锁定锚点 {entity.name}（未发送，仅身份/验收）",
                sent=False,
            )
        )
    return images


def _fullframe_sent_images(
    *,
    parent_image_id: str,
    lock_refs: list[SceneEntity],
    image_layout: str,
) -> list[SentImage]:
    """Describe Qwen/OpenAI multi-image edit payloads with prompt numbering."""
    images: list[SentImage] = []
    if image_layout == "primary_last":
        for index, entity in enumerate(lock_refs, start=1):
            if not entity.anchor_artifact_id:
                continue
            images.append(
                SentImage(
                    role="reference",
                    artifact_id=entity.anchor_artifact_id,
                    index=index,
                    label=f"参考图 {index} · {entity.name}",
                    sent=True,
                )
            )
        primary_index = len(lock_refs) + 1
        images.append(
            SentImage(
                role="primary",
                artifact_id=parent_image_id,
                index=primary_index,
                label=f"当前整图（图 {primary_index}，发给模型）",
                sent=True,
            )
        )
        return images
    images.append(
        SentImage(
            role="primary",
            artifact_id=parent_image_id,
            index=1,
            label="当前整图（图 1，发给模型）",
            sent=True,
        )
    )
    for index, entity in enumerate(lock_refs, start=2):
        if not entity.anchor_artifact_id:
            continue
        images.append(
            SentImage(
                role="reference",
                artifact_id=entity.anchor_artifact_id,
                index=index,
                label=f"参考图 {index} · {entity.name}",
                sent=True,
            )
        )
    return images


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


def _resolve_image_model(
    provider: str, requested: str | None, config: Settings
) -> str | None:
    """Normalize the per-turn image model for full-frame editors."""
    from app.controlled_edit.image_models import DASHSCOPE_FULLFRAME_MODELS

    if provider == "openai":
        return (requested or config.openai_image_model).strip() or config.openai_image_model
    if provider != "dashscope":
        return None
    model = (requested or config.cedit_image_model).strip()
    allowed = set(DASHSCOPE_FULLFRAME_MODELS) | {config.cedit_image_model, *QWEN_EDIT_MODELS}
    if model not in allowed:
        raise EditorUnavailableError(f"不支持的通义整图模型：{model}")
    return model


def _cedit_editor_factory(
    provider: str | None = None, model: str | None = None
) -> ImageEditor:
    """Build an image editor for ``provider``, or the settings default."""
    from app.pipeline.image_providers.dashscope_qwen_edit import (
        DashScopeQwenEditProvider,
    )
    from app.pipeline.image_providers.dashscope_wan27_edit import (
        DashScopeWan27EditProvider,
    )
    from app.pipeline.image_providers.openai_images import OpenAIImageProvider

    chosen = provider or settings.cedit_image_provider
    _assert_editor_available(chosen, settings)
    if chosen == "dashscope":
        resolved = _resolve_image_model("dashscope", model, settings)
        if resolved in WAN27_MODELS:
            return DashScopeWan27EditProvider(model=resolved)
        return DashScopeQwenEditProvider(model=resolved)
    return OpenAIImageProvider()
