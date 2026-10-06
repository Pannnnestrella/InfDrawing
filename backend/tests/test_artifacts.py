"""Artifact persistence, image job, expiry, and telemetry tests."""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.agent.schemas import IntentPlan, IntentType
from app.config import Settings, settings
from app.main import app
from app.pipeline.executor import TaskState
from app.production.artifacts import (
    ArtifactRecord,
    ArtifactResponse,
    ArtifactService,
    JsonArtifactRepository,
    MemoryArtifactRepository,
)
from app.production.auth import (
    ApiKeyAuthenticator,
    ApiPrincipal,
    api_key_locator,
    authenticator,
    generate_api_key,
    hash_api_key,
)
from app.production.infrastructure import LocalArtifactStorage, S3Storage
from app.production.jobs import JobStatus, JobSubmit, MemoryJobRepository
from app.production.telemetry import (
    AuditEvent,
    MemoryTelemetryRepository,
    validate_audit_details,
)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buffer, format="PNG")
    return buffer.getvalue()


def test_local_artifact_service_enforces_owner(tmp_path: Path) -> None:
    async def run() -> None:
        repository = MemoryArtifactRepository()
        service = ArtifactService(repository, LocalArtifactStorage(tmp_path))
        response = await service.create_image("owner-a", _png_bytes(), "image/png")
        owned = await service.read_owned(response.id, "owner-a")
        foreign = await service.read_owned(response.id, "owner-b")
        assert owned is not None
        assert owned[1] == _png_bytes()
        assert foreign is None
        assert response.content_url.endswith(f"/{response.id}/content")
        assert owned[0].storage_key == f"artifacts/{response.id}.png"

    asyncio.run(run())


def test_json_artifact_repository_reloads(tmp_path: Path) -> None:
    async def run() -> None:
        path = tmp_path / "artifacts.json"
        first = JsonArtifactRepository(path)
        service = ArtifactService(first, LocalArtifactStorage(tmp_path / "files"))
        response = await service.create_image("owner-a", _png_bytes(), "image/png")
        second = JsonArtifactRepository(path)
        loaded = await second.get_owned(response.id, "owner-a")
        assert loaded is not None
        assert loaded.owner_key_id == "owner-a"
        assert loaded.sha256 == (await first.get_owned(response.id, "owner-a")).sha256

    asyncio.run(run())


def test_s3_storage_put_and_get_are_mockable(monkeypatch: pytest.MonkeyPatch) -> None:
    objects: dict[str, bytes] = {}

    class FakeBody:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def read(self) -> bytes:
            return self.data

    class FakeS3Client:
        def put_object(self, **kwargs: object) -> None:
            objects[str(kwargs["Key"])] = bytes(kwargs["Body"])  # type: ignore[arg-type]

        def get_object(self, **kwargs: object) -> dict[str, FakeBody]:
            return {"Body": FakeBody(objects[str(kwargs["Key"])])}

    monkeypatch.setattr(
        "app.production.infrastructure.boto3.client",
        lambda *_args, **_kwargs: FakeS3Client(),
    )

    config = Settings(
        s3_endpoint_url="https://minio.example.test",
        s3_bucket="artifacts",
        s3_access_key="access",
        s3_secret_key="secret",
    )

    async def run() -> None:
        storage = S3Storage(config)
        digest = await storage.put_bytes("server/key.png", b"data", "image/png")
        assert len(digest) == 64
        assert await storage.get_bytes("server/key.png") == b"data"

    asyncio.run(run())


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("txt2img", {"prompt": "cat"}),
        (
            "inpaint",
            {
                "image": {"artifact_id": "11111111-1111-4111-8111-111111111111"},
                "mask": {"artifact_id": "22222222-2222-4222-8222-222222222222"},
                "prompt": "repair",
            },
        ),
        (
            "decompose",
            {"image": {"artifact_id": "11111111-1111-4111-8111-111111111111"}},
        ),
        (
            "text_edit",
            {
                "image": {"artifact_id": "11111111-1111-4111-8111-111111111111"},
                "bbox": [0, 0, 4, 4],
                "new_text": "hello",
            },
        ),
    ],
)
def test_all_image_job_payloads_are_validated(
    kind: str,
    payload: dict[str, object],
) -> None:
    submission = JobSubmit(kind=kind, payload=payload)  # type: ignore[arg-type]
    assert submission.kind == kind


