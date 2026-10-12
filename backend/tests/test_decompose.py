"""Tests for decompose helpers."""

import asyncio
import io
import sys
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.pipeline.decompose import foreground_to_inpaint_mask, rembg_available
from app.pipeline.image_providers.dashscope_decompose import instance_mask_to_rgba
from app.pipeline.image_providers.dashscope_wanx import _contains_oss_url


def test_rembg_available_false_when_onnxruntime_missing() -> None:
    real_import = __import__

    def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "onnxruntime":
            raise ImportError("no onnxruntime")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert rembg_available() is False


def test_rembg_available_false_on_system_exit() -> None:
    real_import = __import__

    def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "rembg":
            sys.exit(1)
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert rembg_available() is False


def test_foreground_to_inpaint_mask_inverts_alpha() -> None:
    image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    mask = foreground_to_inpaint_mask(image)
    assert mask.mode == "L"
    center = mask.getpixel((2, 2))
    assert center == 0

    transparent = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    mask_bg = foreground_to_inpaint_mask(transparent)
    assert mask_bg.getpixel((2, 2)) == 255


def test_instance_mask_to_rgba_keeps_nonzero_ids() -> None:
    source = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(source, format="PNG")
    mask_buf = io.BytesIO()
    mask = Image.new("RGB", (4, 4), (0, 0, 0))
    mask.putpixel((1, 1), (2, 0, 0))
    mask.save(mask_buf, format="PNG")
    rgba = instance_mask_to_rgba(source.getvalue(), mask_buf.getvalue())
    assert rgba.getpixel((1, 1))[3] == 255
    assert rgba.getpixel((0, 0))[3] == 0


def test_contains_oss_url_walks_nested_payload() -> None:
    assert _contains_oss_url({"input": {"image_url": "oss://dashscope/tmp.png"}}) is True
    assert _contains_oss_url({"input": {"image_url": "https://example.com/a.png"}}) is False


def test_infer_corner_chroma_when_corners_agree() -> None:
    from app.pipeline.image_providers.dashscope_decompose import infer_corner_chroma

    image = Image.new("RGB", (20, 20), (12, 200, 12))
    image.putpixel((10, 10), (255, 0, 0))
    assert infer_corner_chroma(image) == (12, 200, 12)


def test_apply_chroma_alpha_keeps_source_rgb() -> None:
    source = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(source, format="PNG")
    plate = Image.new("RGB", (4, 4), (255, 0, 255))
    plate.putpixel((1, 1), (10, 20, 30))
    plate_buf = io.BytesIO()
    plate.save(plate_buf, format="PNG")
    from app.pipeline.image_providers.dashscope_decompose import apply_chroma_alpha

    rgba = apply_chroma_alpha(source.getvalue(), plate_buf.getvalue())
    assert rgba.getpixel((1, 1)) == (10, 20, 30, 255)
    assert rgba.getpixel((0, 0))[3] == 0


