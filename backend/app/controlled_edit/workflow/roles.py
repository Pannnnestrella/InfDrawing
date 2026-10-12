"""Match scene entities to workflow role tokens (not absolute entity ids)."""

from __future__ import annotations

from app.controlled_edit.schemas import SceneEntity


def entity_role(entity: SceneEntity) -> str:
    """Return the leaf segment of a dotted entity id (e.g. ``face``)."""
    return entity.id.split(".")[-1].lower()


def role_token(value: str) -> str:
    """Normalize a role or entity id to a comparable leaf token."""
    cleaned = value.strip().lower()
    if "." in cleaned:
        return cleaned.split(".")[-1]
    return cleaned


def match_roles(entities: list[SceneEntity], roles: list[str]) -> list[SceneEntity]:
    """Return entities whose leaf id or name matches any requested role."""
    wanted = {role_token(role) for role in roles if role.strip()}
    if not wanted:
        return []
    matched: list[SceneEntity] = []
    seen: set[str] = set()
    for entity in entities:
        tokens = {entity_role(entity), entity.name.strip().lower(), role_token(entity.id)}
        if tokens & wanted and entity.id not in seen:
            matched.append(entity)
            seen.add(entity.id)
    return matched


def locked_roles(entities: list[SceneEntity]) -> list[str]:
    """Extract unique role tokens for currently locked entities."""
    roles: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        if entity.status.value != "locked":
            continue
        role = entity_role(entity)
        if role not in seen:
            roles.append(role)
            seen.add(role)
    return roles
