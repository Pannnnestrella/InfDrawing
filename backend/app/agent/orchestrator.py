"""Unified dispatch from validated intent plans to registered tools."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import IntentPlan, IntentType
from app.agent.tools import TOOL_REGISTRY
from app.config import settings
from app.pipeline.cloud_executor import (
    run_cloud_image_edit_task,
    run_cloud_inpaint_task,
    run_cloud_txt2img_task,
)
from app.pipeline.comfyui_client import ComfyUIClient
from app.pipeline.decompose_executor import run_decompose_task
from app.pipeline.executor import TaskState, run_comfyui_task
from app.pipeline.image_providers import is_cloud_backend
from app.pipeline.image_validation import validate_inpaint_image_mask_pair
from app.pipeline.text_edit_executor import run_text_edit_task
from app.pipeline.txt2img_router import build_txt2img_workflow_for_backend
from app.storage.local import save_upload


class OrchestrationError(ValueError):
    """Raised when a plan cannot be executed safely."""


async def execute_plan(plan: IntentPlan, inputs: dict[str, Any]) -> TaskState:
    """Execute a validated plan through the shared tool registry."""
    if plan.clarification_required:
        raise OrchestrationError(plan.clarification_question or "clarification required")
    registration = TOOL_REGISTRY.get(plan.target_tool)
    if registration is None or registration["intent"] != plan.intent:
        raise OrchestrationError("unregistered or inconsistent target tool")

    if plan.intent == IntentType.DECOMPOSE:
        return await run_decompose_task(
            image_bytes=_required_bytes(inputs, "image_bytes"),
            outputs_dir=settings.outputs_dir,
            background_prompt=plan.refined_prompt,
            negative_prompt=plan.negative_prompt,
        )
    if plan.intent == IntentType.TEXT_EDIT:
        return await run_text_edit_task(
            image_bytes=_required_bytes(inputs, "image_bytes"),
            bbox_json=str(inputs["bbox_json"]),
            new_text=str(inputs["new_text"]),
            outputs_dir=settings.outputs_dir,
            inpaint_prompt=plan.refined_prompt,
            negative_prompt=plan.negative_prompt,
        )

    params = {**plan.params, **inputs}
    backend = str(params.pop("backend", "sd15"))

    if plan.intent == IntentType.IMAGE_EDIT:
        # Instruction edit is OpenAI-only for this release.
        return await run_cloud_image_edit_task(
            backend="openai",
            image_bytes=_required_bytes(params, "image_bytes"),
            prompt=plan.refined_prompt,
            negative_prompt=plan.negative_prompt,
            seed=int(params.pop("seed", 42)),
            outputs_dir=settings.outputs_dir,
        )

    if plan.intent == IntentType.TXT2IMG and is_cloud_backend(backend):
        return await run_cloud_txt2img_task(
            backend=backend,
            prompt=plan.refined_prompt,
            negative_prompt=plan.negative_prompt,
            seed=int(params.pop("seed", 42)),
            outputs_dir=settings.outputs_dir,
        )

    if plan.intent == IntentType.INPAINT and is_cloud_backend(backend):
        image_bytes, mask_bytes = _inpaint_bytes(params)
        return await run_cloud_inpaint_task(
            backend=backend,
            image_bytes=image_bytes,
            mask_bytes=mask_bytes,
            prompt=plan.refined_prompt,
            negative_prompt=plan.negative_prompt,
            seed=int(params.pop("seed", 42)),
            outputs_dir=settings.outputs_dir,
        )

    client = ComfyUIClient()
    if plan.intent == IntentType.TXT2IMG:
        workflow = await build_txt2img_workflow_for_backend(
            client,
            backend,
            prompt=plan.refined_prompt,
            negative_prompt=plan.negative_prompt,
            seed=int(params.pop("seed", 42)),
            steps=int(params.pop("steps", 20)),
        )
    elif plan.intent == IntentType.INPAINT:
        image_name = params.get("image_name")
        mask_name = params.get("mask_name")
        if image_name is None or mask_name is None:
            image_bytes, mask_bytes = _inpaint_bytes(params)
            image_media_type = str(params.get("image_media_type", "image/png"))
            mask_media_type = str(params.get("mask_media_type", "image/png"))
            validate_inpaint_image_mask_pair(
                image_bytes,
                mask_bytes,
                image_media_type,
                mask_media_type,
            )
            image_path = save_upload("job-image.png", image_bytes)
            mask_path = save_upload("job-mask.png", mask_bytes)
            image_name = await client.upload_image(image_path)
            mask_name = await client.upload_image(mask_path)
        workflow = client.build_inpaint_workflow(
            image_name=str(image_name),
            mask_name=str(mask_name),
            prompt=plan.refined_prompt,
            negative_prompt=plan.negative_prompt,
            seed=int(params.get("seed", 42)),
            steps=int(params.get("steps", 20)),
        )
    else:
        raise OrchestrationError(f"unsupported intent: {plan.intent}")
    return await run_comfyui_task(workflow=workflow, outputs_dir=settings.outputs_dir)


def _inpaint_bytes(params: dict[str, Any]) -> tuple[bytes, bytes]:
    return (
        _required_bytes(params, "image_bytes"),
        _required_bytes(params, "mask_bytes"),
    )


def _required_bytes(inputs: dict[str, Any], key: str) -> bytes:
    value = inputs.get(key)
    if not isinstance(value, bytes):
        raise OrchestrationError(f"{key} is required")
    return value
