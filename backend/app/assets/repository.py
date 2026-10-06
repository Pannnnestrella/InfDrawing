"""JSON persistence for asset libraries and items."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from app.assets.schemas import AssetItem, AssetLibrary
from app.config import settings


class AssetRepository(Protocol):
    """Repository contract for libraries and items."""

    async def save_library(self, library: AssetLibrary) -> AssetLibrary: ...

    async def get_library(
        self, library_id: str, owner_key_id: str
    ) -> AssetLibrary | None: ...

    async def list_libraries(self, owner_key_id: str) -> list[AssetLibrary]: ...

    async def find_library_by_name(
        self, owner_key_id: str, name: str
    ) -> AssetLibrary | None: ...

    async def find_item_by_sha256(
        self, owner_key_id: str, content_sha256: str
    ) -> AssetItem | None: ...

    async def save_item(self, item: AssetItem) -> AssetItem: ...

    async def get_item(self, item_id: str, owner_key_id: str) -> AssetItem | None: ...

    async def delete_item(self, item_id: str, owner_key_id: str) -> bool: ...

    async def list_items(
        self,
        owner_key_id: str,
        *,
        library_id: str | None = None,
        query: str | None = None,
    ) -> list[AssetItem]: ...


class MemoryAssetRepository:
    """Lock-protected in-memory store for tests and as the Json write-through base."""

    def __init__(self) -> None:
        self._libraries: dict[str, AssetLibrary] = {}
        self._items: dict[str, AssetItem] = {}
        self._lock = asyncio.Lock()

    async def save_library(self, library: AssetLibrary) -> AssetLibrary:
        """Insert or overwrite a library."""
        async with self._lock:
            self._libraries[library.id] = library.model_copy(deep=True)
        return library

    async def get_library(
        self, library_id: str, owner_key_id: str
    ) -> AssetLibrary | None:
        """Return an owned library."""
        found = self._libraries.get(library_id)
        if found is None or found.owner_key_id != owner_key_id:
            return None
        return found.model_copy(deep=True)

    async def list_libraries(self, owner_key_id: str) -> list[AssetLibrary]:
        """Return owned libraries, oldest first (default library first)."""
        owned = [lib for lib in self._libraries.values() if lib.owner_key_id == owner_key_id]
        owned.sort(key=lambda lib: lib.created_at)
        return [lib.model_copy(deep=True) for lib in owned]

    async def find_library_by_name(
        self, owner_key_id: str, name: str
    ) -> AssetLibrary | None:
        """Return the owned library whose name matches case-insensitively."""
        needle = name.strip().casefold()
        for lib in self._libraries.values():
            if lib.owner_key_id == owner_key_id and lib.name.strip().casefold() == needle:
                return lib.model_copy(deep=True)
        return None

    async def find_item_by_sha256(
        self, owner_key_id: str, content_sha256: str
    ) -> AssetItem | None:
        """Return the newest owned item whose stored bytes match ``content_sha256``."""
        digest = content_sha256.strip().lower()
        if not digest:
            return None
        matches = [
            item
            for item in self._items.values()
            if item.owner_key_id == owner_key_id and item.content_sha256.lower() == digest
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: item.created_at, reverse=True)
        return matches[0].model_copy(deep=True)

    async def save_item(self, item: AssetItem) -> AssetItem:
        """Insert or overwrite an item."""
        async with self._lock:
            self._items[item.id] = item.model_copy(deep=True)
        return item

    async def get_item(self, item_id: str, owner_key_id: str) -> AssetItem | None:
        """Return an owned item."""
        found = self._items.get(item_id)
        if found is None or found.owner_key_id != owner_key_id:
            return None
        return found.model_copy(deep=True)

    async def delete_item(self, item_id: str, owner_key_id: str) -> bool:
        """Remove an owned item. Missing ids return False."""
        async with self._lock:
            found = self._items.get(item_id)
            if found is None or found.owner_key_id != owner_key_id:
                return False
            del self._items[item_id]
            return True

    async def list_items(
        self,
        owner_key_id: str,
        *,
        library_id: str | None = None,
        query: str | None = None,
    ) -> list[AssetItem]:
        """Return owned items newest first, optionally filtered."""
        owned = [item for item in self._items.values() if item.owner_key_id == owner_key_id]
        if library_id:
            owned = [item for item in owned if item.library_id == library_id]
        needle = (query or "").strip().casefold()
        if needle:
            owned = [item for item in owned if item_matches_query(item, needle)]
        owned.sort(key=lambda item: item.created_at, reverse=True)
        return [item.model_copy(deep=True) for item in owned]


def item_matches_query(item: AssetItem, needle: str) -> bool:
    """Return True when ``needle`` (already casefolded) occurs in searchable fields."""
    haystack = item.search_blob().casefold()
    return needle in haystack


def _atomic_write_json(path: Path, payload: object) -> None:
    """Write JSON by replacing a temp file so a crash cannot leave a half-written store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class JsonAssetRepository(MemoryAssetRepository):
    """Memory repository that reloads from and writes through a JSON file."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._libraries = {
            key: AssetLibrary.model_validate(value)
            for key, value in (raw.get("libraries") or {}).items()
        }
        self._items = {
            key: AssetItem.model_validate(value)
            for key, value in (raw.get("items") or {}).items()
        }

    def _persist(self) -> None:
        libraries = {
            key: value.model_dump(mode="json") for key, value in self._libraries.items()
        }
        items = {key: value.model_dump(mode="json") for key, value in self._items.items()}
        _atomic_write_json(self._path, {"libraries": libraries, "items": items})

    async def save_library(self, library: AssetLibrary) -> AssetLibrary:
        """Persist a library and flush JSON."""
        result = await super().save_library(library)
        self._persist()
        return result

    async def save_item(self, item: AssetItem) -> AssetItem:
        """Persist an item and flush JSON."""
        result = await super().save_item(item)
        self._persist()
        return result

    async def delete_item(self, item_id: str, owner_key_id: str) -> bool:
        """Delete an item and flush JSON when something was removed."""
        removed = await super().delete_item(item_id, owner_key_id)
        if removed:
            self._persist()
        return removed


_repository: AssetRepository | None = None


def get_asset_repository() -> AssetRepository:
    """Return the JSON-backed asset repository."""
    global _repository
    if _repository is not None:
        return _repository
    _repository = JsonAssetRepository(settings.data_dir / "assets" / "library.json")
    return _repository
