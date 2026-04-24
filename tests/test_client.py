"""Tests for :mod:`socialhome_client.client`.

Each HTTP method is stubbed with :mod:`aioresponses`; we never touch
the network. Tests are grouped under section banners that mirror the
client's resource sub-clients (``c.me`` / ``c.shopping`` / ``c.bot`` /
…). Each resource's happy path and one or two edge cases are covered.
"""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest
from aioresponses import aioresponses
from yarl import URL

from socialhome_client import (
    Calendar,
    CalendarEvent,
    Conversation,
    FederationBaseUpdate,
    SHAuthError,
    SHClientError,
    SHNotFoundError,
    ShoppingItem,
    SocialHomeClient,
    Space,
    SpaceBot,
    SpaceBotWithToken,
    UnreadSummary,
    User,
)

# ── Session / context manager ─────────────────────────────────────────────


async def test_context_manager_closes_owned_session():
    async with SocialHomeClient("http://sh.test", token="t") as c:
        await c._session_once()
        assert c._session is not None
    assert c._session is None


async def test_external_session_not_closed_by_client():
    async with aiohttp.ClientSession() as sess:
        c = SocialHomeClient("http://sh.test", token="t", session=sess)
        await c.close()
        assert not sess.closed


async def test_base_url_strips_trailing_slash():
    c = SocialHomeClient("http://sh.test/", token="t")
    assert c.base_url == "http://sh.test"
    await c.close()


# ── Error mapping (shared by all resources) ───────────────────────────────


async def test_401_raises_auth_error(client: SocialHomeClient):
    with aioresponses() as m:
        m.get("http://sh.test/api/me", status=401)
        with pytest.raises(SHAuthError):
            await client.me.get()


async def test_404_raises_not_found(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/shopping-list/items/missing",
            status=404,
            payload={"error": {"message": "no such item"}},
        )
        with pytest.raises(SHNotFoundError) as exc_info:
            await client.get("/api/shopping-list/items/missing")
    assert "no such item" in str(exc_info.value)


async def test_500_raises_generic_client_error(client: SocialHomeClient):
    with aioresponses() as m:
        m.get("http://sh.test/api/me", status=500)
        with pytest.raises(SHClientError) as exc_info:
            await client.me.get()
    assert exc_info.value.status == 500


async def test_transport_error_wrapped(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/me",
            exception=aiohttp.ClientError("connection reset"),
        )
        with pytest.raises(SHClientError) as exc_info:
            await client.me.get()
    assert exc_info.value.status is None


# ── c.me ──────────────────────────────────────────────────────────────────


async def test_me_get(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/me",
            payload={"user_id": "u1", "username": "alice", "display_name": "Alice"},
        )
        user = await client.me.get()
    assert isinstance(user, User)
    assert user.username == "alice"


async def test_me_create_token(client: SocialHomeClient):
    with aioresponses() as m:
        m.post("http://sh.test/api/me/tokens", payload={"token": "deadbeef"})
        token = await client.me.create_token("ha-integration")
    assert token == "deadbeef"


async def test_me_unread_summary(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/me/unread-summary",
            payload={"total": 4, "feed": 1, "dms": 2, "spaces": {"s1": 1}},
        )
        summary = await client.me.unread_summary()
    assert isinstance(summary, UnreadSummary)
    assert summary.total == 4
    assert summary.spaces == {"s1": 1}


# ── c.presence ────────────────────────────────────────────────────────────


async def test_presence_post_location(client: SocialHomeClient):
    with aioresponses() as m:
        m.post("http://sh.test/api/presence/location", status=204)
        await client.presence.post_location(
            "alice",
            latitude=52.5,
            longitude=13.4,
            accuracy_m=25.0,
            zone_name="home",
        )
        (call,) = m.requests[("POST", _url("/api/presence/location"))]
        assert call.kwargs["json"] == {
            "username": "alice",
            "latitude": 52.5,
            "longitude": 13.4,
            "accuracy_m": 25.0,
            "zone_name": "home",
        }


# ── c.space ───────────────────────────────────────────────────────────────


