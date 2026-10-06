"""HTTP API for named asset libraries (mounted behind ``assets`` scope)."""

# FastAPI dependency defaults (Depends/File/Form) are the supported injection style.
# ruff: noqa: B008

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

from app.assets.schemas import (
    AssetItem,
    AssetLibrary,
    ItemPatchRequest,
    LibraryCreateRequest,
    LibraryPatchRequest,
)
from app.assets.service import (
    AssetLibraryService,
    DuplicateItemError,
    ItemNotFoundError,
    LibraryNotFoundError,
    get_asset_library_service,
)
from app.pipeline.image_validation import resolve_upload_mime
from app.production.auth import ApiPrincipal, current_principal
from app.production.http import error_response
from app.production.telemetry import record_audit

router = APIRouter(prefix="/assets", tags=["assets"])


def _service() -> AssetLibraryService:
    return get_asset_library_service()


def _map_lookup(exc: Exception) -> HTTPException:
    if isinstance(exc, (LibraryNotFoundError, ItemNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc)[:500])


@router.get("/libraries", response_model=list[AssetLibrary])
async def list_libraries(
    principal: ApiPrincipal = Depends(current_principal),
    service: AssetLibraryService = Depends(_service),
) -> list[AssetLibrary]:
    """List the caller's libraries, creating a default one if needed."""
    return await service.list_libraries(principal.key_id)


@router.post("/libraries", response_model=AssetLibrary, status_code=201)
async def create_library(
    body: LibraryCreateRequest,
    principal: ApiPrincipal = Depends(current_principal),
    service: AssetLibraryService = Depends(_service),
) -> AssetLibrary:
    """Create a named library (idempotent on the same name)."""
    library = await service.create_library(principal.key_id, body.name, body.purpose)
    await record_audit(
        principal.key_id,
        "assets.create_library",
        "asset_library",
        library.id,
        details={"name": library.name},
    )
    return library


@router.patch("/libraries/{library_id}", response_model=AssetLibrary)
async def patch_library(
    library_id: str,
    body: LibraryPatchRequest,
    principal: ApiPrincipal = Depends(current_principal),
    service: AssetLibraryService = Depends(_service),
) -> AssetLibrary:
    """Update a library's name or purpose."""
    try:
        return await service.patch_library(principal.key_id, library_id, body)
    except LibraryNotFoundError as exc:
        raise _map_lookup(exc) from exc


@router.post("/items", response_model=AssetItem, status_code=201)
async def ingest_item(
    request: Request,
    image: UploadFile = File(...),
    library_id: str = Form(""),
    library_name: str = Form(""),
    library_purpose: str = Form(""),
    title: str = Form(""),
    keywords: str = Form(""),
    source_project: str = Form(""),
    character_name: str = Form(""),
    force: str = Form(""),
    principal: ApiPrincipal = Depends(current_principal),
    service: AssetLibraryService = Depends(_service),
) -> AssetItem | JSONResponse:
    """Upload an image, caption it with VLM, and store it in a named library."""
    data = await image.read()
    media_type = resolve_upload_mime(data, image.content_type)
    try:
        item = await service.ingest(
            principal.key_id,
            data,
            media_type,
            library_id=library_id.strip() or None,
            library_name=library_name.strip() or None,
            library_purpose=library_purpose.strip() or None,
            title=title.strip() or None,
            keywords=_split_csv(keywords),
            source_project=source_project.strip() or None,
            character_name=character_name.strip() or None,
            force=_truthy(force),
        )
    except DuplicateItemError as exc:
        existing = exc.existing
        return error_response(
            getattr(request.state, "request_id", "unknown"),
            409,
            "duplicate_asset",
            f"相同内容已入库：{existing.title}",
            {
                "existing_id": existing.id,
                "title": existing.title,
                "library_id": existing.library_id,
            },
        )
    except LibraryNotFoundError as exc:
        raise _map_lookup(exc) from exc
    await record_audit(
        principal.key_id,
        "assets.ingest",
        "asset_item",
        item.id,
        details={"library_id": item.library_id, "caption_status": item.caption_status},
    )
    return item


@router.get("/items", response_model=list[AssetItem])
async def list_items(
    q: str = "",
    library_id: str = "",
    principal: ApiPrincipal = Depends(current_principal),
    service: AssetLibraryService = Depends(_service),
) -> list[AssetItem]:
    """Search owned items by substring across caption fields."""
    return await service.list_items(
        principal.key_id,
        library_id=library_id.strip() or None,
        query=q.strip() or None,
    )


@router.patch("/items/{item_id}", response_model=AssetItem)
async def patch_item(
    item_id: str,
    body: ItemPatchRequest,
    principal: ApiPrincipal = Depends(current_principal),
    service: AssetLibraryService = Depends(_service),
) -> AssetItem:
    """Update title, tags, description, style, or library membership."""
    try:
        return await service.patch_item(principal.key_id, item_id, body)
    except (LibraryNotFoundError, ItemNotFoundError) as exc:
        raise _map_lookup(exc) from exc


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str,
    principal: ApiPrincipal = Depends(current_principal),
    service: AssetLibraryService = Depends(_service),
) -> Response:
    """Remove an item from the library index."""
    try:
        await service.delete_item(principal.key_id, item_id)
    except ItemNotFoundError as exc:
        raise _map_lookup(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items/{item_id}/recaption", response_model=AssetItem)
async def recaption_item(
    item_id: str,
    principal: ApiPrincipal = Depends(current_principal),
    service: AssetLibraryService = Depends(_service),
) -> AssetItem:
    """Re-run VLM captioning on a stored item."""
    try:
        return await service.recaption(principal.key_id, item_id)
    except ItemNotFoundError as exc:
        raise _map_lookup(exc) from exc


@router.get("/artifacts/{artifact_id}")
async def get_artifact_content(
    artifact_id: str,
    principal: ApiPrincipal = Depends(current_principal),
    service: AssetLibraryService = Depends(_service),
) -> Response:
    """Serve an owned image so this feature works without ``artifacts:read``."""
    found = await service.read_owned_artifact(principal.key_id, artifact_id)
    if found is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    media_type, data = found
    return Response(
        data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


def _split_csv(raw: str) -> list[str]:
    parts = [part.strip() for part in raw.replace("，", ",").split(",")]
    return [part for part in parts if part]


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}
