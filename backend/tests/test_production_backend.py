"""Tests for routing, authentication, job reliability, and upload security."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

from app.agent.providers import IntentProvider
from app.agent.router import RoutingValidationError, plan_intent
from app.agent.schemas import AgentContext, AgentPlanRequest, IntentPlan, IntentType
from app.api.generate import _bind_task_owner
from app.api.jobs import _stream_events, repository
from app.config import Settings, settings
from app.main import app
from app.pipeline.executor import TaskState, task_manager
from app.pipeline.image_validation import validate_upload_image
from app.production.artifacts import ArtifactResponse
from app.production.auth import (
    ApiKeyAuthenticator,
    ApiPrincipal,
    api_key_locator,
    authenticator,
    generate_api_key,
    hash_api_key,
)
from app.production.jobs import (
    PUBLIC_JOB_KINDS,
    IdempotencyConflict,
    JobStatus,
    JobSubmit,
    MemoryJobRepository,
)


class FakeProvider(IntentProvider):
    """Return a predefined plan."""

    def __init__(self, plan: IntentPlan) -> None:
        self.plan = plan

    async def classify(self, system_prompt: str, user_prompt: str) -> IntentPlan:
        del system_prompt, user_prompt
        return self.plan


def test_explicit_override_has_priority_and_requests_missing_context() -> None:
    async def run() -> None:
        request = AgentPlanRequest(
            user_message="anything",
            intent_override=IntentType.INPAINT,
        )
        plan = await plan_intent(request)
        assert plan.intent == IntentType.INPAINT
        assert plan.confidence == 1.0
        assert plan.clarification_required
        assert "image_id" in (plan.clarification_question or "")

    asyncio.run(run())


def test_low_confidence_plan_requests_clarification() -> None:
    async def run() -> None:
        provider = FakeProvider(
            IntentPlan(
                intent=IntentType.TXT2IMG,
                refined_prompt="cat",
                target_tool="comfyui_txt2img_v1",
                confidence=0.2,
            )
        )
        plan = await plan_intent(AgentPlanRequest(user_message="cat"), provider)
        assert plan.clarification_required

    asyncio.run(run())


def test_automatic_text_edit_requires_structured_replacement_text() -> None:
    async def run() -> None:
        request = AgentPlanRequest(
            user_message="replace the title",
            context=AgentContext(
                image_id="image-1",
                bbox=[0, 0, 20, 20],
                new_text="replace the title",
            ),
        )
        provider = FakeProvider(
            IntentPlan(
                intent=IntentType.TEXT_EDIT,
                refined_prompt="replace the title",
                target_tool="comfyui_text_edit_v1",
                params={},
            )
        )
        plan = await plan_intent(request, provider)
        assert plan.clarification_required
        assert "new_text" in (plan.clarification_question or "")

    asyncio.run(run())


def test_automatic_text_edit_normalizes_structured_replacement_text() -> None:
    async def run() -> None:
        request = AgentPlanRequest(
            user_message="replace the title with Hello",
            context=AgentContext(image_id="image-1", bbox=[0, 0, 20, 20]),
        )
        provider = FakeProvider(
            IntentPlan(
                intent=IntentType.TEXT_EDIT,
                refined_prompt="clean background",
                target_tool="comfyui_text_edit_v1",
                params={"new_text": "  Hello  "},
            )
        )
        plan = await plan_intent(request, provider)
        assert not plan.clarification_required
        assert plan.params["new_text"] == "Hello"

    asyncio.run(run())


def test_disabled_capability_rejects_plan() -> None:
    async def run() -> None:
        request = AgentPlanRequest(
            user_message="draw",
            context=AgentContext(capabilities={"txt2img": False}),
        )
        provider = FakeProvider(
            IntentPlan(
                intent=IntentType.TXT2IMG,
                refined_prompt="draw",
                target_tool="comfyui_txt2img_v1",
            )
        )
        with pytest.raises(RoutingValidationError):
            await plan_intent(request, provider)

    asyncio.run(run())


def test_api_key_hash_is_peppered_and_deterministic() -> None:
    pepper = "p" * 32
    assert hash_api_key("infd_example", pepper) == hash_api_key("infd_example", pepper)
    assert hash_api_key("infd_example", pepper) != hash_api_key("infd_other", pepper)
    with pytest.raises(ValueError):
        hash_api_key("infd_example", "short")


def test_job_idempotency_and_event_sequences() -> None:
    async def run() -> None:
        repository = MemoryJobRepository()
        submission = JobSubmit(kind="agent_route", payload={"user_message": "cat"})
        first, created = await repository.submit("owner", submission, "same")
        second, created_again = await repository.submit("owner", submission, "same")
        assert created is True
        assert created_again is False
        assert first.id == second.id
        events = await repository.events(first.id)
        assert [event.sequence for event in events] == [1]

    asyncio.run(run())


def test_idempotency_key_rejects_different_payload() -> None:
    async def run() -> None:
        job_repository = MemoryJobRepository()
        first = JobSubmit(kind="txt2img", payload={"prompt": "cat"})
        second = JobSubmit(kind="txt2img", payload={"prompt": "dog"})
        await job_repository.submit("owner", first, "same")
        with pytest.raises(IdempotencyConflict):
            await job_repository.submit("owner", second, "same")

    asyncio.run(run())


def test_job_retry_then_dead_letter() -> None:
    async def run() -> None:
        repository = MemoryJobRepository()
        job, _ = await repository.submit(
            "owner",
            JobSubmit(
                kind="agent_route",
                payload={"user_message": "cat"},
                max_retries=1,
            ),
            None,
        )
        await repository.acquire(job.id, "worker")
        retried = await repository.finish(job.id, error={"code": "failed"})
        assert retried.status == JobStatus.RETRYING
        await repository.acquire(job.id, "worker")
        dead = await repository.finish(job.id, error={"code": "failed"})
        assert dead.status == JobStatus.DEAD_LETTER
        assert [event.sequence for event in await repository.events(job.id)] == [1, 2, 3, 4, 5]

    asyncio.run(run())


def test_cancel_queued_job_is_terminal() -> None:
    async def run() -> None:
        repository = MemoryJobRepository()
        job, _ = await repository.submit(
            "owner",
            JobSubmit(kind="agent_route", payload={"user_message": "cat"}),
            None,
        )
        cancelled = await repository.cancel(job.id, "owner")
        assert cancelled is not None
        assert cancelled.status == JobStatus.CANCELLED

    asyncio.run(run())


def test_upload_validation_checks_signature_and_pixels() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
    png = buffer.getvalue()
    assert validate_upload_image(png, "image/png")[:2] == (8, 8)
    assert validate_upload_image(png, "")[2] == "image/png"
    assert validate_upload_image(png, None)[2] == "image/png"
    with pytest.raises(HTTPException) as exc:
        validate_upload_image(png, "image/jpeg")
    assert exc.value.status_code == 415


def test_production_configuration_fails_fast() -> None:
    config = Settings(environment="production", debug=False)
    with pytest.raises(RuntimeError, match="Invalid production configuration"):
        config.validate_runtime()


def test_request_id_and_jobs_api_idempotency() -> None:
    with TestClient(app) as client:
        headers = {"Idempotency-Key": "api-test-idempotency", "X-Request-ID": "request-123"}
        first = client.post(
            "/api/v1/jobs",
            headers=headers,
            json={"kind": "agent_route", "payload": {"user_message": "cat"}},
        )
        second = client.post(
            "/api/v1/jobs",
            headers=headers,
            json={"kind": "agent_route", "payload": {"user_message": "cat"}},
        )
    assert first.status_code == 202
    assert first.headers["X-Request-ID"] == "request-123"
    assert first.json()["id"] == second.json()["id"]


def test_unified_validation_error_response() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/jobs", json={"kind": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "request_id" in response.json()


def test_jobs_api_validates_artifact_ownership_and_public_queue() -> None:
    with TestClient(app) as client:
        image_job = client.post(
            "/api/v1/jobs",
            json={
                "kind": "inpaint",
                "payload": {
                    "image": {"artifact_id": "b48c26d0-d05a-4da6-b60c-30d588eef254"},
                    "mask": {"artifact_id": "09365bc5-bf4c-441d-ad78-77b69f741485"},
                    "prompt": "repair",
                },
            },
        )
        queue_override = client.post(
            "/api/v1/jobs",
            json={"kind": "txt2img", "payload": {"prompt": "cat"}, "queue": "jobs:api"},
        )
    assert image_job.status_code == 404
    assert queue_override.status_code == 422


def test_public_job_kinds_all_have_worker_handlers() -> None:
    from app.worker import JOB_HANDLERS

    assert set(JOB_HANDLERS) == set(PUBLIC_JOB_KINDS)


def test_jobs_api_returns_409_for_idempotency_conflict() -> None:
    key = "conflict-api-test"
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/jobs",
            headers={"Idempotency-Key": key},
            json={"kind": "txt2img", "payload": {"prompt": "cat"}},
        )
        second = client.post(
            "/api/v1/jobs",
            headers={"Idempotency-Key": key},
            json={"kind": "txt2img", "payload": {"prompt": "dog"}},
        )
    assert first.status_code == 202
    assert second.status_code == 409


def test_sse_resumes_from_last_event_id_and_keeps_terminal_event() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/jobs",
            json={"kind": "agent_route", "payload": {"user_message": "cat"}},
        ).json()
        cancelled = client.post(f"/api/v1/jobs/{created['id']}/cancel")
        response = client.get(
            f"/api/v1/jobs/{created['id']}/events",
            headers={"Last-Event-ID": "1"},
        )
    assert cancelled.status_code == 200
    assert response.status_code == 200
    assert "id: 2" in response.text
    assert "event: cancelled" in response.text


def test_sse_emits_heartbeat_without_short_busy_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        job, _ = await repository.submit(
            "development",
            JobSubmit(kind="agent_route", payload={"user_message": "cat"}),
            None,
        )
        monkeypatch.setattr("app.api.jobs.settings.sse_heartbeat_seconds", 0.0)
        monkeypatch.setattr("app.api.jobs.settings.sse_poll_seconds", 0.0)
        stream = _stream_events(job.id, "development", 1)
        assert await anext(stream) == ": heartbeat\n\n"
        await stream.aclose()

    asyncio.run(run())


def test_api_key_authenticator_uses_indexed_locator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pepper = "p" * 32
    monkeypatch.setattr("app.production.auth.settings.api_key_pepper", pepper)
    raw_key = generate_api_key()
    locator = api_key_locator(raw_key)
    assert locator is not None
    key_authenticator = ApiKeyAuthenticator()
    principal = ApiPrincipal("key-1", frozenset({"jobs:read"}))
    key_authenticator.register_hash(locator, hash_api_key(raw_key, pepper), principal)
    assert key_authenticator.verify(raw_key) == principal
    assert key_authenticator.verify(generate_api_key()) is None


def test_legacy_websocket_rejects_missing_key_when_auth_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.production.auth.settings.auth_required", True)
    monkeypatch.setattr("app.production.auth.settings.api_key_pepper", "p" * 32)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/v1/ws?task_id=unknown"):
                pass
    assert exc.value.code == 4401


def test_generate_task_binding_uses_authenticated_principal() -> None:
    task = TaskState(task_id="generate-owner-task", prompt_id="prompt")
    task_manager.register(task)
    response = _bind_task_owner(
        task,
        ApiPrincipal("generate-owner", frozenset({"generate"})),
    )
    assert response.task_id == task.task_id
    assert task.owner_key_id == "generate-owner"


def test_legacy_websocket_allows_correct_owner_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pepper = "p" * 32
    raw_key = generate_api_key()
    locator = api_key_locator(raw_key)
    assert locator is not None
    principal = ApiPrincipal("ws-owner", frozenset({"generate"}))
    authenticator.register_hash(locator, hash_api_key(raw_key, pepper), principal)
    task = TaskState(
        task_id="owned-production-task",
        prompt_id="prompt",
        owner_key_id=principal.key_id,
    )
    task_manager.register(task)
    asyncio.run(task.emit_complete("/api/v1/files/outputs/owned.png"))
    monkeypatch.setattr("app.production.auth.settings.auth_required", True)
    monkeypatch.setattr("app.production.auth.settings.api_key_pepper", pepper)

    with TestClient(app) as client:
        monkeypatch.setattr(settings, "environment", "production")
        with client.websocket_connect(
            "/api/v1/ws?task_id=owned-production-task",
            headers={"X-API-Key": raw_key},
        ) as websocket:
            event = websocket.receive_json()
    assert event["type"] == "complete"
    assert event["image_url"].endswith("owned.png")


def test_legacy_websocket_hides_foreign_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pepper = "p" * 32
    raw_key = generate_api_key()
    locator = api_key_locator(raw_key)
    assert locator is not None
    principal = ApiPrincipal("wrong-owner", frozenset({"jobs:read"}))
    authenticator.register_hash(locator, hash_api_key(raw_key, pepper), principal)
    task_manager.register(
        TaskState(
            task_id="foreign-task",
            prompt_id="prompt",
            owner_key_id="actual-owner",
        )
    )
    monkeypatch.setattr("app.production.auth.settings.auth_required", True)
    monkeypatch.setattr("app.production.auth.settings.api_key_pepper", pepper)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                "/api/v1/ws?task_id=foreign-task",
                headers={"X-API-Key": raw_key},
            ):
                pass
        with pytest.raises(WebSocketDisconnect) as unknown_exc:
            with client.websocket_connect(
                "/api/v1/ws?task_id=absent-task",
                headers={"X-API-Key": raw_key},
            ):
                pass
    assert exc.value.code == 4404
    assert unknown_exc.value.code == exc.value.code


def test_txt2img_worker_handler_persists_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def run() -> None:
        job_repository = MemoryJobRepository()
        job, _ = await job_repository.submit(
            "owner",
            JobSubmit(kind="txt2img", payload={"prompt": "cat"}),
            None,
        )
        assert job.queue == settings.queue_gpu
        output_path = tmp_path / "cat.png"
        Image.new("RGB", (4, 4), "red").save(output_path)
        task = TaskState(
            task_id="task-1",
            prompt_id="prompt-1",
            image_path=output_path,
        )
        await task.emit_complete("/api/v1/files/outputs/cat.png")

        class FakeArtifactService:
            async def create_output(
                self,
                owner_key_id: str,
                job_id: str,
                path: Path,
            ) -> ArtifactResponse:
                assert owner_key_id == "owner"
                assert path == output_path
                return ArtifactResponse(
                    id="artifact-1",
                    job_id=job_id,
                    media_type="image/png",
                    size_bytes=64,
                    sha256="a" * 64,
                    content_url="/api/v1/artifacts/artifact-1/content",
                )

        async def fake_resolve(_backend: str) -> str:
            return "sd15"

        async def fake_execute(_plan: object, _inputs: object) -> TaskState:
            return task

        monkeypatch.setattr("app.worker.get_job_repository", lambda: job_repository)
        monkeypatch.setattr(
            "app.worker.get_artifact_service",
            lambda: FakeArtifactService(),
        )
        monkeypatch.setattr("app.worker.resolve_txt2img_backend", fake_resolve)
        monkeypatch.setattr("app.worker.execute_plan", fake_execute)

        from app.worker import execute_job

        result = await execute_job({}, job.id)
        persisted = await job_repository.get(job.id, "owner")
        assert result["status"] == "succeeded"
        assert persisted is not None
        assert persisted.status == JobStatus.SUCCEEDED
        assert persisted.result is not None
        assert persisted.result["primary_artifact"]["id"] == "artifact-1"

    asyncio.run(run())


def test_health_readiness_and_metrics_endpoints() -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        ready = client.get("/ready")
        metrics = client.get("/metrics")

    assert health.json() == {"status": "ok"}
    assert ready.json() == {"status": "ready"}
    assert metrics.status_code == 200
    assert "infdrawing_http_requests_total" in metrics.text