def test_expired_memory_api_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    pepper = "p" * 32
    monkeypatch.setattr("app.production.auth.settings.api_key_pepper", pepper)
    raw_key = generate_api_key()
    locator = api_key_locator(raw_key)
    assert locator is not None
    authenticator = ApiKeyAuthenticator()
    authenticator.register_hash(
        locator,
        hash_api_key(raw_key, pepper),
        ApiPrincipal("expired", frozenset({"jobs:read"})),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    assert authenticator.verify(raw_key) is None


def test_expired_api_key_is_rejected_by_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.production.auth import authenticator

    pepper = "p" * 32
    raw_key = generate_api_key()
    locator = api_key_locator(raw_key)
    assert locator is not None
    authenticator.register_hash(
        locator,
        hash_api_key(raw_key, pepper),
        ApiPrincipal("expired-endpoint", frozenset({"jobs:read"})),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "api_key_pepper", pepper)
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/jobs/unknown",
            headers={"X-API-Key": raw_key},
        )
    assert response.status_code == 401


def test_audit_rejects_sensitive_details() -> None:
    with pytest.raises(ValueError, match="sensitive"):
        validate_audit_details({"prompt": "private prompt"})
    with pytest.raises(ValueError, match="sensitive"):
        validate_audit_details({"api_key": "secret"})

    async def run() -> None:
        repository = MemoryTelemetryRepository()
        event = AuditEvent(
            actor_key_id="owner",
            action="job.submit",
            resource_type="job",
            resource_id="job-1",
            details=validate_audit_details({"kind": "txt2img", "queue": "jobs:gpu"}),
        )
        await repository.audit(event)
        serialized = repository.audit_events[0].model_dump_json()
        assert "private prompt" not in serialized
        assert "secret" not in serialized

    asyncio.run(run())


def test_artifact_api_audit_contains_no_image_or_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = ArtifactService(
        MemoryArtifactRepository(),
        LocalArtifactStorage(tmp_path),
    )
    audit = AsyncMock()
    pepper = "p" * 32
    owner_key = generate_api_key()
    other_key = generate_api_key()
    owner_locator = api_key_locator(owner_key)
    other_locator = api_key_locator(other_key)
    assert owner_locator is not None
    assert other_locator is not None
    scopes = frozenset({"artifacts:write", "artifacts:read"})
    authenticator.register_hash(
        owner_locator,
        hash_api_key(owner_key, pepper),
        ApiPrincipal("artifact-owner", scopes),
    )
    authenticator.register_hash(
        other_locator,
        hash_api_key(other_key, pepper),
        ApiPrincipal("other-owner", scopes),
    )
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "api_key_pepper", pepper)
    monkeypatch.setattr("app.api.artifacts.get_artifact_service", lambda: service)
    monkeypatch.setattr("app.api.artifacts.record_audit", audit)
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v1/artifacts",
            headers={"X-API-Key": owner_key},
            files={"image": ("upload.png", _png_bytes(), "image/png")},
        )
        content = client.get(
            f"/api/v1/artifacts/{uploaded.json()['id']}/content",
            headers={"X-API-Key": owner_key},
        )
        foreign = client.get(
            f"/api/v1/artifacts/{uploaded.json()['id']}/content",
            headers={"X-API-Key": other_key},
        )
    assert uploaded.status_code == 201
    assert content.status_code == 200
    assert foreign.status_code == 404
    calls = str(audit.await_args_list).lower()
    assert "authorization" not in calls
    assert "api_key" not in calls
    assert str(_png_bytes()[:8]).lower() not in calls


def test_job_submit_and_cancel_audit_excludes_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = AsyncMock()
    monkeypatch.setattr("app.api.jobs.record_audit", audit)
    with TestClient(app) as client:
        submitted = client.post(
            "/api/v1/jobs",
            json={
                "kind": "txt2img",
                "payload": {"prompt": "private audit prompt"},
            },
        )
        cancelled = client.post(f"/api/v1/jobs/{submitted.json()['id']}/cancel")
    assert submitted.status_code == 202
    assert cancelled.status_code == 200
    calls = str(audit.await_args_list)
    assert "private audit prompt" not in calls
    assert "job.submit" in calls
    assert "job.cancel" in calls


