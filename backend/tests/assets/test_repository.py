"""In-memory repository search and ownership."""

from __future__ import annotations

import asyncio

from app.assets.repository import MemoryAssetRepository, item_matches_query
from app.assets.schemas import AssetItem, AssetLibrary, utc_now


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _item(**kwargs: object) -> AssetItem:
    now = utc_now()
    payload: dict[str, object] = {
        "id": "i1",
        "owner_key_id": "key-1",
        "library_id": "lib-1",
        "artifact_id": "art-1",
        "title": "红披风骑士",
        "objects": ["骑士", "长剑"],
        "tags": ["奇幻", "角色"],
        "description": "夜景城堡前的骑士。",
        "style": "电影光，冷色调",
        "asset_type": "character",
        "genre": "fantasy",
        "created_at": now,
        "updated_at": now,
    }
    payload.update(kwargs)
    return AssetItem.model_validate(payload)


def test_list_items_filters_by_query_and_library() -> None:
    repo = MemoryAssetRepository()
    now = utc_now()

    async def scenario() -> None:
        await repo.save_library(
            AssetLibrary(
                id="lib-1",
                owner_key_id="key-1",
                name="角色",
                created_at=now,
                updated_at=now,
            )
        )
        await repo.save_item(
            _item(
                id="k",
                source_project="骑士demo",
                character_name="女剑士",
                keywords=["持剑"],
            )
        )
        await repo.save_item(
            _item(
                id="c",
                library_id="lib-2",
                title="城堡",
                objects=["城堡"],
                tags=["场景"],
                description="白天的石堡。",
                style="水彩",
            )
        )
        await repo.save_item(_item(id="o", owner_key_id="key-2", title="骑士"))
        hits = await repo.list_items("key-1", query="夜景")
        assert [item.id for item in hits] == ["k"]
        by_lib = await repo.list_items("key-1", library_id="lib-2")
        assert [item.id for item in by_lib] == ["c"]
        by_project = await repo.list_items("key-1", query="骑士demo")
        assert [item.id for item in by_project] == ["k"]
        by_character = await repo.list_items("key-1", query="女剑士")
        assert [item.id for item in by_character] == ["k"]
        by_keyword = await repo.list_items("key-1", query="持剑")
        assert [item.id for item in by_keyword] == ["k"]

    _run(scenario())


def test_find_item_by_sha256_is_owner_scoped() -> None:
    repo = MemoryAssetRepository()

    async def scenario() -> None:
        await repo.save_item(_item(id="k", content_sha256="abc", source_project="骑士demo"))
        await repo.save_item(_item(id="o", owner_key_id="key-2", content_sha256="abc"))
        found = await repo.find_item_by_sha256("key-1", "ABC")
        assert found is not None and found.id == "k"
        missing = await repo.find_item_by_sha256("key-1", "nope")
        assert missing is None

    _run(scenario())


def test_legacy_item_defaults_empty_metadata() -> None:
    item = _item()
    assert item.keywords == []
    assert item.source_project == ""
    assert item.character_name == ""
    assert item.content_sha256 == ""
    now = utc_now()
    library = AssetLibrary(
        id="lib-1",
        owner_key_id="key-1",
        name="角色",
        created_at=now,
        updated_at=now,
    )
    assert library.purpose == ""


def test_item_matches_query_on_style() -> None:
    assert item_matches_query(_item(), "冷色")
    assert item_matches_query(_item(), "角色")
    assert not item_matches_query(_item(), "赛博")
