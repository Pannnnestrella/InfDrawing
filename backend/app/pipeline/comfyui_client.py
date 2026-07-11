import json
import shutil
import uuid
from copy import deepcopy
from pathlib import Path

import httpx

from app.config import settings
from app.pipeline.workflow_registry import get_workflow_spec


class ComfyUIClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.comfyui_base_url).rstrip("/")
        self.workflows_dir = Path(__file__).resolve().parent / "workflows"

    def load_workflow(self, name: str) -> dict:
        path = self.workflows_dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    def has_workflow_template(self, workflow_name: str) -> bool:
        """Return True when the registered workflow's template file exists."""
        spec = get_workflow_spec(workflow_name)
        return (self.workflows_dir / spec.template).exists()

    def build_workflow(self, workflow_name: str, **params: object) -> dict:
        """Instantiate a registered workflow template with named parameters."""
        spec = get_workflow_spec(workflow_name)
        values = {**spec.defaults, **params}
        unknown = set(values) - set(spec.inputs)
        if unknown:
            raise KeyError(
                f"unknown parameter(s) {sorted(unknown)} for workflow {workflow_name!r}"
            )
        workflow = deepcopy(self.load_workflow(spec.template))
        for name, value in values.items():
            node_id, input_key = spec.inputs[name]
            workflow[node_id]["inputs"][input_key] = value
        return workflow

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

    def build_txt2img_workflow(self, **params: object) -> dict:
        return self.build_workflow("sd15_txt2img", **params)

    def has_flux_txt2img_workflow(self) -> bool:
        """Return True when a Flux txt2img workflow template is present."""
        return self.has_workflow_template("flux_txt2img")

    def build_flux_txt2img_workflow(self, **params: object) -> dict:
        """Build Flux Schnell workflow (requires flux_schnell_txt2img_api.json)."""
        return self.build_workflow("flux_txt2img", **params)

    def build_inpaint_workflow(self, **params: object) -> dict:
        return self.build_workflow("sd15_inpaint", **params)

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
