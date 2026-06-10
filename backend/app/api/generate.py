from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.agent.schemas import GenerateTaskResponse
from app.config import settings
from app.pipeline.comfyui_client import ComfyUIClient
from app.pipeline.decompose import rembg_available
from app.pipeline.decompose_executor import run_decompose_task
from app.pipeline.text_detect import easyocr_available
from app.pipeline.text_edit_executor import run_text_edit_task
from app.pipeline.executor import run_comfyui_task
from app.pipeline.image_validation import validate_inpaint_image_mask_pair
from app.pipeline.txt2img_router import build_txt2img_workflow_for_backend, resolve_txt2img_backend
from app.storage.local import ensure_data_dirs, save_upload

router = APIRouter(prefix="/generate", tags=["generate"])


@router.post("/txt2img", response_model=GenerateTaskResponse)
async def generate_txt2img(
    prompt: str = Form(...),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly"),
    seed: int = Form(42),
    steps: int = Form(20),
    backend: str = Form("auto"),
) -> GenerateTaskResponse:
    ensure_data_dirs()
    resolved_backend = await resolve_txt2img_backend(backend)
    client = ComfyUIClient()
    workflow = await build_txt2img_workflow_for_backend(
        client,
        resolved_backend,
        prompt=prompt,
        negative_prompt=negative_prompt,
        seed=seed,
        steps=steps,
    )
    task = await run_comfyui_task(workflow=workflow, outputs_dir=settings.outputs_dir)
    return GenerateTaskResponse(task_id=task.task_id)


@router.post("/inpaint", response_model=GenerateTaskResponse)
async def generate_inpaint(
    image: UploadFile = File(...),
    mask: UploadFile = File(...),
    prompt: str = Form(...),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly"),
    seed: int = Form(42),
    steps: int = Form(20),
) -> GenerateTaskResponse:
    ensure_data_dirs()
    image_bytes = await image.read()
    mask_bytes = await mask.read()
    validate_inpaint_image_mask_pair(image_bytes, mask_bytes)

    image_path = save_upload(image.filename or "image.png", image_bytes)
    mask_path = save_upload(mask.filename or "mask.png", mask_bytes)

    client = ComfyUIClient()
    image_name = await client.upload_image(image_path)
    mask_name = await client.upload_image(mask_path)
    workflow = client.build_inpaint_workflow(
        image_name=image_name,
        mask_name=mask_name,
        prompt=prompt,
        negative_prompt=negative_prompt,
        seed=seed,
        steps=steps,
    )
    task = await run_comfyui_task(workflow=workflow, outputs_dir=settings.outputs_dir)
    return GenerateTaskResponse(task_id=task.task_id)


@router.post("/decompose", response_model=GenerateTaskResponse)
async def generate_decompose(
    image: UploadFile = File(...),
    background_prompt: str = Form("clean seamless background, high quality"),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly"),
) -> GenerateTaskResponse:
    """Split image into background + foreground layers (rembg + SD1.5 inpaint)."""
    if not rembg_available():
        raise HTTPException(status_code=503, detail="rembg not installed")
    ensure_data_dirs()
    image_bytes = await image.read()
    task = await run_decompose_task(
        image_bytes=image_bytes,
        outputs_dir=settings.outputs_dir,
        background_prompt=background_prompt,
        negative_prompt=negative_prompt,
    )
    return GenerateTaskResponse(task_id=task.task_id)


@router.post("/text-edit", response_model=GenerateTaskResponse)
async def generate_text_edit(
    image: UploadFile = File(...),
    bbox: str = Form(...),
    new_text: str = Form(...),
    inpaint_prompt: str = Form("clean seamless background, high quality"),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly, text, letters"),
) -> GenerateTaskResponse:
    """Erase text at bbox via inpaint; client overlays new_text on canvas."""
    if not easyocr_available():
        raise HTTPException(status_code=503, detail="easyocr not installed")
    ensure_data_dirs()
    image_bytes = await image.read()
    task = await run_text_edit_task(
        image_bytes=image_bytes,
        bbox_json=bbox,
        new_text=new_text,
        outputs_dir=settings.outputs_dir,
        inpaint_prompt=inpaint_prompt,
        negative_prompt=negative_prompt,
    )
    return GenerateTaskResponse(task_id=task.task_id)
