import json
import shutil
import uuid
from copy import deepcopy
from pathlib import Path

import httpx

from app.config import settings


class ComfyUIClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.comfyui_base_url).rstrip("/")
        self.workflows_dir = Path(__file__).resolve().parent / "workflows"

    def load_workflow(self, name: str) -> dict:
        path = self.workflows_dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    async def upload_image(self, file_path: Path) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with file_path.open("rb") as handle:
                response = await client.post(
                    f"{self.base_url}/upload/image",
                    files={"image": (file_path.name, handle, "application/octet-stream")},
                    data={"overwrite": "true"},
                )
            response.raise_for_status()
            return response.json()["name"]

    async def queue_prompt(self, workflow: dict, client_id: str | None = None) -> str:
        client_id = client_id or str(uuid.uuid4())
        payload = {"prompt": workflow, "client_id": client_id}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.base_url}/prompt", json=payload)
            response.raise_for_status()
            return response.json()["prompt_id"]

    async def get_history(self, prompt_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/history/{prompt_id}")
            response.raise_for_status()
            return response.json()

    def build_txt2img_workflow(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        seed: int = 42,
        steps: int = 20,
        cfg: float = 7.0,
    ) -> dict:
        workflow = deepcopy(self.load_workflow("sd15_txt2img_api.json"))
        workflow["2"]["inputs"]["text"] = prompt
        workflow["3"]["inputs"]["text"] = negative_prompt
        workflow["5"]["inputs"].update({"seed": seed, "steps": steps, "cfg": cfg})
        return workflow

    def build_inpaint_workflow(
        self,
        *,
        image_name: str,
        mask_name: str,
        prompt: str,
        negative_prompt: str,
        seed: int = 42,
        steps: int = 20,
        cfg: float = 7.0,
        denoise: float = 1.0,
    ) -> dict:
        workflow = deepcopy(self.load_workflow("sd15_inpaint_api.json"))
        workflow["2"]["inputs"]["image"] = image_name
        workflow["3"]["inputs"]["image"] = mask_name
        workflow["5"]["inputs"]["text"] = prompt
        workflow["6"]["inputs"]["text"] = negative_prompt
        workflow["8"]["inputs"].update(
            {"seed": seed, "steps": steps, "cfg": cfg, "denoise": denoise}
        )
        return workflow

    async def copy_output_image(self, prompt_id: str, dest_dir: Path) -> Path | None:
        history = await self.get_history(prompt_id)
        entry = history.get(prompt_id, {})
        outputs = entry.get("outputs", {})
        for node_output in outputs.values():
            for image in node_output.get("images", []):
                filename = image["filename"]
                subfolder = image.get("subfolder", "")
                comfy_output = settings.comfyui_output_dir
                if subfolder:
                    comfy_output = comfy_output / subfolder
                src = comfy_output / filename
                if not src.exists():
                    continue
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / f"{prompt_id}_{filename}"
                shutil.copy2(src, dest)
                return dest
        return None
