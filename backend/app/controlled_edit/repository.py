"""Persistence for controlled-edit sessions and version trees."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import settings
from app.controlled_edit.schemas import EditSession, EditVersion, utc_now
from app.production.models import EditSessionRow, EditVersionRow


class EditRepository(Protocol):
    """Repository contract shared by memory and PostgreSQL implementations."""

    async def create_session(self, session: EditSession) -> EditSession: ...

    async def get_session(self, session_id: str, owner_key_id: str) -> EditSession | None: ...

    async def list_sessions(self, owner_key_id: str) -> list[EditSession]: ...

    async def save_session(self, session: EditSession) -> EditSession: ...

    async def add_version(self, version: EditVersion) -> EditVersion: ...

    async def get_version(self, session_id: str, version_id: str) -> EditVersion | None: ...

    async def save_version(self, version: EditVersion) -> EditVersion: ...

    async def list_versions(self, session_id: str) -> list[EditVersion]: ...

    async def delete_versions(self, session_id: str, version_ids: set[str]) -> None: ...


class MemoryEditRepository:
    """Lock-protected in-memory repository for tests and local development."""

    def __init__(self) -> None:
        self._sessions: dict[str, EditSession] = {}
        self._versions: dict[str, dict[str, EditVersion]] = {}
        self._lock = asyncio.Lock()

    async def create_session(self, session: EditSession) -> EditSession:
        """Persist a new session."""
        async with self._lock:
            if session.id in self._sessions:
                raise ValueError(f"session already exists: {session.id}")
            self._sessions[session.id] = session.model_copy(deep=True)
            self._versions[session.id] = {}
        return session

    async def get_session(self, session_id: str, owner_key_id: str) -> EditSession | None:
        """Return an owned session."""
        found = self._sessions.get(session_id)
        if found is None or found.owner_key_id != owner_key_id:
            return None
        return found.model_copy(deep=True)

    async def list_sessions(self, owner_key_id: str) -> list[EditSession]:
        """Return owned sessions, newest first."""
        owned = [s for s in self._sessions.values() if s.owner_key_id == owner_key_id]
        owned.sort(key=lambda s: s.updated_at, reverse=True)
        return [s.model_copy(deep=True) for s in owned]

    async def save_session(self, session: EditSession) -> EditSession:
        """Overwrite an existing session."""
        async with self._lock:
            if session.id not in self._sessions:
                raise KeyError(f"session not found: {session.id}")
            session.updated_at = utc_now()
            self._sessions[session.id] = session.model_copy(deep=True)
        return session

    async def add_version(self, version: EditVersion) -> EditVersion:
        """Insert a version node; the parent must already exist in the same session."""
        async with self._lock:
            versions = self._versions.get(version.session_id)
            if versions is None:
                raise KeyError(f"session not found: {version.session_id}")
            if version.parent_id is not None and version.parent_id not in versions:
                raise KeyError(f"parent version not found: {version.parent_id}")
            versions[version.id] = version.model_copy(deep=True)
        return version

    async def get_version(self, session_id: str, version_id: str) -> EditVersion | None:
        """Return one version of a session."""
        found = self._versions.get(session_id, {}).get(version_id)
        return found.model_copy(deep=True) if found else None

    async def save_version(self, version: EditVersion) -> EditVersion:
        """Overwrite an existing version node."""
        async with self._lock:
            versions = self._versions.get(version.session_id, {})
            if version.id not in versions:
                raise KeyError(f"version not found: {version.id}")
            version.updated_at = utc_now()
            versions[version.id] = version.model_copy(deep=True)
        return version

    async def list_versions(self, session_id: str) -> list[EditVersion]:
        """Return every version of a session in creation order."""
        versions = list(self._versions.get(session_id, {}).values())
        versions.sort(key=lambda v: v.created_at)
        return [v.model_copy(deep=True) for v in versions]

    async def delete_versions(self, session_id: str, version_ids: set[str]) -> None:
        """Remove the given version ids from a session (missing ids are ignored)."""
        async with self._lock:
            versions = self._versions.get(session_id)
            if versions is None:
                raise KeyError(f"session not found: {session_id}")
            for version_id in version_ids:
                versions.pop(version_id, None)


def _atomic_write_json(path: Path, payload: object) -> None:
    """Write JSON by replacing a temp file so a crash cannot leave a half-written store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class JsonEditRepository(MemoryEditRepository):
    """Memory repository that reloads from and writes through a JSON file."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._sessions = {
            key: EditSession.model_validate(value)
            for key, value in (raw.get("sessions") or {}).items()
        }
        self._versions = {
            session_id: {
                version_id: EditVersion.model_validate(value)
                for version_id, value in versions.items()
            }
            for session_id, versions in (raw.get("versions") or {}).items()
        }

    def _persist(self) -> None:
        _atomic_write_json(
            self._path,
            {
                "sessions": {
                    key: session.model_dump(mode="json")
                    for key, session in self._sessions.items()
                },
                "versions": {
                    session_id: {
                        version_id: version.model_dump(mode="json")
                        for version_id, version in versions.items()
                    }
                    for session_id, versions in self._versions.items()
                },
            },
        )

    async def create_session(self, session: EditSession) -> EditSession:
        """Persist a new session and flush the store."""
        result = await super().create_session(session)
        self._persist()
        return result

    async def save_session(self, session: EditSession) -> EditSession:
        """Overwrite a session and flush the store."""
        result = await super().save_session(session)
        self._persist()
        return result

    async def add_version(self, version: EditVersion) -> EditVersion:
        """Insert a version and flush the store."""
        result = await super().add_version(version)
        self._persist()
        return result

    async def save_version(self, version: EditVersion) -> EditVersion:
        """Overwrite a version and flush the store."""
        result = await super().save_version(version)
        self._persist()
        return result

    async def delete_versions(self, session_id: str, version_ids: set[str]) -> None:
        """Remove versions and flush the store."""
        await super().delete_versions(session_id, version_ids)
        self._persist()


class SqlEditRepository:
    """PostgreSQL repository storing serialized models in JSON columns."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def create_session(self, session: EditSession) -> EditSession:
        """Insert a new session."""
        async with self.sessions.begin() as db:
            db.add(
                EditSessionRow(
                    id=session.id,
                    owner_key_id=session.owner_key_id,
                    data=session.model_dump(mode="json"),
                )
            )
        return session

    async def get_session(self, session_id: str, owner_key_id: str) -> EditSession | None:
        """Return an owned session."""
        async with self.sessions() as db:
            row = await db.scalar(
                select(EditSessionRow).where(
                    EditSessionRow.id == session_id,
                    EditSessionRow.owner_key_id == owner_key_id,
                )
            )
        return EditSession.model_validate(row.data) if row else None

    async def list_sessions(self, owner_key_id: str) -> list[EditSession]:
        """Return owned sessions, newest first."""
        async with self.sessions() as db:
            rows = await db.scalars(
                select(EditSessionRow)
                .where(EditSessionRow.owner_key_id == owner_key_id)
                .order_by(EditSessionRow.updated_at.desc())
            )
            return [EditSession.model_validate(row.data) for row in rows]

    async def save_session(self, session: EditSession) -> EditSession:
        """Overwrite an existing session."""
        session.updated_at = utc_now()
        async with self.sessions.begin() as db:
            row = await db.get(EditSessionRow, session.id)
            if row is None:
                raise KeyError(f"session not found: {session.id}")
            row.data = session.model_dump(mode="json")
        return session

    async def add_version(self, version: EditVersion) -> EditVersion:
        """Insert a version node."""
        async with self.sessions.begin() as db:
            if version.parent_id is not None:
                parent = await db.get(EditVersionRow, version.parent_id)
                if parent is None or parent.session_id != version.session_id:
                    raise KeyError(f"parent version not found: {version.parent_id}")
            db.add(
                EditVersionRow(
                    id=version.id,
                    session_id=version.session_id,
                    parent_id=version.parent_id,
                    status=version.status.value,
                    data=version.model_dump(mode="json"),
                )
            )
        return version

    async def get_version(self, session_id: str, version_id: str) -> EditVersion | None:
        """Return one version of a session."""
        async with self.sessions() as db:
            row = await db.get(EditVersionRow, version_id)
        if row is None or row.session_id != session_id:
            return None
        return EditVersion.model_validate(row.data)

    async def save_version(self, version: EditVersion) -> EditVersion:
        """Overwrite an existing version node."""
        version.updated_at = utc_now()
        async with self.sessions.begin() as db:
            row = await db.get(EditVersionRow, version.id)
            if row is None:
                raise KeyError(f"version not found: {version.id}")
            row.status = version.status.value
            row.data = version.model_dump(mode="json")
        return version

    async def list_versions(self, session_id: str) -> list[EditVersion]:
        """Return every version of a session in creation order."""
        async with self.sessions() as db:
            rows = await db.scalars(
                select(EditVersionRow)
                .where(EditVersionRow.session_id == session_id)
                .order_by(EditVersionRow.created_at)
            )
            return [EditVersion.model_validate(row.data) for row in rows]

    async def delete_versions(self, session_id: str, version_ids: set[str]) -> None:
        """Delete version rows that belong to ``session_id``."""
        if not version_ids:
            return
        async with self.sessions.begin() as db:
            rows = await db.scalars(
                select(EditVersionRow).where(
                    EditVersionRow.session_id == session_id,
                    EditVersionRow.id.in_(version_ids),
                )
            )
            for row in rows:
                await db.delete(row)


_repository: EditRepository | None = None


def get_edit_repository() -> EditRepository:
    """Return the configured memory or PostgreSQL repository."""
    global _repository
    if _repository is not None:
        return _repository
    if settings.persistence_backend == "memory":
        _repository = JsonEditRepository(settings.data_dir / "cedit" / "sessions.json")
    elif settings.persistence_backend == "postgres":
        from app.production.models import create_engine

        _repository = SqlEditRepository(create_engine())
    else:
        raise RuntimeError(f"unsupported persistence backend: {settings.persistence_backend}")
    return _repository
