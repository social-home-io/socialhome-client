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
    FederationBaseUpdate,
    ShoppingItem,
    Space,
    SpaceBot,
    SpaceBotWithToken,
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


def test_space_bot_disabled_by_default():
    sp = Space.from_api({"id": "s1", "name": "Family"})
    assert sp.bot_enabled is False
    assert sp.emoji is None


def test_space_bot_enabled_roundtrip():
    sp = Space.from_api({"id": "s1", "name": "Family", "bot_enabled": True})
    assert sp.bot_enabled is True


def test_conversation_defaults_to_dm():
    conv = Conversation.from_api({"id": "c1", "display_name": "Bob"})
    assert conv.type == "dm"
    assert conv.bot_enabled is False


def test_conversation_bot_enabled_roundtrip():
    conv = Conversation.from_api({"id": "c1", "display_name": "Bob", "bot_enabled": True})
    assert conv.bot_enabled is True


def test_space_bot_from_api_full():
    bot = SpaceBot.from_api(
        {
            "bot_id": "b1",
            "space_id": "s1",
            "scope": "space",
            "slug": "doorbell",
            "name": "Doorbell",
            "icon": "🔔",
            "created_by": "u-alice",
            "created_at": "2026-04-23T10:00:00+00:00",
        }
    )
    assert bot.scope == "space"
    assert bot.slug == "doorbell"
    # SpaceBot never carries a token; any leak would be a bug.
    assert not hasattr(bot, "token")


def test_space_bot_unknown_scope_defaults_to_member():
    # Forward-compat: backend could add new scopes; fall back to the
    # lowest-privilege attribution rather than blowing up.
    bot = SpaceBot.from_api(
        {
            "bot_id": "b1",
            "space_id": "s1",
            "scope": "future-scope-we-dont-know",
            "slug": "x",
            "name": "X",
            "icon": "❓",
            "created_by": "u1",
            "created_at": "2026-04-23T10:00:00+00:00",
        }
    )
    assert bot.scope == "member"


def test_space_bot_with_token_from_api():
    bot = SpaceBotWithToken.from_api(
        {
            "bot_id": "b1",
            "space_id": "s1",
            "scope": "member",
            "slug": "gym",
            "name": "Gym",
            "icon": "⏱️",
            "created_by": "u-pascal",
            "created_at": "2026-04-23T10:00:00+00:00",
            "token": "shb_plaintext",
        }
    )
    assert bot.token == "shb_plaintext"
    # SpaceBotWithToken subclasses SpaceBot — callers can pass it where
    # a SpaceBot is expected (after capturing the token separately).
    assert isinstance(bot, SpaceBot)


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


def test_federation_base_update_full_shape():
    update = FederationBaseUpdate.from_api(
        {
            "ok": True,
            "base": "https://external.example.org",
            "changed": True,
            "peers_notified": 5,
        }
    )
    assert update.ok is True
    assert update.base == "https://external.example.org"
    assert update.changed is True
    assert update.peers_notified == 5


def test_federation_base_update_defaults_are_safe():
    # Server can omit ``peers_notified`` when there are no peers to
    # notify; ``from_api`` must not raise KeyError and must default
    # to a non-negative int.
    update = FederationBaseUpdate.from_api({"ok": True, "base": "https://x.test"})
    assert update.changed is False
    assert update.peers_notified == 0
