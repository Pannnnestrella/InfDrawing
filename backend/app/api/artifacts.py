"""Owner-protected image artifact upload and download APIs."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.production.artifacts import (
    ArtifactResponse,
    artifact_response,
    get_artifact_service,
)
from app.production.auth import ApiPrincipal, require_any_scope, require_scopes
from app.production.telemetry import record_audit

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.post("", response_model=ArtifactResponse, status_code=201)
async def upload_artifact(
    image: UploadFile = File(...),
    principal: ApiPrincipal = Depends(require_any_scope("artifacts:write", "generate")),
) -> ArtifactResponse:
    """Validate and persist an owner-bound image artifact."""
    data = await image.read()
    artifact = await get_artifact_service().create_image(
        principal.key_id,
        data,
        image.content_type or "",
    )
    await record_audit(
        principal.key_id,
        "artifact.upload",
        "artifact",
        artifact.id,
        details={"media_type": artifact.media_type, "size_bytes": artifact.size_bytes},
    )
    return artifact


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
    principal: ApiPrincipal = Depends(require_scopes("artifacts:read")),
) -> ArtifactResponse:
    """Return owner-filtered artifact metadata."""
    service = get_artifact_service()
    record = await service.get_owned(artifact_id, principal.key_id)
    if record is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    await record_audit(
        principal.key_id,
        "artifact.read_metadata",
        "artifact",
        artifact_id,
    )
    return artifact_response(record)


@router.get("/{artifact_id}/content")
async def get_artifact_content(
    artifact_id: str,
    principal: ApiPrincipal = Depends(require_scopes("artifacts:read")),
) -> Response:
    """Return owner-filtered artifact bytes."""
    found = await get_artifact_service().read_owned(artifact_id, principal.key_id)
    if found is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    record, data = found
    await record_audit(
        principal.key_id,
        "artifact.read_content",
        "artifact",
        artifact_id,
        details={"size_bytes": record.size_bytes},
    )
    return Response(
        data,
        media_type=record.media_type,
        headers={"Cache-Control": "private, no-store"},
    )
