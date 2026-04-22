"""Tests for :mod:`socialhome_client.models`.

``from_api`` classmethods are the only behaviour worth testing —
they defend the public dataclasses from API shape drift (missing
fields, wrong types, nulls).
"""

from __future__ import annotations

from socialhome_client import (
    Calendar,
    CalendarEvent,
    Conversation,
    ShoppingItem,
    Space,
    UnreadSummary,
    User,
)


def test_user_from_api_minimal():
    u = User.from_api({"user_id": "u1", "username": "alice", "display_name": "Alice"})
    assert u.user_id == "u1"
    assert u.is_admin is False


def test_user_from_api_admin():
    u = User.from_api(
        {
            "user_id": "u1",
            "username": "alice",
            "display_name": "Alice",
            "is_admin": True,
        }
    )
    assert u.is_admin is True


def test_shopping_item_defaults():
    item = ShoppingItem.from_api({"id": "i1", "name": "milk"})
    assert item.checked is False
    assert item.order == 0


def test_calendar_parses_type():
    cal = Calendar.from_api(
        {
            "id": "c1",
            "name": "Family",
            "color": "#fff",
            "owner_username": "alice",
            "type": "space",
        }
    )
    assert cal.type == "space"
    assert cal.owner_username == "alice"


def test_calendar_event_optional_description():
    ev = CalendarEvent.from_api(
        {
            "id": "e1",
            "calendar_id": "c1",
            "summary": "Dentist",
            "start_at": "2026-05-01T09:00:00Z",
            "end_at": "2026-05-01T10:00:00Z",
            "all_day": False,
        }
    )
    assert ev.description is None


def test_space_notify_disabled_by_default():
    sp = Space.from_api({"id": "s1", "name": "Family"})
    assert sp.notify_enabled is False
    assert sp.emoji is None


def test_conversation_defaults_to_dm():
    conv = Conversation.from_api({"id": "c1", "display_name": "Bob"})
    assert conv.type == "dm"


def test_unread_summary_spaces_coerced_to_ints():
    summary = UnreadSummary.from_api(
        {
            "total": "3",  # tolerate stringly-typed counts
            "feed": 1,
            "dms": 0,
            "spaces": {"s1": "2"},
        }
    )
    assert summary.total == 3
    assert summary.spaces == {"s1": 2}


def test_unread_summary_empty_spaces():
    summary = UnreadSummary.from_api({"total": 0, "feed": 0, "dms": 0})
    assert summary.spaces == {}
