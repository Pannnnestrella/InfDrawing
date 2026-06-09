from fastapi import APIRouter, File, Form, UploadFile

from app.agent.schemas import GenerateTaskResponse
from app.config import settings
from app.pipeline.comfyui_client import ComfyUIClient
from app.pipeline.executor import run_comfyui_task
from app.storage.local import ensure_data_dirs, save_upload

router = APIRouter(prefix="/generate", tags=["generate"])


@router.post("/txt2img", response_model=GenerateTaskResponse)
async def generate_txt2img(
    prompt: str = Form(...),
    negative_prompt: str = Form("blurry, low quality, distorted, ugly"),
    seed: int = Form(42),
    steps: int = Form(20),
) -> GenerateTaskResponse:
    ensure_data_dirs()
    client = ComfyUIClient()
    workflow = client.build_txt2img_workflow(
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
    image_path = save_upload(image.filename or "image.png", await image.read())
    mask_path = save_upload(mask.filename or "mask.png", await mask.read())

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
