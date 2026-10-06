"""HTTP API for controlled multi-turn editing (mounted behind ``controlled_edit`` scope)."""

from __future__ import annotations

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

from app.config import settings
from app.controlled_edit.entities import InheritedLockError
from app.controlled_edit.intent_parser import IntentParseError
from app.controlled_edit.scene_parser import SceneParseError
from app.controlled_edit.schemas import (
    CheckoutRequest,
    EditSession,
    EditTurnRequest,
    EditVersion,
    EntityBBoxUpdate,
    EntityStatusUpdate,
    SessionTree,
)
from app.controlled_edit.service import (
    ControlledEditService,
    EditorUnavailableError,
    LockConflictError,
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
        exc, (VersionNotReadyError, VersionNotDeletableError, EditorUnavailableError)
    ):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}"[:500])


_UPSTREAM_ERRORS = (VisionError, SceneParseError, IntentParseError, ImageProviderError)


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
        tree = await service.create_session(
            principal.key_id, data, image.content_type or "", title
        )
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
