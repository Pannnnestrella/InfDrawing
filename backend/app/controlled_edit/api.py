"""HTTP API for controlled multi-turn editing (mounted behind ``controlled_edit`` scope)."""

from __future__ import annotations

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, Response
from PIL import UnidentifiedImageError
from pydantic import BaseModel, Field

from app.config import settings
from app.controlled_edit.entities import InheritedLockError
from app.controlled_edit.inpaint_types import InpaintOptions, MaskRecord
from app.controlled_edit.intent_parser import IntentParseError
from app.controlled_edit.sam2_segmenter import sam2_ready
from app.controlled_edit.scene_parser import SceneParseError
from app.controlled_edit.schemas import (
    CheckoutRequest,
    EditSession,
    EditTurnRequest,
    EditVersion,
    EntityBBoxUpdate,
    EntityStatusUpdate,
    SessionTitleUpdate,
    SessionTree,
    VersionTitleUpdate,
)
from app.controlled_edit.segmentation import (
    SegmentationUnavailableError,
    SegmentRequest,
)
from app.controlled_edit.service import (
    ControlledEditService,
    EditorUnavailableError,
    LockConflictError,
    SessionNotDeletableError,
    SessionNotFoundError,
    VersionNotDeletableError,
    VersionNotReadyError,
    get_controlled_edit_service,
)
from app.controlled_edit.vision import VisionError
from app.pipeline.image_providers.base import ImageProviderError
from app.production.auth import ApiPrincipal, current_principal
from app.production.http import error_response
from app.production.telemetry import record_audit

router = APIRouter(prefix="/controlled-edit", tags=["controlled-edit"])


def require_openai_configured() -> None:
    """Fail fast when the feature's only provider is not configured."""
    if not settings.openai_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key is not configured (controlled edit requires OpenAI)",
        )


def _service() -> ControlledEditService:
    return get_controlled_edit_service()


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, SessionNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(
        exc,
        (
            VersionNotReadyError,
            VersionNotDeletableError,
            SessionNotDeletableError,
            EditorUnavailableError,
        ),
    ):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}"[:500])


_UPSTREAM_ERRORS = (VisionError, SceneParseError, IntentParseError, ImageProviderError)


class PreviewRequest(BaseModel):
    """Server-owned mask reference and local preprocessing options."""

    mask_artifact_id: str
    options: InpaintOptions = Field(default_factory=InpaintOptions)


@router.get("/segmentation-capabilities")
async def segmentation_capabilities(
    principal: ApiPrincipal = Depends(current_principal),
) -> dict[str, bool]:
    """Report optional setup availability without claiming tested inference."""
    return {"sam2": sam2_ready(settings), "sam3": bool(settings.cedit_sam3_base_url)}


