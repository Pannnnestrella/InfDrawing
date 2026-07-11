"""Declarative registry of ComfyUI workflow templates.

Adding a new generation mode = drop a template JSON into ``workflows/`` and
register a :class:`WorkflowSpec` here; no node-id plumbing elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkflowSpec:
    """A workflow template plus its named parameters.

    ``inputs`` maps a parameter name to the ``(node_id, input_key)`` slot in
    the template JSON that receives it. ``defaults`` are applied for
    parameters the caller omits.
    """

    template: str
    inputs: dict[str, tuple[str, str]]
    defaults: dict[str, Any] = field(default_factory=dict)


WORKFLOWS: dict[str, WorkflowSpec] = {
    "sd15_txt2img": WorkflowSpec(
        template="sd15_txt2img_api.json",
        inputs={
            "prompt": ("2", "text"),
            "negative_prompt": ("3", "text"),
            "seed": ("5", "seed"),
            "steps": ("5", "steps"),
            "cfg": ("5", "cfg"),
        },
        defaults={"seed": 42, "steps": 20, "cfg": 7.0},
    ),
    "flux_txt2img": WorkflowSpec(
        template="flux_schnell_txt2img_api.json",
        inputs={
            "prompt": ("2", "text"),
            "negative_prompt": ("3", "text"),
            "seed": ("5", "seed"),
            "steps": ("5", "steps"),
            "cfg": ("5", "cfg"),
        },
        defaults={"seed": 42, "steps": 4, "cfg": 1.0},
    ),
    "sd15_inpaint": WorkflowSpec(
        template="sd15_inpaint_api.json",
        inputs={
            "image_name": ("2", "image"),
            "mask_name": ("3", "image"),
            "prompt": ("5", "text"),
            "negative_prompt": ("6", "text"),
            "seed": ("8", "seed"),
            "steps": ("8", "steps"),
            "cfg": ("8", "cfg"),
            "denoise": ("8", "denoise"),
        },
        defaults={"seed": 42, "steps": 20, "cfg": 7.0, "denoise": 1.0},
    ),
}


def get_workflow_spec(name: str) -> WorkflowSpec:
    spec = WORKFLOWS.get(name)
    if spec is None:
        raise KeyError(f"unknown workflow: {name!r}")
    return spec
