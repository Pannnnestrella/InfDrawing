"""Create libraries, ingest images, caption them, and search."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from app.assets.caption_parser import CaptionParseError, parse_caption
from app.assets.repository import AssetRepository, get_asset_repository
from app.assets.schemas import (
    DEFAULT_LIBRARY_NAME,
    AssetItem,
    AssetLibrary,
    CaptionDraft,
    ItemPatchRequest,
    LibraryPatchRequest,
    new_id,
    utc_now,
)
from app.controlled_edit.scene_parser import JsonVisionModel
from app.controlled_edit.vision import VisionError
from app.production.artifacts import ArtifactService, get_artifact_service


class LibraryNotFoundError(LookupError):
    """Raised when a library id is missing or not owned."""


class ItemNotFoundError(LookupError):
    """Raised when an item id is missing or not owned."""


class DuplicateItemError(LookupError):
    """Raised when the same image bytes are already in the owner's library."""

    def __init__(self, existing: AssetItem) -> None:
        super().__init__(f"duplicate asset already stored as {existing.id}")
        self.existing = existing


class AssetLibraryService:
    """Coordinate artifacts, VLM captions, and the JSON library index."""

    def __init__(
        self,
        repository: AssetRepository,
        artifacts: ArtifactService,
        vision_factory: Callable[[], JsonVisionModel],
    ) -> None:
        self._repository = repository
        self._artifacts = artifacts
        self._vision_factory = vision_factory

    async def list_libraries(self, owner_key_id: str) -> list[AssetLibrary]:
        """Return owned libraries, creating the default library if none exist."""
        await self.ensure_default_library(owner_key_id)
        return await self._repository.list_libraries(owner_key_id)

    async def create_library(
        self, owner_key_id: str, name: str, purpose: str = ""
    ) -> AssetLibrary:
        """Create a library, or return the existing one with the same name."""
        cleaned = name.strip() or DEFAULT_LIBRARY_NAME
        cleaned_purpose = purpose.strip()[:240]
        existing = await self._repository.find_library_by_name(owner_key_id, cleaned)
        if existing is not None:
            if cleaned_purpose and cleaned_purpose != existing.purpose:
                existing = existing.model_copy(
                    update={"purpose": cleaned_purpose, "updated_at": utc_now()}
                )
                return await self._repository.save_library(existing)
            return existing
        now = utc_now()
        library = AssetLibrary(
            id=new_id(),
            owner_key_id=owner_key_id,
            name=cleaned[:80],
            purpose=cleaned_purpose,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.save_library(library)

    async def patch_library(
        self, owner_key_id: str, library_id: str, patch: LibraryPatchRequest
    ) -> AssetLibrary:
        """Rename a library or update its purpose."""
        library = await self._repository.get_library(library_id, owner_key_id)
        if library is None:
            raise LibraryNotFoundError(f"library not found: {library_id}")
        updates: dict[str, object] = {}
        if patch.name is not None:
            cleaned = patch.name.strip() or library.name
            clash = await self._repository.find_library_by_name(owner_key_id, cleaned)
            if clash is not None and clash.id != library.id:
                raise LibraryNotFoundError(f"library name already exists: {cleaned}")
            updates["name"] = cleaned[:80]
        if patch.purpose is not None:
            updates["purpose"] = patch.purpose.strip()[:240]
        if updates:
            library = library.model_copy(update={**updates, "updated_at": utc_now()})
            await self._repository.save_library(library)
        return library

    async def ensure_default_library(self, owner_key_id: str) -> AssetLibrary:
        """Guarantee each owner has a library named 默认."""
        existing = await self._repository.find_library_by_name(
            owner_key_id, DEFAULT_LIBRARY_NAME
        )
        if existing is not None:
            return existing
        return await self.create_library(owner_key_id, DEFAULT_LIBRARY_NAME)

    async def ingest(
        self,
        owner_key_id: str,
        image_bytes: bytes,
        media_type: str,
        *,
        library_id: str | None = None,
        library_name: str | None = None,
        library_purpose: str | None = None,
        title: str | None = None,
        keywords: list[str] | None = None,
        source_project: str | None = None,
        character_name: str | None = None,
        force: bool = False,
    ) -> AssetItem:
        """Store the image, caption it, and index the item.

        Caption failures still persist the item with ``caption_failed``.
        Identical bytes owned by the same caller raise ``DuplicateItemError``
        unless ``force`` is true.
        """
        digest = _sha256_hex(image_bytes)
        if not force:
            existing = await self._repository.find_item_by_sha256(owner_key_id, digest)
            if existing is not None:
                raise DuplicateItemError(existing)
        if library_id:
            library = await self._resolve_library(owner_key_id, library_id, None)
        elif library_name and library_name.strip():
            library = await self.create_library(
                owner_key_id, library_name, purpose=library_purpose or ""
            )
        else:
            library = await self.ensure_default_library(owner_key_id)
        artifact = await self._artifacts.create_image(owner_key_id, image_bytes, media_type)
        now = utc_now()
        user_title = (title or "").strip()
        item = AssetItem(
            id=new_id(),
            owner_key_id=owner_key_id,
            library_id=library.id,
            artifact_id=artifact.id,
            title=user_title or "未命名素材",
            keywords=CaptionDraft(tags=keywords or []).tags,
            source_project=(source_project or "").strip()[:240],
            character_name=(character_name or "").strip()[:240],
            content_sha256=artifact.sha256,
            created_at=now,
            updated_at=now,
        )
        await self._apply_caption(item, image_bytes, prefer_title=user_title)
        return await self._repository.save_item(item)

    async def list_items(
        self,
        owner_key_id: str,
        *,
        library_id: str | None = None,
        query: str | None = None,
    ) -> list[AssetItem]:
        """Return owned items, newest first."""
        return await self._repository.list_items(
            owner_key_id, library_id=library_id, query=query
        )

    async def patch_item(
        self, owner_key_id: str, item_id: str, patch: ItemPatchRequest
    ) -> AssetItem:
        """Apply a partial update to an owned item."""
        item = await self._require_item(owner_key_id, item_id)
        updates: dict[str, object] = {}
        if patch.library_id is not None:
            library = await self._repository.get_library(patch.library_id, owner_key_id)
            if library is None:
                raise LibraryNotFoundError(f"library not found: {patch.library_id}")
            updates["library_id"] = library.id
        if patch.title is not None:
            updates["title"] = patch.title.strip() or item.title
        if patch.objects is not None:
            updates["objects"] = CaptionDraft(objects=patch.objects).objects
        if patch.tags is not None:
            updates["tags"] = CaptionDraft(tags=patch.tags).tags
        if patch.keywords is not None:
            updates["keywords"] = CaptionDraft(tags=patch.keywords).tags
        if patch.description is not None:
            updates["description"] = patch.description.strip()
        if patch.style is not None:
            updates["style"] = patch.style.strip()
        if patch.source_project is not None:
            updates["source_project"] = patch.source_project.strip()[:240]
        if patch.character_name is not None:
            updates["character_name"] = patch.character_name.strip()[:240]
        if patch.asset_type is not None:
            updates["asset_type"] = CaptionDraft(asset_type=patch.asset_type).asset_type
        if patch.view is not None:
            updates["view"] = CaptionDraft(view=patch.view).view
        if patch.genre is not None:
            updates["genre"] = CaptionDraft(genre=patch.genre).genre
        if patch.background is not None:
            updates["background"] = CaptionDraft(background=patch.background).background
        if patch.pose is not None:
            updates["pose"] = CaptionDraft(pose=patch.pose).pose
        if patch.palette is not None:
            updates["palette"] = CaptionDraft(palette=patch.palette).palette
        if patch.materials is not None:
            updates["materials"] = CaptionDraft(materials=patch.materials).materials
        if updates:
            item = item.model_copy(update={**updates, "updated_at": utc_now()})
            await self._repository.save_item(item)
        return item

    async def delete_item(self, owner_key_id: str, item_id: str) -> None:
        """Remove an owned item from the index."""
        removed = await self._repository.delete_item(item_id, owner_key_id)
        if not removed:
            raise ItemNotFoundError(f"item not found: {item_id}")

    async def recaption(self, owner_key_id: str, item_id: str) -> AssetItem:
        """Re-run VLM captioning on a stored image."""
        item = await self._require_item(owner_key_id, item_id)
        found = await self._artifacts.read_owned(item.artifact_id, owner_key_id)
        if found is None:
            raise ItemNotFoundError(f"artifact missing for item: {item_id}")
        _, data = found
        await self._apply_caption(item, data, prefer_title="")
        item.updated_at = utc_now()
        return await self._repository.save_item(item)

    async def read_owned_artifact(
        self, owner_key_id: str, artifact_id: str
    ) -> tuple[str, bytes] | None:
        """Return media type and bytes when the caller owns the artifact."""
        found = await self._artifacts.read_owned(artifact_id, owner_key_id)
        if found is None:
            return None
        record, data = found
        return record.media_type, data

    async def _resolve_library(
        self,
        owner_key_id: str,
        library_id: str | None,
        library_name: str | None,
    ) -> AssetLibrary:
        if library_id:
            library = await self._repository.get_library(library_id, owner_key_id)
            if library is None:
                raise LibraryNotFoundError(f"library not found: {library_id}")
            return library
        if library_name and library_name.strip():
            return await self.create_library(owner_key_id, library_name)
        return await self.ensure_default_library(owner_key_id)

    async def _require_item(self, owner_key_id: str, item_id: str) -> AssetItem:
        item = await self._repository.get_item(item_id, owner_key_id)
        if item is None:
            raise ItemNotFoundError(f"item not found: {item_id}")
        return item

    async def _apply_caption(
        self, item: AssetItem, image_bytes: bytes, *, prefer_title: str
    ) -> None:
        try:
            vision = self._vision_factory()
            draft = await parse_caption(vision, image_bytes)
        except (VisionError, CaptionParseError) as exc:
            item.caption_status = "caption_failed"
            item.caption_error = str(exc)[:500]
            return
        item.objects = draft.objects
        item.tags = draft.tags
        item.description = draft.description
        item.style = draft.style
        item.asset_type = draft.asset_type
        item.view = draft.view
        item.genre = draft.genre
        item.background = draft.background
        item.pose = draft.pose
        item.palette = draft.palette
        item.materials = draft.materials
        item.caption_status = "ok"
        item.caption_error = None
        if not prefer_title and draft.title:
            item.title = draft.title


def _sha256_hex(data: bytes) -> str:
    """Hex digest of stored image bytes (filename-independent)."""
    return hashlib.sha256(data).hexdigest()


_service: AssetLibraryService | None = None


def get_asset_library_service() -> AssetLibraryService:
    """Return the process-wide asset library service."""
    global _service
    if _service is not None:
        return _service
    from app.controlled_edit.vision import scene_vision_client

    _service = AssetLibraryService(
        repository=get_asset_repository(),
        artifacts=get_artifact_service(),
        vision_factory=scene_vision_client,
    )
    return _service
