"""Caption schema validation."""

import pytest

from app.assets.caption_parser import CaptionParseError, caption_from_reply


def test_caption_from_reply_trims_and_dedupes() -> None:
    draft = caption_from_reply(
        {
            "title": "  骑士  ",
            "objects": ["剑", "剑", " 盾 ", ""],
            "tags": "奇幻",
            "description": "夜色中的骑士。",
            "style": "油画",
            "asset_type": "角色",
            "view": "全身",
            "genre": "fantasy",
            "background": "environment",
            "pose": "standing",
            "palette": ["红", "金"],
            "materials": ["金属", "布料"],
        }
    )
    assert draft.title == "骑士"
    assert draft.objects == ["剑", "盾"]
    assert draft.tags == ["奇幻"]
    assert draft.asset_type == "character"
    assert draft.view == "full_body"
    assert draft.palette == ["红", "金"]
    assert "夜色" in draft.description


def test_caption_from_reply_rejects_empty() -> None:
    with pytest.raises(CaptionParseError):
        caption_from_reply({"title": "", "objects": [], "tags": [], "description": ""})
