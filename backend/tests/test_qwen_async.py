"""Tests for Qwen 2.1 asynchronous submission and recoverable task polling."""

import json

import httpx
import pytest

from app.config import Settings, settings
from app.pipeline.image_providers.base import ImageProviderError
from app.pipeline.image_providers.dashscope_qwen_edit import DashScopeQwenEditProvider


def config() -> Settings:
    """Return isolated configuration without real credentials."""
    return settings.model_copy(
        update={
            "dashscope_api_key": "test",
            "cedit_image_model": "qwen-image-2.1-pro",
            "cloud_image_poll_seconds": 0.01,
        }
    )


@pytest.mark.asyncio
async def test_async_submit_poll_and_download() -> None:
    """Submit once, poll pending/running, and decode the documented choices response."""
    requests = []
    polls = 0

    def reply(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        requests.append(request)
        if request.url.path.endswith("/uploads"):
            assert request.url.params["model"] == "qwen-image-2.1-pro"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "upload_host": "https://upload.example.com",
                        "upload_dir": "test",
                        "oss_access_key_id": "upload-key",
                        "signature": "signature",
                        "policy": "policy",
                    }
                },
            )
        if request.url.host == "upload.example.com":
            return httpx.Response(200)
        if request.method == "POST":
            assert request.url.path.endswith("/image-generation/generation")
            assert request.headers["X-DashScope-Async"] == "enable"
            assert "X-DashScope-OssResourceResolve" not in request.headers
            body = json.loads(request.content)
            assert body["parameters"]["n"] == 1
            assert len(body["input"]["messages"][0]["content"]) == 3
            assert body["input"]["messages"][0]["content"][0]["image"].startswith("data:")
            return httpx.Response(
                200, json={"output": {"task_id": "task-1"}, "request_id": "req-1"}
            )
        if request.url.path.endswith("/tasks/task-1"):
            polls += 1
            if polls < 3:
                return httpx.Response(
                    200,
                    json={
                        "output": {
                            "task_status": "PENDING" if polls == 1 else "RUNNING",
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "choices": [
                            {"message": {"content": [{"image": "https://example.com/out.png"}]}}
                        ],
                    }
                },
            )
        return httpx.Response(200, content=b"image-result")

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        provider = DashScopeQwenEditProvider(config(), client)
        result = await provider.multi_image_edit(
            image_bytes=b"source", reference_images=[b"mask"], prompt="recolor"
        )
    assert result == b"image-result"
    assert sum(r.method == "POST" and r.url.path.endswith("/generation") for r in requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["FAILED", "CANCELED", "UNKNOWN", "invalid"])
async def test_terminal_task_errors_do_not_resubmit(state: str) -> None:
    """Terminal failures carry the existing task ID and never issue a new POST."""

    def reply(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json={"output": {"task_status": state, "message": "failure"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(ImageProviderError, match="task_id=existing"):
            await DashScopeQwenEditProvider(config(), client).wait_edit_task("existing")


@pytest.mark.asyncio
async def test_poll_deadline_preserves_task_id() -> None:
    """A local deadline leaves the paid task resumable by its identifier."""

    def reply(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(ImageProviderError, match="resume this task"):
            await DashScopeQwenEditProvider(config(), client).wait_edit_task(
                "existing", timeout_seconds=0.02
            )


@pytest.mark.asyncio
async def test_legacy_qwen_2_remains_synchronous() -> None:
    """Older models keep their supported synchronous endpoint."""

    def reply(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path.endswith("/multimodal-generation/generation")
            assert "X-DashScope-Async" not in request.headers
            return httpx.Response(
                200,
                json={
                    "output": {
                        "choices": [
                            {
                                "message": {
                                    "content": [{"image": "https://example.com/out.png"}],
                                }
                            }
                        ]
                    }
                },
            )
        return httpx.Response(200, content=b"image")

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        older = config().model_copy(update={"cedit_image_model": "qwen-image-2.0"})
        assert (
            await DashScopeQwenEditProvider(older, client).multi_image_edit(
                image_bytes=b"source", reference_images=[], prompt="edit"
            )
            == b"image"
        )


@pytest.mark.asyncio
async def test_poll_transport_retry_only_repeats_get() -> None:
    """An interrupted status query retries the same task without duplicate generation."""
    polls = 0

    def reply(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        assert request.method == "GET"
        polls += 1
        if polls == 1:
            raise httpx.ReadTimeout("temporary", request=request)
        return httpx.Response(200, json={"output": {"task_status": "FAILED"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(ImageProviderError, match="FAILED"):
            await DashScopeQwenEditProvider(config(), client).wait_edit_task("existing")
    assert polls == 2
