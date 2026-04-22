"""Typed dataclasses mirroring API response bodies.

Every public :class:`SocialHomeClient` method returns one of these
(or a list of them) — never a raw ``dict``. Spec §6.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    notify_enabled: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Space:
        return cls(
            id=data["id"],
            name=data["name"],
            emoji=data.get("emoji"),
            notify_enabled=bool(data.get("notify_enabled", False)),
        )


@dataclass(slots=True, frozen=True)
class Conversation:
    id: str
    display_name: str
    type: str  # "dm" | "group"
    notify_enabled: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Conversation:
        return cls(
            id=data["id"],
            display_name=data["display_name"],
            type=data.get("type", "dm"),
            notify_enabled=bool(data.get("notify_enabled", False)),
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
