from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.agent.orchestrator import execute_plan
from app.agent.schemas import GenerateTaskResponse, IntentPlan, IntentType
from app.config import settings
from app.pipeline.comfyui_client import ComfyUIClient
from app.pipeline.decompose import rembg_available
from app.pipeline.executor import TaskState, task_manager
from app.pipeline.image_providers import is_cloud_backend
from app.pipeline.image_providers.dashscope_decompose import (
    dashscope_decompose_available,
)
from app.pipeline.image_validation import (
    validate_inpaint_image_mask_pair,
    validate_upload_image,
)
from app.pipeline.text_detect import easyocr_available
from app.pipeline.txt2img_router import resolve_inpaint_backend, resolve_txt2img_backend
from app.production.auth import ApiPrincipal, current_principal
from app.storage.local import ensure_data_dirs, save_upload

router = APIRouter(prefix="/generate", tags=["generate"])


@router.post("/txt2img", response_model=GenerateTaskResponse)
async def generate_txt2img(
    prompt: str = Form(...),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly"),
    seed: int = Form(42),
    steps: int = Form(20),
    backend: str = Form("auto"),
    principal: ApiPrincipal = Depends(current_principal),
) -> GenerateTaskResponse:
    ensure_data_dirs()
    resolved_backend = await resolve_txt2img_backend(backend)
    task = await execute_plan(
        IntentPlan(
            intent=IntentType.TXT2IMG,
            refined_prompt=prompt,
            negative_prompt=negative_prompt,
            target_tool="comfyui_txt2img_v1",
        ),
        {"backend": resolved_backend, "seed": seed, "steps": steps},
    )
    return _bind_task_owner(task, principal)


@router.post("/inpaint", response_model=GenerateTaskResponse)
async def generate_inpaint(
    image: UploadFile = File(...),
    mask: UploadFile = File(...),
    prompt: str = Form(...),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly"),
    seed: int = Form(42),
    steps: int = Form(20),
    backend: str = Form("auto"),
    principal: ApiPrincipal = Depends(current_principal),
) -> GenerateTaskResponse:
    ensure_data_dirs()
    image_bytes = await image.read()
    mask_bytes = await mask.read()
    validate_inpaint_image_mask_pair(
        image_bytes,
        mask_bytes,
        image.content_type or "",
        mask.content_type or "",
    )

    resolved_backend = await resolve_inpaint_backend(backend)
    extras: dict = {
        "backend": resolved_backend,
        "seed": seed,
        "steps": steps,
        "image_bytes": image_bytes,
        "mask_bytes": mask_bytes,
        "image_media_type": image.content_type or "image/png",
        "mask_media_type": mask.content_type or "image/png",
    }

    if not is_cloud_backend(resolved_backend):
        image_path = save_upload(image.filename or "image.png", image_bytes)
        mask_path = save_upload(mask.filename or "mask.png", mask_bytes)
        client = ComfyUIClient()
        extras["image_name"] = await client.upload_image(image_path)
        extras["mask_name"] = await client.upload_image(mask_path)

    task = await execute_plan(
        IntentPlan(
            intent=IntentType.INPAINT,
            refined_prompt=prompt,
            negative_prompt=negative_prompt,
            target_tool="comfyui_inpaint_v1",
        ),
        extras,
    )
    return _bind_task_owner(task, principal)


@router.post("/image-edit", response_model=GenerateTaskResponse)
async def generate_image_edit(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly"),
    seed: int = Form(42),
    principal: ApiPrincipal = Depends(current_principal),
) -> GenerateTaskResponse:
    """Instruction-based image edit via OpenAI Images (no mask)."""
    if not settings.openai_api_key.strip():
        raise HTTPException(status_code=503, detail="OpenAI API key is not configured")
    ensure_data_dirs()
    image_bytes = await image.read()
    validate_upload_image(image_bytes, image.content_type)
    task = await execute_plan(
        IntentPlan(
            intent=IntentType.IMAGE_EDIT,
            refined_prompt=prompt,
            negative_prompt=negative_prompt,
            target_tool="openai_image_edit_v1",
        ),
        {
            "backend": "openai",
            "seed": seed,
            "image_bytes": image_bytes,
        },
    )
    return _bind_task_owner(task, principal)


@router.post("/decompose", response_model=GenerateTaskResponse)
async def generate_decompose(
    image: UploadFile = File(...),
    background_prompt: str = Form("clean seamless background, high quality"),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly"),
    principal: ApiPrincipal = Depends(current_principal),
) -> GenerateTaskResponse:
    """Split image into background + foreground layers (DashScope or rembg)."""
    if not dashscope_decompose_available() and not rembg_available():
        raise HTTPException(
            status_code=503,
            detail="decompose requires INFD_DASHSCOPE_API_KEY or rembg",
        )
    ensure_data_dirs()
    image_bytes = await image.read()
    validate_upload_image(image_bytes, image.content_type)
    task = await execute_plan(
        IntentPlan(
            intent=IntentType.DECOMPOSE,
            refined_prompt=background_prompt,
            negative_prompt=negative_prompt,
            target_tool="comfyui_decompose_v1",
        ),
        {"image_bytes": image_bytes},
    )
    return _bind_task_owner(task, principal)


@router.post("/text-edit", response_model=GenerateTaskResponse)
async def generate_text_edit(
    image: UploadFile = File(...),
    bbox: str = Form(...),
    new_text: str = Form(...),
    inpaint_prompt: str = Form("clean seamless background, high quality"),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly, text, letters"),
    principal: ApiPrincipal = Depends(current_principal),
) -> GenerateTaskResponse:
    """Erase text at bbox via inpaint; client overlays new_text on canvas."""
    if not easyocr_available():
        raise HTTPException(status_code=503, detail="easyocr not installed")
    ensure_data_dirs()
    image_bytes = await image.read()
    validate_upload_image(image_bytes, image.content_type)
    task = await execute_plan(
        IntentPlan(
            intent=IntentType.TEXT_EDIT,
            refined_prompt=inpaint_prompt,
            negative_prompt=negative_prompt,
            target_tool="comfyui_text_edit_v1",
        ),
        {"image_bytes": image_bytes, "bbox_json": bbox, "new_text": new_text},
    )
    return _bind_task_owner(task, principal)


def _bind_task_owner(
    task: TaskState,
    principal: ApiPrincipal,
) -> GenerateTaskResponse:
    task_manager.bind_owner(task.task_id, principal.key_id)
    return GenerateTaskResponse(task_id=task.task_id)
