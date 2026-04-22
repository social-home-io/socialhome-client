"""Tests for :mod:`socialhome_client.client`.

Each HTTP method is stubbed with :mod:`aioresponses`; we never touch
the network.
"""

from __future__ import annotations

import aiohttp
import pytest
from aioresponses import aioresponses

from socialhome_client import (
    Calendar,
    CalendarEvent,
    Conversation,
    SHAuthError,
    SHClientError,
    SHNotFoundError,
    ShoppingItem,
    SocialHomeClient,
    Space,
    UnreadSummary,
    User,
)


async def test_context_manager_closes_owned_session():
    async with SocialHomeClient("http://sh.test", token="t") as c:
        # Force the lazy session to exist so we can assert close.
        await c._session_once()
        assert c._session is not None
    assert c._session is None


async def test_external_session_not_closed_by_client():
    async with aiohttp.ClientSession() as sess:
        c = SocialHomeClient("http://sh.test", token="t", session=sess)
        await c.close()
        # External session is untouched.
        assert not sess.closed


async def test_get_me_parses_response(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/me",
            payload={"user_id": "u1", "username": "alice", "display_name": "Alice"},
        )
        user = await client.get_me()
    assert isinstance(user, User)
    assert user.username == "alice"


async def test_401_raises_auth_error(client: SocialHomeClient):
    with aioresponses() as m:
        m.get("http://sh.test/api/me", status=401)
        with pytest.raises(SHAuthError):
            await client.get_me()


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
            await client.get_me()
    assert exc_info.value.status == 500


async def test_transport_error_wrapped(client: SocialHomeClient):
    with aioresponses() as m:
        m.get("http://sh.test/api/me", exception=aiohttp.ClientError("connection reset"))
        with pytest.raises(SHClientError) as exc_info:
            await client.get_me()
    # Transport-level errors have status=None.
    assert exc_info.value.status is None


async def test_create_token_returns_raw_string(client: SocialHomeClient):
    with aioresponses() as m:
        m.post("http://sh.test/api/me/tokens", payload={"token": "deadbeef"})
        token = await client.create_token("ha-integration")
    assert token == "deadbeef"


async def test_post_location_sends_payload(client: SocialHomeClient):
    with aioresponses() as m:
        m.post("http://sh.test/api/presence/location", status=204)
        await client.post_location(
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


async def test_shopping_list_crud(client: SocialHomeClient):
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

        items = await client.get_shopping_list()
        assert len(items) == 1
        assert items[0].name == "milk"

        added = await client.add_shopping_item("bread")
        assert isinstance(added, ShoppingItem)

        updated = await client.update_shopping_item("i2", checked=True)
        assert updated.checked is True

        await client.delete_shopping_item("i2")
        await client.clear_shopping_list()


async def test_update_shopping_item_only_sends_non_none(client: SocialHomeClient):
    with aioresponses() as m:
        m.patch(
            "http://sh.test/api/shopping-list/items/i1",
            payload={"id": "i1", "name": "eggs", "checked": False, "order": 0},
        )
        await client.update_shopping_item("i1", name="eggs")
        (call,) = m.requests[("PATCH", _url("/api/shopping-list/items/i1"))]
        assert call.kwargs["json"] == {"name": "eggs"}


async def test_calendars(client: SocialHomeClient):
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
        cals = await client.get_visible_calendars()
        assert isinstance(cals[0], Calendar)

        events = await client.get_calendar_events("c1", "S", "E")
        assert isinstance(events[0], CalendarEvent)
        assert events[0].summary == "Dentist"


async def test_create_calendar_event_omits_description_when_none(
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
        await client.create_calendar_event("c1", "Meeting", start="S", end="E")
        (call,) = m.requests[("POST", _url("/api/calendars/c1/events"))]
        assert "description" not in call.kwargs["json"]


async def test_update_calendar_event_passthrough_kwargs(client: SocialHomeClient):
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
        ev = await client.update_calendar_event(
            "c1", "e1", summary="Moved", start_at="S2", end_at="E2"
        )
        assert ev.summary == "Moved"


async def test_notify_space_and_conversation(client: SocialHomeClient):
    with aioresponses() as m:
        m.post("http://sh.test/api/notify-bridge/spaces/s1", status=204)
        m.post("http://sh.test/api/notify-bridge/conversations/c1", status=204)
        await client.notify_space("s1", title="hi", message="there")
        await client.notify_conversation("c1", title=None, message="pong")


async def test_discovery_endpoints(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/spaces",
            payload={"spaces": [{"id": "s1", "name": "Family"}]},
        )
        m.get(
            "http://sh.test/api/conversations",
            payload={"conversations": [{"id": "c1", "display_name": "Bob"}]},
        )
        spaces = await client.get_spaces()
        conversations = await client.get_conversations()
    assert spaces == [Space(id="s1", name="Family")]
    assert conversations == [Conversation(id="c1", display_name="Bob", type="dm")]


async def test_unread_summary(client: SocialHomeClient):
    with aioresponses() as m:
        m.get(
            "http://sh.test/api/me/unread-summary",
            payload={"total": 4, "feed": 1, "dms": 2, "spaces": {"s1": 1}},
        )
        summary = await client.get_unread_summary()
    assert isinstance(summary, UnreadSummary)
    assert summary.total == 4
    assert summary.spaces == {"s1": 1}


async def test_base_url_strips_trailing_slash():
    c = SocialHomeClient("http://sh.test/", token="t")
    assert c.base_url == "http://sh.test"
    await c.close()


def _url(path: str) -> str:
    # aioresponses keys requests by yarl.URL; we need the same
    # canonical form. Local helper so the asserts stay readable.
    from yarl import URL

    return URL(f"http://sh.test{path}")