def test_inpaint_job_accepts_owned_artifact_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OwnedArtifactService:
        async def get_owned(
            self,
            artifact_id: str,
            owner_key_id: str,
        ) -> ArtifactRecord | None:
            return ArtifactRecord(
                id=artifact_id,
                owner_key_id=owner_key_id,
                job_id=None,
                storage_key=f"artifacts/{artifact_id}.png",
                media_type="image/png",
                size_bytes=64,
                sha256="a" * 64,
                created_at=datetime.now(UTC),
            )

    monkeypatch.setattr(
        "app.api.jobs.get_artifact_service",
        lambda: OwnedArtifactService(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            json={
                "kind": "inpaint",
                "payload": {
                    "image": {"artifact_id": "11111111-1111-4111-8111-111111111111"},
                    "mask": {"artifact_id": "22222222-2222-4222-8222-222222222222"},
                    "prompt": "repair",
                },
            },
        )
    assert response.status_code == 202
    assert response.json()["kind"] == "inpaint"
    assert response.json()["queue"] == settings.queue_gpu


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        (
            "inpaint",
            {
                "image": {"artifact_id": "11111111-1111-4111-8111-111111111111"},
                "mask": {"artifact_id": "22222222-2222-4222-8222-222222222222"},
                "prompt": "repair",
            },
        ),
        (
            "decompose",
            {"image": {"artifact_id": "11111111-1111-4111-8111-111111111111"}},
        ),
        (
            "text_edit",
            {
                "image": {"artifact_id": "11111111-1111-4111-8111-111111111111"},
                "bbox": [0, 0, 4, 4],
                "new_text": "hello",
            },
        ),
    ],
)
def test_artifact_worker_handlers_complete_with_mocked_pipeline(
    kind: str,
    payload: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def run() -> None:
        job_repository = MemoryJobRepository()
        job, _ = await job_repository.submit(
            "owner",
            JobSubmit(kind=kind, payload=payload),  # type: ignore[arg-type]
            None,
        )
        output_path = tmp_path / f"{kind}.png"
        Image.new("RGB", (8, 8), "green").save(output_path)
        task = TaskState(
            task_id=f"task-{kind}",
            prompt_id="prompt",
            image_path=output_path,
        )
        await task.emit_complete(f"/outputs/{kind}.png")
        input_record = ArtifactRecord(
            id="input",
            owner_key_id="owner",
            job_id=None,
            storage_key="artifacts/input.png",
            media_type="image/png",
            size_bytes=len(_png_bytes()),
            sha256="a" * 64,
            created_at=datetime.now(UTC),
        )

        class FakeArtifactService:
            async def read_owned(
                self,
                artifact_id: str,
                owner_key_id: str,
            ) -> tuple[ArtifactRecord, bytes] | None:
                assert owner_key_id == "owner"
                return input_record, _png_bytes()

            async def create_output(
                self,
                owner_key_id: str,
                job_id: str,
                path: Path,
            ) -> ArtifactResponse:
                assert owner_key_id == "owner"
                return ArtifactResponse(
                    id=f"output-{kind}",
                    job_id=job_id,
                    media_type="image/png",
                    size_bytes=path.stat().st_size,
                    sha256="b" * 64,
                    content_url=f"/api/v1/artifacts/output-{kind}/content",
                )

        async def fake_execute(
            _plan: IntentPlan,
            _inputs: dict[str, object],
        ) -> TaskState:
            return task

        monkeypatch.setattr("app.worker.get_job_repository", lambda: job_repository)
        monkeypatch.setattr(
            "app.worker.get_artifact_service",
            lambda: FakeArtifactService(),
        )
        monkeypatch.setattr("app.worker.execute_plan", fake_execute)

        from app.worker import execute_job

        result = await execute_job({}, job.id)
        persisted = await job_repository.get(job.id, "owner")
        assert result["status"] == "succeeded"
        assert persisted is not None
        assert persisted.status == JobStatus.SUCCEEDED
        assert persisted.result is not None
        assert persisted.result["primary_artifact"]["id"] == f"output-{kind}"

    asyncio.run(run())


def test_agent_route_records_provider_metadata_without_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        repository = MemoryJobRepository()
        job, _ = await repository.submit(
            "owner",
            JobSubmit(
                kind="agent_route",
                payload={"user_message": "sensitive prompt"},
            ),
            None,
        )
        recorder = AsyncMock()

        async def fake_plan(_request: object) -> IntentPlan:
            return IntentPlan(
                intent=IntentType.TXT2IMG,
                refined_prompt="result",
                target_tool="comfyui_txt2img_v1",
            )

        monkeypatch.setattr("app.worker.get_job_repository", lambda: repository)
        monkeypatch.setattr("app.worker.plan_intent", fake_plan)
        monkeypatch.setattr("app.worker.record_provider_call", recorder)

        from app.worker import execute_job

        await execute_job({}, job.id)
        event = recorder.await_args.args[0]
        serialized = event.model_dump_json()
        assert event.provider
        assert event.model
        assert event.success is True
        assert "sensitive prompt" not in serialized
        assert "result" not in serialized

    asyncio.run(run())