def _png(color: tuple[int, int, int], size: tuple[int, int] = (80, 80)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_named_prompt_ignores_blank_and_legacy_defaults() -> None:
    from app.pipeline.image_providers.dashscope_decompose import (
        is_named_decompose_prompt,
    )

    assert is_named_decompose_prompt("") is False
    assert is_named_decompose_prompt("  ") is False
    assert is_named_decompose_prompt("clean seamless background, high quality") is False
    assert is_named_decompose_prompt("Clean Seamless Background") is False
    assert is_named_decompose_prompt("剑、盾") is True


def test_parse_named_targets_caps_and_skips_blanks() -> None:
    from app.pipeline.image_providers.dashscope_decompose import parse_named_targets

    payload = {
        "targets": [
            {"name": "", "label": "空"},
            *[{"name": f"object {index}", "label": f"物体{index}"} for index in range(7)],
        ]
    }
    targets = parse_named_targets(payload)
    assert len(targets) == 6
    assert targets[0].label == "物体0"
    assert targets[-1].name == "object 5"


def test_small_subject_matte_keeps_a_thin_object() -> None:
    from app.pipeline.image_providers.base import ImageProviderError
    from app.pipeline.image_providers.dashscope_decompose import matte_from_plate

    source = _png((10, 20, 30))
    plate = Image.new("RGB", (80, 80), (255, 0, 255))
    for x in range(8):
        for y in range(8):
            plate.putpixel((20 + x, 20 + y), (10, 20, 30))
    plate_buf = io.BytesIO()
    plate.save(plate_buf, format="PNG")
    rgba = matte_from_plate(source, plate_buf.getvalue(), small_subject=True)
    assert rgba.getpixel((24, 24))[3] == 255
    assert rgba.getpixel((0, 0))[3] == 0
    try:
        matte_from_plate(source, plate_buf.getvalue(), small_subject=False)
    except ImageProviderError:
        return
    raise AssertionError("default matte should reject a thin object")


def test_split_named_layers_orders_background_first() -> None:
    from app.pipeline.image_providers.dashscope_decompose import (
        DashScopeDecomposeClient,
        NamedTarget,
    )

    plate = Image.new("RGB", (80, 80), (255, 0, 255))
    for x in range(10):
        for y in range(10):
            plate.putpixel((x, y), (10, 20, 30))
    plate_buf = io.BytesIO()
    plate.save(plate_buf, format="PNG")
    prompts: list[str] = []

    async def edit(**kwargs: object) -> bytes:
        prompt = str(kwargs["prompt"])
        prompts.append(prompt)
        if prompt.startswith("Remove only"):
            return _png((1, 2, 3))
        return plate_buf.getvalue()

    async def scenario() -> None:
        client = DashScopeDecomposeClient.__new__(DashScopeDecomposeClient)
        client._qwen = AsyncMock()
        client._qwen.multi_image_edit = AsyncMock(side_effect=edit)
        targets = [
            NamedTarget(name="the longsword", label="长剑"),
            NamedTarget(name="the shield", label="盾"),
        ]
        with patch(
            "app.pipeline.image_providers.dashscope_decompose.recognize_named_targets",
            new=AsyncMock(return_value=targets),
        ):
            layers = await client.split_named_layers(_png((10, 20, 30)), "剑、盾")
        assert [label for label, _png_bytes in layers] == ["background", "长剑", "盾"]
        assert "the longsword" in prompts[0]
        assert "the shield" in prompts[1]
        assert "the longsword" in prompts[2] and "the shield" in prompts[2]

    asyncio.run(scenario())


def test_executor_routes_blank_prompt_to_two_layers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.pipeline.decompose_executor import run_decompose_task

    foreground = Image.new("RGBA", (8, 8), (9, 9, 9, 255))

    async def scenario() -> None:
        with (
            patch(
                "app.pipeline.decompose_executor.dashscope_decompose_available",
                return_value=True,
            ),
            patch("app.pipeline.decompose_executor.DashScopeDecomposeClient") as client_cls,
        ):
            client = client_cls.return_value
            client.split_layers = AsyncMock(return_value=(foreground, _png((4, 5, 6), (8, 8))))
            client.split_named_layers = AsyncMock()
            task = await run_decompose_task(
                image_bytes=_png((1, 1, 1), (8, 8)),
                outputs_dir=tmp_path,
                background_prompt="clean seamless background, high quality",
            )
            for _ in range(50):
                if task.is_terminal:
                    break
                await asyncio.sleep(0)
        assert task.status == "complete"
        labels = [layer["label"] for layer in task.last_event["layers"]]
        assert labels == ["background", "foreground"]
        client.split_named_layers.assert_not_called()

    asyncio.run(scenario())


def test_executor_named_failure_does_not_fall_back(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.pipeline.decompose_executor import run_decompose_task
    from app.pipeline.image_providers.base import ImageProviderError

    async def scenario() -> None:
        with (
            patch(
                "app.pipeline.decompose_executor.dashscope_decompose_available",
                return_value=True,
            ),
            patch(
                "app.pipeline.decompose_executor.extract_foreground_rgba",
                side_effect=AssertionError("rembg fallback"),
            ),
            patch("app.pipeline.decompose_executor.DashScopeDecomposeClient") as client_cls,
        ):
            client = client_cls.return_value
            client.split_named_layers = AsyncMock(
                side_effect=ImageProviderError("没有从提示里识别出要拆开的物体")
            )
            task = await run_decompose_task(
                image_bytes=_png((1, 1, 1), (8, 8)),
                outputs_dir=tmp_path,
                background_prompt="剑、盾",
            )
            for _ in range(50):
                if task.is_terminal:
                    break
                await asyncio.sleep(0)
        assert task.status == "error"
        assert "没有从提示里识别出要拆开的物体" in (task.error or "")

    asyncio.run(scenario())
