"""Domain models for named asset libraries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DEFAULT_LIBRARY_NAME = "默认"
CaptionStatus = Literal["ok", "caption_failed"]

ASSET_TYPES: dict[str, str] = {
    "character": "角色",
    "creature": "生物",
    "weapon": "武器",
    "armor": "防具",
    "prop": "道具",
    "item": "物品",
    "environment": "场景",
    "architecture": "建筑",
    "vehicle": "载具",
    "ui": "界面",
    "icon": "图标",
    "vfx": "特效",
    "concept": "概念图",
    "other": "其他",
}
VIEWS: dict[str, str] = {
    "full_body": "全身",
    "bust": "半身",
    "face": "头像",
    "three_quarter": "四分之三侧",
    "side": "侧面",
    "back": "背面",
    "isometric": "等距",
    "top_down": "俯视",
    "close_up": "特写",
    "scene": "场景构图",
    "other": "其他",
}
GENRES: dict[str, str] = {
    "fantasy": "奇幻",
    "scifi": "科幻",
    "modern": "现代",
    "historical": "历史",
    "eastern": "东方",
    "horror": "恐怖",
    "anime": "二次元",
    "other": "其他",
}
BACKGROUNDS: dict[str, str] = {
    "environment": "实景/环境",
    "studio": "棚拍/灰底",
    "transparent": "透明底",
    "solid": "纯色底",
    "sky": "天空",
    "other": "其他",
}
POSES: dict[str, str] = {
    "standing": "站立",
    "action": "动作",
    "idle": "待机",
    "sitting": "坐/跪",
    "flying": "飞行",
    "none": "无（非角色）",
    "other": "其他",
}

_CHOICE_ALIASES: dict[str, dict[str, str]] = {
    "asset_type": {
        "角色": "character",
        "人物": "character",
        "角色原画": "character",
        "生物": "creature",
        "怪物": "creature",
        "武器": "weapon",
        "剑": "weapon",
        "防具": "armor",
        "盔甲": "armor",
        "道具": "prop",
        "物件": "prop",
        "物品": "item",
        "场景": "environment",
        "环境": "environment",
        "建筑": "architecture",
        "城堡": "architecture",
        "载具": "vehicle",
        "界面": "ui",
        "图标": "icon",
        "特效": "vfx",
        "概念图": "concept",
        "原画": "concept",
        "其他": "other",
    },
    "view": {
        "全身": "full_body",
        "fullbody": "full_body",
        "半身": "bust",
        "头像": "face",
        "面部": "face",
        "四分之三": "three_quarter",
        "3/4": "three_quarter",
        "侧面": "side",
        "背面": "back",
        "等距": "isometric",
        "俯视": "top_down",
        "topdown": "top_down",
        "特写": "close_up",
        "场景构图": "scene",
        "其他": "other",
    },
    "genre": {
        "奇幻": "fantasy",
        "幻想": "fantasy",
        "科幻": "scifi",
        "sci_fi": "scifi",
        "sci-fi": "scifi",
        "现代": "modern",
        "历史": "historical",
        "东方": "eastern",
        "恐怖": "horror",
        "二次元": "anime",
        "动漫": "anime",
        "其他": "other",
    },
    "background": {
        "环境": "environment",
        "实景": "environment",
        "棚拍": "studio",
        "灰底": "studio",
        "透明": "transparent",
        "透明底": "transparent",
        "纯色": "solid",
        "纯色底": "solid",
        "天空": "sky",
        "其他": "other",
    },
    "pose": {
        "站立": "standing",
        "站姿": "standing",
        "动作": "action",
        "战斗": "action",
        "待机": "idle",
        "坐": "sitting",
        "跪": "sitting",
        "飞行": "flying",
        "无": "none",
        "其他": "other",
    },
}


def normalize_choice(raw: object, allowed: dict[str, str], aliases: dict[str, str]) -> str:
    """Map a VLM/user value onto a closed catalog code, or empty if unknown."""
    text = str(raw or "").strip()
    if not text:
        return ""
    key = text.casefold().replace("-", "_").replace(" ", "_")
    if key in allowed:
        return key
    mapped = aliases.get(key) or aliases.get(text)
    if mapped in allowed:
        return mapped
    return ""


def choice_search_blob(code: str, catalog: dict[str, str]) -> str:
    """Include both the code and its Chinese label in search text."""
    label = catalog.get(code, "")
    return f"{code} {label}".strip()


def new_id() -> str:
    """Return a random identifier for libraries and items."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def normalize_string_list(value: object, *, limit: int = 24) -> list[str]:
    """Deduplicate a free-text list while keeping order."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text[:80])
        if len(cleaned) >= limit:
            break
    return cleaned


class AssetLibrary(BaseModel):
    """A named collection owned by one API principal."""

    id: str
    owner_key_id: str
    name: str
    purpose: str = ""
    created_at: datetime
    updated_at: datetime

    @field_validator("purpose", mode="before")
    @classmethod
    def _library_purpose(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()[:240]


class AssetItem(BaseModel):
    """One stored image plus searchable caption fields."""

    id: str
    owner_key_id: str
    library_id: str
    artifact_id: str
    title: str
    objects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    description: str = ""
    style: str = ""
    source_project: str = ""
    character_name: str = ""
    content_sha256: str = ""
    asset_type: str = ""
    view: str = ""
    genre: str = ""
    background: str = ""
    pose: str = ""
    palette: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    caption_status: CaptionStatus = "ok"
    caption_error: str | None = None
    shape_feat: list[float] | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("asset_type", mode="before")
    @classmethod
    def _item_asset_type(cls, value: object) -> str:
        return normalize_choice(value, ASSET_TYPES, _CHOICE_ALIASES["asset_type"])

    @field_validator("view", mode="before")
    @classmethod
    def _item_view(cls, value: object) -> str:
        return normalize_choice(value, VIEWS, _CHOICE_ALIASES["view"])

    @field_validator("genre", mode="before")
    @classmethod
    def _item_genre(cls, value: object) -> str:
        return normalize_choice(value, GENRES, _CHOICE_ALIASES["genre"])

    @field_validator("background", mode="before")
    @classmethod
    def _item_background(cls, value: object) -> str:
        return normalize_choice(value, BACKGROUNDS, _CHOICE_ALIASES["background"])

    @field_validator("pose", mode="before")
    @classmethod
    def _item_pose(cls, value: object) -> str:
        return normalize_choice(value, POSES, _CHOICE_ALIASES["pose"])

    @field_validator("keywords", "objects", "tags", "palette", "materials", mode="before")
    @classmethod
    def _item_string_list(cls, value: object) -> list[str]:
        return normalize_string_list(value)

    @field_validator("source_project", "character_name", mode="before")
    @classmethod
    def _item_short_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()[:240]

    def search_blob(self) -> str:
        """Concatenate caption and game-catalog fields for substring search."""
        return " ".join(
            [
                self.title,
                self.description,
                self.style,
                *self.tags,
                *self.keywords,
                *self.objects,
                *self.palette,
                *self.materials,
                self.source_project,
                self.character_name,
                choice_search_blob(self.asset_type, ASSET_TYPES),
                choice_search_blob(self.view, VIEWS),
                choice_search_blob(self.genre, GENRES),
                choice_search_blob(self.background, BACKGROUNDS),
                choice_search_blob(self.pose, POSES),
            ]
        )


class CaptionDraft(BaseModel):
    """Validated VLM caption used to fill an item."""

    title: str = ""
    objects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    style: str = ""
    asset_type: str = ""
    view: str = ""
    genre: str = ""
    background: str = ""
    pose: str = ""
    palette: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)

    @field_validator("title", "description", "style", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("asset_type", mode="before")
    @classmethod
    def _asset_type(cls, value: object) -> str:
        return normalize_choice(value, ASSET_TYPES, _CHOICE_ALIASES["asset_type"])

    @field_validator("view", mode="before")
    @classmethod
    def _view(cls, value: object) -> str:
        return normalize_choice(value, VIEWS, _CHOICE_ALIASES["view"])

    @field_validator("genre", mode="before")
    @classmethod
    def _genre(cls, value: object) -> str:
        return normalize_choice(value, GENRES, _CHOICE_ALIASES["genre"])

    @field_validator("background", mode="before")
    @classmethod
    def _background(cls, value: object) -> str:
        return normalize_choice(value, BACKGROUNDS, _CHOICE_ALIASES["background"])

    @field_validator("pose", mode="before")
    @classmethod
    def _pose(cls, value: object) -> str:
        return normalize_choice(value, POSES, _CHOICE_ALIASES["pose"])

    @field_validator("objects", "tags", "palette", "materials", mode="before")
    @classmethod
    def _string_list(cls, value: object) -> list[str]:
        return normalize_string_list(value)


class LibraryCreateRequest(BaseModel):
    """Body for creating a named library."""

    name: str = Field(min_length=1, max_length=80)
    purpose: str = Field(default="", max_length=240)


class LibraryPatchRequest(BaseModel):
    """Partial update for a library's name or purpose."""

    name: str | None = Field(default=None, max_length=80)
    purpose: str | None = Field(default=None, max_length=240)


class ItemPatchRequest(BaseModel):
    """Partial update for a stored asset."""

    library_id: str | None = None
    title: str | None = None
    objects: list[str] | None = None
    tags: list[str] | None = None
    keywords: list[str] | None = None
    description: str | None = None
    style: str | None = None
    source_project: str | None = None
    character_name: str | None = None
    asset_type: str | None = None
    view: str | None = None
    genre: str | None = None
    background: str | None = None
    pose: str | None = None
    palette: list[str] | None = None
    materials: list[str] | None = None