@router.post("/sessions/{session_id}/versions/{version_id}/masks", response_model=MaskRecord)
async def upload_mask(
    session_id: str,
    version_id: str,
    mask: UploadFile = File(...),
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> MaskRecord:
    """Upload a source-resolution grayscale mask for a specific version."""
    data = await mask.read(10_000_001)
    if len(data) > 10_000_000:
        raise HTTPException(413, "Mask 文件超过 10MB")
    try:
        return await service.save_mask(principal.key_id, session_id, version_id, data)
    except (SessionNotFoundError, VersionNotReadyError) as exc:
        raise _translate(exc) from exc
    except (ValueError, UnidentifiedImageError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/sessions/{session_id}/versions/{version_id}/segment")
async def segment_mask(
    session_id: str,
    version_id: str,
    prompt: SegmentRequest,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> list[MaskRecord]:
    """Produce selectable irregular masks through SAM 2 or a SAM 3 service."""
    try:
        return await service.segment_mask(principal.key_id, session_id, version_id, prompt)
    except SegmentationUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"SAM 服务请求失败：{type(exc).__name__}") from exc
    except (SessionNotFoundError, VersionNotReadyError) as exc:
        raise _translate(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/sessions/{session_id}/versions/{version_id}/inpaint-preview")
async def inpaint_preview(
    session_id: str,
    version_id: str,
    request: PreviewRequest,
    http_request: Request,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> JSONResponse:
    """Prepare protected crop artifacts without invoking a generation model."""
    try:
        preview = await service.preview_local_crop(
            principal.key_id, session_id, version_id, request.mask_artifact_id, request.options
        )
    except LockConflictError as exc:
        return error_response(
            getattr(http_request.state, "request_id", ""),
            409,
            "lock_conflict",
            str(exc),
            details={"entities": [{"id": e.id, "name": e.name} for e in exc.entities]},
        )
    except (SessionNotFoundError, VersionNotReadyError) as exc:
        raise _translate(exc) from exc
    except (ValueError, UnidentifiedImageError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return JSONResponse(preview)


@router.post(
    "/sessions",
    response_model=SessionTree,
    status_code=201,
    dependencies=[Depends(require_openai_configured)],
)
async def create_session(
    image: UploadFile = File(...),
    title: str = Form("Untitled"),
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> SessionTree:
    """Upload a source image, parse its scene, and create the root version."""
    data = await image.read()
    try:
        tree = await service.create_session(principal.key_id, data, image.content_type or "", title)
    except _UPSTREAM_ERRORS as exc:
        raise _translate(exc) from exc
    await record_audit(
        principal.key_id,
        "controlled_edit.create_session",
        "edit_session",
        tree.session.id,
        details={"entities": len(tree.versions[0].entities)},
    )
    return tree


@router.get("/sessions", response_model=list[EditSession])
async def list_sessions(
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> list[EditSession]:
    """List the caller's sessions, newest first."""
    return await service.list_sessions(principal.key_id)


@router.get("/sessions/{session_id}", response_model=SessionTree)
async def get_session(
    session_id: str,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> SessionTree:
    """Return a session with its full version tree."""
    try:
        return await service.get_tree(principal.key_id, session_id)
    except SessionNotFoundError as exc:
        raise _translate(exc) from exc


@router.patch("/sessions/{session_id}", response_model=EditSession)
async def rename_session(
    session_id: str,
    body: SessionTitleUpdate,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> EditSession:
    """Rename an owned session."""
    try:
        return await service.rename_session(principal.key_id, session_id, body.title)
    except SessionNotFoundError as exc:
        raise _translate(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> None:
    """Delete a session and all of its version records (artifacts kept on disk)."""
    try:
        await service.delete_session(principal.key_id, session_id)
    except (SessionNotFoundError, SessionNotDeletableError) as exc:
        raise _translate(exc) from exc
    await record_audit(
        principal.key_id,
        "controlled_edit.delete_session",
        "edit_session",
        session_id,
    )


@router.patch(
    "/sessions/{session_id}/versions/{version_id}",
    response_model=EditVersion,
)
async def rename_version(
    session_id: str,
    version_id: str,
    body: VersionTitleUpdate,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> EditVersion:
    """Set or clear the display title of one version node."""
    try:
        return await service.rename_version(
            principal.key_id, session_id, version_id, body.title
        )
    except SessionNotFoundError as exc:
        raise _translate(exc) from exc


@router.post(
    "/sessions/{session_id}/turns",
    response_model=EditVersion,
    status_code=202,
    dependencies=[Depends(require_openai_configured)],
)
async def submit_turn(
    session_id: str,
    body: EditTurnRequest,
    request: Request,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> EditVersion | JSONResponse:
    """Submit one edit instruction; generation continues in the background."""
    try:
        version = await service.submit_turn(principal.key_id, session_id, body)
    except LockConflictError as exc:
        return error_response(
            getattr(request.state, "request_id", "unknown"),
            409,
            "lock_conflict",
            str(exc),
            {"entities": [{"id": e.id, "name": e.name} for e in exc.entities]},
        )
    except (ValueError, UnidentifiedImageError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except (
        SessionNotFoundError,
        VersionNotReadyError,
        EditorUnavailableError,
        *_UPSTREAM_ERRORS,
    ) as exc:
        raise _translate(exc) from exc
    await record_audit(
        principal.key_id,
        "controlled_edit.submit_turn",
        "edit_version",
        version.id,
        details={"session_id": session_id},
    )
    return version


@router.post(
    "/sessions/{session_id}/versions/{version_id}/entities/{entity_id}/status",
    response_model=EditVersion,
)
async def update_entity_status(
    session_id: str,
    version_id: str,
    entity_id: str,
    body: EntityStatusUpdate,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> EditVersion:
    """Lock, approve, or unlock one entity of a version."""
    try:
        return await service.update_entity_status(
            principal.key_id, session_id, version_id, entity_id, body.status
        )
    except InheritedLockError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (SessionNotFoundError, VersionNotReadyError) as exc:
        raise _translate(exc) from exc


@router.put(
    "/sessions/{session_id}/versions/{version_id}/entities/{entity_id}/bbox",
    response_model=EditVersion,
)
async def update_entity_bbox(
    session_id: str,
    version_id: str,
    entity_id: str,
    body: EntityBBoxUpdate,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> EditVersion:
    """Manually correct one entity's bounding box (normalized 0-1 coordinates)."""
    try:
        return await service.update_entity_bbox(
            principal.key_id, session_id, version_id, entity_id, body.bbox
        )
    except (SessionNotFoundError, VersionNotReadyError) as exc:
        raise _translate(exc) from exc


@router.post("/sessions/{session_id}/checkout", response_model=EditSession)
async def checkout(
    session_id: str,
    body: CheckoutRequest,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> EditSession:
    """Move the session cursor to another version."""
    try:
        return await service.checkout(principal.key_id, session_id, body.version_id)
    except SessionNotFoundError as exc:
        raise _translate(exc) from exc


@router.delete(
    "/sessions/{session_id}/versions/{version_id}",
    response_model=SessionTree,
)
async def delete_version(
    session_id: str,
    version_id: str,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> SessionTree:
    """Delete a version node and all of its descendants."""
    try:
        tree = await service.delete_version(principal.key_id, session_id, version_id)
    except (SessionNotFoundError, VersionNotDeletableError) as exc:
        raise _translate(exc) from exc
    await record_audit(
        principal.key_id,
        "controlled_edit.delete_version",
        "edit_version",
        version_id,
        details={"session_id": session_id},
    )
    return tree


@router.get("/artifacts/{artifact_id}")
async def get_artifact_content(
    artifact_id: str,
    principal: ApiPrincipal = Depends(current_principal),
    service: ControlledEditService = Depends(_service),
) -> Response:
    """Serve an owned image so this feature works without the ``artifacts:read`` scope."""
    found = await service.read_owned_artifact(principal.key_id, artifact_id)
    if found is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    media_type, data = found
    return Response(data, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})
