"""Owner-bound artifact metadata and storage services."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import settings
from app.pipeline.image_validation import validate_upload_image
from app.production.infrastructure import LocalArtifactStorage, S3Storage
from app.production.models import Artifact

_SUFFIX_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class ArtifactRecord(BaseModel):
    """Internal owner-bound artifact metadata."""

    id: str
    owner_key_id: str
    job_id: str | None
    storage_key: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ArtifactResponse(BaseModel):
    """Safe artifact metadata returned by protected APIs."""

    id: str
    job_id: str | None
    media_type: str
    size_bytes: int
    sha256: str
    content_url: str


class ArtifactRepository(Protocol):
    """Artifact metadata persistence contract."""

    async def create(self, record: ArtifactRecord) -> ArtifactRecord: ...

    async def get_owned(
        self,
        artifact_id: str,
        owner_key_id: str,
    ) -> ArtifactRecord | None: ...


class MemoryArtifactRepository:
    """In-memory artifact metadata for development and tests."""

    def __init__(self) -> None:
        self._records: dict[str, ArtifactRecord] = {}

    async def create(self, record: ArtifactRecord) -> ArtifactRecord:
        """Persist artifact metadata."""
        self._records[record.id] = record
        return record

    async def get_owned(
        self,
        artifact_id: str,
        owner_key_id: str,
    ) -> ArtifactRecord | None:
        """Return metadata only when the owner matches."""
        record = self._records.get(artifact_id)
        return record if record and record.owner_key_id == owner_key_id else None


class JsonArtifactRepository(MemoryArtifactRepository):
    """Memory artifact index that reloads from and writes through a JSON file."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._records = {
            key: ArtifactRecord.model_validate(value)
            for key, value in (raw.get("records") or {}).items()
        }

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        payload = {
            "records": {key: record.model_dump(mode="json") for key, record in self._records.items()}
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    async def create(self, record: ArtifactRecord) -> ArtifactRecord:
        """Persist artifact metadata and flush the index."""
        result = await super().create(record)
        self._persist()
        return result


class SqlArtifactRepository:
    """PostgreSQL artifact metadata repository."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def create(self, record: ArtifactRecord) -> ArtifactRecord:
        """Insert artifact metadata."""
        async with self.sessions.begin() as session:
            session.add(
                Artifact(
                    id=record.id,
                    owner_key_id=record.owner_key_id,
                    job_id=record.job_id,
                    storage_key=record.storage_key,
                    media_type=record.media_type,
                    size_bytes=record.size_bytes,
                    sha256=record.sha256,
                )
            )
        return record

    async def get_owned(
        self,
        artifact_id: str,
        owner_key_id: str,
    ) -> ArtifactRecord | None:
        """Return an owner-filtered artifact."""
        async with self.sessions() as session:
            row = await session.scalar(
                select(Artifact).where(
                    Artifact.id == artifact_id,
                    Artifact.owner_key_id == owner_key_id,
                )
            )
        return _record_from_row(row) if row else None


class ArtifactStorage(Protocol):
    """Binary artifact storage contract."""

    async def put_bytes(self, key: str, data: bytes, media_type: str) -> str: ...

    async def get_bytes(self, key: str) -> bytes: ...


class ArtifactService:
    """Coordinate validated bytes with owner-filtered metadata."""

    def __init__(
        self,
        repository: ArtifactRepository,
        storage: ArtifactStorage,
    ) -> None:
        self.repository = repository
        self.storage = storage

    async def create_image(
        self,
        owner_key_id: str,
        data: bytes,
        media_type: str,
        *,
        job_id: str | None = None,
    ) -> ArtifactResponse:
        """Validate and persist one image using a server-generated object key."""
        _, _, verified_mime = validate_upload_image(data, media_type)
        artifact_id = str(uuid.uuid4())
        storage_key = f"artifacts/{artifact_id}{_SUFFIX_BY_MIME[verified_mime]}"
        digest = await self.storage.put_bytes(storage_key, data, verified_mime)
        record = ArtifactRecord(
            id=artifact_id,
            owner_key_id=owner_key_id,
            job_id=job_id,
            storage_key=storage_key,
            media_type=verified_mime,
            size_bytes=len(data),
            sha256=digest,
            created_at=datetime.now(UTC),
        )
        await self.repository.create(record)
        return artifact_response(record)

    async def get_owned(
        self,
        artifact_id: str,
        owner_key_id: str,
    ) -> ArtifactRecord | None:
        """Return owner-filtered metadata."""
        return await self.repository.get_owned(artifact_id, owner_key_id)

    async def read_owned(
        self,
        artifact_id: str,
        owner_key_id: str,
    ) -> tuple[ArtifactRecord, bytes] | None:
        """Read bytes only when the caller owns the artifact."""
        record = await self.get_owned(artifact_id, owner_key_id)
        if record is None:
            return None
        return record, await self.storage.get_bytes(record.storage_key)

    async def create_output(
        self,
        owner_key_id: str,
        job_id: str,
        path: Path,
    ) -> ArtifactResponse:
        """Persist a generated image output."""
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(path.suffix.lower(), "image/png")
        return await self.create_image(
            owner_key_id,
            await asyncio.to_thread(path.read_bytes),
            media_type,
            job_id=job_id,
        )


def artifact_response(record: ArtifactRecord) -> ArtifactResponse:
    """Build protected public metadata without exposing the storage key."""
    return ArtifactResponse(
        id=record.id,
        job_id=record.job_id,
        media_type=record.media_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        content_url=f"/api/v1/artifacts/{record.id}/content",
    )


def _record_from_row(row: Artifact) -> ArtifactRecord:
    return ArtifactRecord(
        id=row.id,
        owner_key_id=row.owner_key_id,
        job_id=row.job_id,
        storage_key=row.storage_key,
        media_type=row.media_type,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        created_at=row.created_at,
    )


_artifact_service: ArtifactService | None = None


def get_artifact_service() -> ArtifactService:
    """Return the configured local or S3 artifact service."""
    global _artifact_service
    if _artifact_service is not None:
        return _artifact_service
    if settings.persistence_backend == "postgres":
        from app.production.models import create_engine

        repository: ArtifactRepository = SqlArtifactRepository(create_engine())
    else:
        repository = JsonArtifactRepository(settings.data_dir / "cedit" / "artifacts.json")
    storage: ArtifactStorage
    if settings.storage_backend == "s3":
        storage = S3Storage()
    else:
        storage = LocalArtifactStorage(settings.artifacts_dir)
    _artifact_service = ArtifactService(repository, storage)
    return _artifact_service