async def test_space_list(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/spaces",
            payload={"spaces": [{"id": "s1", "name": "Family"}]},
        )
        spaces = await client.space.list()
    assert spaces == [Space(id="s1", name="Family")]


async def test_space_update_bot_enabled(client: SocialHomeClient):
    with aioresponses() as m:
        m.patch(
            "http://sh.test/api/spaces/s1",
            payload={"id": "s1", "name": "Family", "bot_enabled": True},
        )
        sp = await client.space.update("s1", bot_enabled=True)
        (call,) = m.requests[("PATCH", _url("/api/spaces/s1"))]
        assert call.kwargs["json"] == {"bot_enabled": True}
    assert sp.bot_enabled is True


async def test_space_update_noop_sends_empty_body(client: SocialHomeClient):
    # No kwargs → empty payload. Useful because callers may branch
    # through this helper without always having something to set.
    with aioresponses() as m:
        m.patch(
            "http://sh.test/api/spaces/s1",
            payload={"id": "s1", "name": "Family"},
        )
        await client.space.update("s1")
        (call,) = m.requests[("PATCH", _url("/api/spaces/s1"))]
        assert call.kwargs["json"] == {}


# ── c.conversation ────────────────────────────────────────────────────────


async def test_conversation_list(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/conversations",
            payload={"conversations": [{"id": "c1", "display_name": "Bob"}]},
        )
        convs = await client.conversation.list()
    assert convs == [Conversation(id="c1", display_name="Bob", type="dm")]


# ── c.shopping ────────────────────────────────────────────────────────────


async def test_shopping_full_crud(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/shopping-list",
            payload={
                "items": [
                    {"id": "i1", "name": "milk", "checked": False, "order": 0},
                ],
            },
        )
        m.post(
            "http://sh.test/api/shopping-list/items",
            payload={"id": "i2", "name": "bread", "checked": False, "order": 1},
        )
        m.patch(
            "http://sh.test/api/shopping-list/items/i2",
            payload={"id": "i2", "name": "bread", "checked": True, "order": 1},
        )
        m.delete("http://sh.test/api/shopping-list/items/i2", status=204)
        m.post("http://sh.test/api/shopping-list/clear", status=204)

        items = await client.shopping.list()
        assert len(items) == 1 and items[0].name == "milk"

        added = await client.shopping.add("bread")
        assert isinstance(added, ShoppingItem)

        updated = await client.shopping.update("i2", checked=True)
        assert updated.checked is True

        await client.shopping.delete("i2")
        await client.shopping.clear()


async def test_shopping_update_only_sends_non_none(client: SocialHomeClient):
    with aioresponses() as m:
        m.patch(
            "http://sh.test/api/shopping-list/items/i1",
            payload={"id": "i1", "name": "eggs", "checked": False, "order": 0},
        )
        await client.shopping.update("i1", name="eggs")
        (call,) = m.requests[("PATCH", _url("/api/shopping-list/items/i1"))]
        assert call.kwargs["json"] == {"name": "eggs"}


# ── c.calendar ────────────────────────────────────────────────────────────


async def test_calendar_list_visible_and_events(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/calendars/visible",
            payload={
                "calendars": [
                    {
                        "id": "c1",
                        "name": "Family",
                        "color": "#f00",
                        "owner_username": "alice",
                        "type": "space",
                    }
                ],
            },
        )
        m.get(
            "http://sh.test/api/calendars/c1/events?start=S&end=E",
            payload={
                "events": [
                    {
                        "id": "e1",
                        "calendar_id": "c1",
                        "summary": "Dentist",
                        "start_at": "S",
                        "end_at": "E",
                        "all_day": False,
                    }
                ],
            },
        )
        cals = await client.calendar.list_visible()
        assert isinstance(cals[0], Calendar)

        events = await client.calendar.list_events("c1", "S", "E")
        assert isinstance(events[0], CalendarEvent)
        assert events[0].summary == "Dentist"


