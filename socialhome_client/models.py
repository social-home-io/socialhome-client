"""Typed dataclasses mirroring API response bodies.

Every public :class:`SocialHomeClient` method returns one of these
(or a list of them) — never a raw ``dict``. Spec §6.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True, frozen=True)
class User:
    user_id: str
    username: str
    display_name: str
    is_admin: bool

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> User:
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            display_name=data["display_name"],
            is_admin=bool(data.get("is_admin", False)),
        )


@dataclass(slots=True, frozen=True)
class ShoppingItem:
    id: str
    name: str
    checked: bool
    order: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ShoppingItem:
        return cls(
            id=data["id"],
            name=data["name"],
            checked=bool(data.get("checked", False)),
            order=int(data.get("order", 0)),
        )


@dataclass(slots=True, frozen=True)
class Calendar:
    id: str
    name: str
    color: str
    owner_username: str
    type: str  # "personal" | "space"

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Calendar:
        return cls(
            id=data["id"],
            name=data["name"],
            color=data.get("color", ""),
            owner_username=data.get("owner_username", ""),
            type=data.get("type", "personal"),
        )


@dataclass(slots=True, frozen=True)
class CalendarEvent:
    id: str
    calendar_id: str
    summary: str
    start_at: str
    end_at: str
    all_day: bool
    description: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> CalendarEvent:
        return cls(
            id=data["id"],
            calendar_id=data["calendar_id"],
            summary=data["summary"],
            start_at=data["start_at"],
            end_at=data["end_at"],
            all_day=bool(data.get("all_day", False)),
            description=data.get("description"),
        )


@dataclass(slots=True, frozen=True)
class Space:
    id: str
    name: str
    emoji: str | None = None
    # True when an admin has opted this space in to receiving posts from
    # Home Assistant bots via the bot-bridge. Formerly called
    # ``notify_enabled``; renamed to match the bot-personas feature.
    bot_enabled: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Space:
        return cls(
            id=data["id"],
            name=data["name"],
            emoji=data.get("emoji"),
            bot_enabled=bool(data.get("bot_enabled", False)),
        )


@dataclass(slots=True, frozen=True)
class Conversation:
    id: str
    display_name: str
    type: str  # "dm" | "group"
    # True when at least one participant has opted this DM in to receiving
    # system-authored posts from Home Assistant automations. DMs have no
    # named bots — the 1:1 context makes a generic "Home Assistant"
    # sender adequate, so this is a simple on/off.
    bot_enabled: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Conversation:
        return cls(
            id=data["id"],
            display_name=data["display_name"],
            type=data.get("type", "dm"),
            bot_enabled=bool(data.get("bot_enabled", False)),
        )


@dataclass(slots=True, frozen=True)
class SpaceBot:
    """A named bot persona registered against a space.

    Returned by :meth:`SocialHomeClient.bot.list` and
    :meth:`SocialHomeClient.bot.update`. *Never* carries the Bearer
    token — that only surfaces on :class:`SpaceBotWithToken`, so any
    object of type :class:`SpaceBot` is safe to log.
    """

    bot_id: str
    space_id: str
    # "space" = admin-curated shared bot; "member" = personal automation.
    scope: Literal["space", "member"]
    slug: str
    name: str
    icon: str
    created_by: str
    created_at: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> SpaceBot:
        scope = data.get("scope", "member")
        if scope not in ("space", "member"):
            # Defensive narrowing — the API only ever sends these two,
            # but a future backend could introduce new scopes; default
            # to "member" to fail safely (less-privileged attribution).
            scope = "member"
        return cls(
            bot_id=data["bot_id"],
            space_id=data["space_id"],
            scope=scope,
            slug=data["slug"],
            name=data["name"],
            icon=data["icon"],
            created_by=data["created_by"],
            created_at=data["created_at"],
        )


@dataclass(slots=True, frozen=True)
class SpaceBotWithToken(SpaceBot):
    """A :class:`SpaceBot` plus its plaintext Bearer token.

    Returned *only* from :meth:`SocialHomeClient.bot.create` and
    :meth:`SocialHomeClient.bot.rotate_token` — the backend exposes the
    plaintext token exactly once per lifecycle event. Persist it
    somewhere safe; a second fetch will not return it. The superclass
    :class:`SpaceBot` deliberately excludes this field so normal reads
    can't accidentally carry a secret.
    """

    token: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> SpaceBotWithToken:
        scope = data.get("scope", "member")
        if scope not in ("space", "member"):
            scope = "member"
        return cls(
            bot_id=data["bot_id"],
            space_id=data["space_id"],
            scope=scope,
            slug=data["slug"],
            name=data["name"],
            icon=data["icon"],
            created_by=data["created_by"],
            created_at=data["created_at"],
            token=data["token"],
        )


@dataclass(slots=True, frozen=True)
class UnreadSummary:
    total: int
    feed: int
    dms: int
    spaces: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> UnreadSummary:
        return cls(
            total=int(data.get("total", 0)),
            feed=int(data.get("feed", 0)),
            dms=int(data.get("dms", 0)),
            spaces={k: int(v) for k, v in (data.get("spaces") or {}).items()},
        )
