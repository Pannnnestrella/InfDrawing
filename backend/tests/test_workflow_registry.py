"""Tests for the declarative workflow registry and generic builder."""

import pytest

from app.pipeline.comfyui_client import ComfyUIClient
from app.pipeline.workflow_registry import WORKFLOWS, get_workflow_spec


def test_get_workflow_spec_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_workflow_spec("nope")


def test_registry_covers_bundled_templates() -> None:
    client = ComfyUIClient()
    assert client.has_workflow_template("sd15_txt2img")
    assert client.has_workflow_template("sd15_inpaint")


def test_spec_inputs_match_template_nodes() -> None:
    """Every registered (node_id, input_key) slot must exist in its template."""
    client = ComfyUIClient()
    for name, spec in WORKFLOWS.items():
        if not client.has_workflow_template(name):
            continue  # e.g. flux template is optional
        template = client.load_workflow(spec.template)
        for param, (node_id, input_key) in spec.inputs.items():
            assert node_id in template, f"{name}.{param}: node {node_id} missing"
            assert input_key in template[node_id]["inputs"], (
                f"{name}.{param}: input {input_key} missing on node {node_id}"
            )


def test_build_workflow_writes_named_params() -> None:
    client = ComfyUIClient()
    workflow = client.build_workflow(
        "sd15_txt2img", prompt="a cat", negative_prompt="ugly", seed=7, steps=12
    )
    assert workflow["2"]["inputs"]["text"] == "a cat"
    assert workflow["3"]["inputs"]["text"] == "ugly"
    assert workflow["5"]["inputs"]["seed"] == 7
    assert workflow["5"]["inputs"]["steps"] == 12
    assert workflow["5"]["inputs"]["cfg"] == 7.0  # default applied


def test_build_workflow_rejects_unknown_param() -> None:
    client = ComfyUIClient()
    with pytest.raises(KeyError):
        client.build_workflow("sd15_txt2img", prompt="x", bogus=1)


def test_inpaint_wrapper_maps_image_and_mask() -> None:
    client = ComfyUIClient()
    workflow = client.build_inpaint_workflow(
        image_name="img.png", mask_name="mask.png", prompt="p", negative_prompt="n"
    )
    assert workflow["2"]["inputs"]["image"] == "img.png"
    assert workflow["3"]["inputs"]["image"] == "mask.png"
    assert workflow["8"]["inputs"]["denoise"] == 1.0