async def test_calendar_create_event_omits_description_when_none(
    client: SocialHomeClient,
):
    with aioresponses() as m:
        m.post(
            "http://sh.test/api/calendars/c1/events",
            payload={
                "id": "e1",
                "calendar_id": "c1",
                "summary": "Meeting",
                "start_at": "S",
                "end_at": "E",
                "all_day": False,
            },
        )
        await client.calendar.create_event("c1", "Meeting", start="S", end="E")
        (call,) = m.requests[("POST", _url("/api/calendars/c1/events"))]
        assert "description" not in call.kwargs["json"]


async def test_calendar_update_event_passthrough_kwargs(client: SocialHomeClient):
    with aioresponses() as m:
        m.patch(
            "http://sh.test/api/calendars/c1/events/e1",
            payload={
                "id": "e1",
                "calendar_id": "c1",
                "summary": "Moved",
                "start_at": "S2",
                "end_at": "E2",
                "all_day": False,
            },
        )
        ev = await client.calendar.update_event(
            "c1", "e1", summary="Moved", start_at="S2", end_at="E2"
        )
        assert ev.summary == "Moved"


async def test_calendar_delete_event(client: SocialHomeClient):
    with aioresponses() as m:
        m.delete("http://sh.test/api/calendars/c1/events/e1", status=204)
        await client.calendar.delete_event("c1", "e1")


# ── c.bot ─────────────────────────────────────────────────────────────────


def _bot_row(
    *,
    bot_id: str = "b1",
    space_id: str = "s1",
    scope: str = "space",
    slug: str = "doorbell",
    name: str = "Doorbell",
    icon: str = "🔔",
    created_by: str = "u1",
    token: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "bot_id": bot_id,
        "space_id": space_id,
        "scope": scope,
        "slug": slug,
        "name": name,
        "icon": icon,
        "created_by": created_by,
        "created_at": "2026-04-23T10:00:00+00:00",
    }
    if token is not None:
        row["token"] = token
    return row


async def test_bot_list(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/spaces/s1/bots",
            payload=[_bot_row(scope="space"), _bot_row(bot_id="b2", scope="member")],
        )
        bots = await client.bot.list("s1")
    assert [b.bot_id for b in bots] == ["b1", "b2"]
    assert all(isinstance(b, SpaceBot) for b in bots)
    # None of the list-response objects carry a token — only create +
    # rotate return SpaceBotWithToken. Typing should already enforce
    # this but double-checking the runtime shape guards against drift.
    assert all(not isinstance(b, SpaceBotWithToken) for b in bots)


async def test_bot_create_returns_plaintext_token(client: SocialHomeClient):
    with aioresponses() as m:
        m.post(
            "http://sh.test/api/spaces/s1/bots",
            payload=_bot_row(token="shb_abcdefghij"),
            status=201,
        )
        created = await client.bot.create(
            "s1", scope="space", slug="doorbell", name="Doorbell", icon="🔔"
        )
        (call,) = m.requests[("POST", _url("/api/spaces/s1/bots"))]
        assert call.kwargs["json"] == {
            "scope": "space",
            "slug": "doorbell",
            "name": "Doorbell",
            "icon": "🔔",
        }
    assert isinstance(created, SpaceBotWithToken)
    assert created.token == "shb_abcdefghij"


async def test_bot_update_partial_fields(client: SocialHomeClient):
    with aioresponses() as m:
        m.patch(
            "http://sh.test/api/spaces/s1/bots/b1",
            payload=_bot_row(name="Front door"),
        )
        updated = await client.bot.update("s1", "b1", name="Front door")
        (call,) = m.requests[("PATCH", _url("/api/spaces/s1/bots/b1"))]
        assert call.kwargs["json"] == {"name": "Front door"}
    assert updated.name == "Front door"


async def test_bot_delete(client: SocialHomeClient):
    with aioresponses() as m:
        m.delete("http://sh.test/api/spaces/s1/bots/b1", status=204)
        await client.bot.delete("s1", "b1")


async def test_bot_rotate_token_returns_new_secret(client: SocialHomeClient):
    with aioresponses() as m:
        m.post(
            "http://sh.test/api/spaces/s1/bots/b1/token",
            payload=_bot_row(token="shb_rotated_xyz"),
        )
        rotated = await client.bot.rotate_token("s1", "b1")
    assert isinstance(rotated, SpaceBotWithToken)
    assert rotated.token == "shb_rotated_xyz"


async def test_bot_post_uses_provided_bot_token(client: SocialHomeClient):
    # The space-post endpoint MUST authenticate with the per-bot token,
    # not the user API token. Verify by inspecting the Authorization
    # header on the captured request — if the session's default header
    # (Bearer tok) leaked through, this assertion fails.
    with aioresponses() as m:
        m.post("http://sh.test/api/bot-bridge/spaces/s1", status=201)
        await client.bot.post("s1", "shb_secret", title="Ring", message="Front door")
        (call,) = m.requests[("POST", _url("/api/bot-bridge/spaces/s1"))]
    assert call.kwargs["headers"]["Authorization"] == "Bearer shb_secret"
    assert call.kwargs["json"] == {"title": "Ring", "message": "Front door"}


async def test_bot_post_conversation_uses_user_token(client: SocialHomeClient):
    # DM bot-bridge posts go through the normal session. aioresponses
    # captures the merged request kwargs including the session's default
    # Authorization header, so the check here is: auth carries the USER
    # token ("tok" from conftest) — not a bot token.
    with aioresponses() as m:
        m.post("http://sh.test/api/bot-bridge/conversations/c1", status=201)
        await client.bot.post_conversation("c1", title=None, message="Laundry done")
        (call,) = m.requests[("POST", _url("/api/bot-bridge/conversations/c1"))]
    assert call.kwargs["headers"]["Authorization"] == "Bearer tok"
    assert call.kwargs["json"] == {"title": None, "message": "Laundry done"}


async def test_bot_post_disabled_space_raises_client_error(client: SocialHomeClient):
    # Backend returns 403 BOT_DISABLED when an admin has toggled off
    # bot posting for a space. Client surfaces that as SHClientError
    # with status=403 — callers can branch on exc.status to show
    # "bots are disabled for this space" rather than a generic error.
    with aioresponses() as m:
        m.post(
            "http://sh.test/api/bot-bridge/spaces/s1",
            status=403,
            payload={"error": {"code": "BOT_DISABLED", "message": "off"}},
        )
        with pytest.raises(SHClientError) as exc_info:
            await client.bot.post("s1", "shb_secret", title=None, message="blocked")
    assert exc_info.value.status == 403


# ── c.federation ──────────────────────────────────────────────────────────


async def test_federation_get_base_returns_current(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/ha/integration/federation-base",
            status=200,
            payload={"base": "https://external.example.org"},
        )
        assert await client.federation.get_base() == "https://external.example.org"


async def test_federation_get_base_returns_none_when_unset(client: SocialHomeClient):
    # Server returns ``{"base": null}`` before the integration has ever
    # pushed a URL — callers treat ``None`` as "nothing configured yet".
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/ha/integration/federation-base",
            status=200,
            payload={"base": None},
        )
        assert await client.federation.get_base() is None


async def test_federation_set_base_puts_and_parses_response(client: SocialHomeClient):
    with aioresponses() as m:
        m.put(
            "http://sh.test/api/ha/integration/federation-base",
            status=200,
            payload={
                "ok": True,
                "base": "https://external.example.org",
                "changed": True,
                "peers_notified": 3,
            },
        )
        result = await client.federation.set_base("https://external.example.org/")

        (call,) = m.requests[("PUT", _url("/api/ha/integration/federation-base"))]
        assert call.kwargs["json"] == {"base": "https://external.example.org/"}
        assert result == FederationBaseUpdate(
            ok=True,
            base="https://external.example.org",
            changed=True,
            peers_notified=3,
        )


# ── Helpers ───────────────────────────────────────────────────────────────


def _url(path: str) -> URL:
    """Canonical URL form used by aioresponses as request-dict keys."""
    return URL(f"http://sh.test{path}")
