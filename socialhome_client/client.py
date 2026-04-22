"""Async HTTP client for the Social Home REST API.

Spec §6.1. The library is intentionally thin: one method per endpoint
the HA integration needs, plus typed low-level helpers for anything
we haven't wrapped yet. All methods are ``async``, raise typed
exceptions, and return typed dataclasses from :mod:`.models`.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any, Self

import aiohttp

from .exceptions import SHAuthError, SHClientError, SHNotFoundError
from .models import (
    Calendar,
    CalendarEvent,
    Conversation,
    ShoppingItem,
    Space,
    UnreadSummary,
    User,
)

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S: float = 30.0


class SocialHomeClient:
    """Async HTTP client for a Social Home instance.

    One instance per config entry. Owns an :class:`aiohttp.ClientSession`
    lazily created on first request and closed via :meth:`close` (or the
    async context-manager protocol).

    The caller supplies a full ``base_url`` including scheme and port,
    e.g. ``"http://homeassistant.local:8099"``, and a bearer ``token``
    minted through ``/api/me/tokens`` or the initial login flow.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        # When the caller passes a session we do not own it — callers
        # are responsible for closing their own sessions. When we
        # create one on demand we mark it owned and close in
        # :meth:`close`.
        self._session = session
        self._owns_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)

    # ── Session lifecycle ─────────────────────────────────────────────────

    async def _session_once(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=self._timeout,
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close the underlying :class:`aiohttp.ClientSession` if we own it."""
        if self._session is not None and self._owns_session:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    # ── Low-level HTTP helpers ────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        session = await self._session_once()
        url = f"{self._base_url}{path}"
        try:
            async with session.request(method, url, params=params, json=json) as resp:
                status = resp.status
                if status == 204 or resp.content_length == 0:
                    body: Any = None
                else:
                    body = await resp.json(content_type=None)
                if status == 401:
                    raise SHAuthError()
                if status == 404:
                    raise SHNotFoundError(_error_message(body) or "not found")
                if status >= 400:
                    raise SHClientError(
                        _error_message(body) or f"{method} {path} → {status}",
                        status=status,
                    )
                return body
        except aiohttp.ClientError as exc:
            raise SHClientError(f"{method} {path} failed: {exc}") from exc

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """GET ``{base_url}{path}``. Returns parsed JSON."""
        return await self._request("GET", path, params=params)

    async def post(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        """POST ``{base_url}{path}`` with an optional JSON body."""
        return await self._request("POST", path, json=json)

    async def patch(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        """PATCH ``{base_url}{path}`` with an optional JSON body."""
        return await self._request("PATCH", path, json=json)

    async def delete(self, path: str) -> None:
        """DELETE ``{base_url}{path}``. Returns ``None`` on success."""
        await self._request("DELETE", path)

    # ── Auth ──────────────────────────────────────────────────────────────

    async def get_me(self) -> User:
        """GET ``/api/me`` — validate token + fetch current user.

        Used in the HA integration's config flow to confirm the
        entered URL + token before completing setup.
        """
        return User.from_api(await self.get("/api/me"))

    async def create_token(self, label: str, expires_in_days: int = 0) -> str:
        """POST ``/api/me/tokens`` — returns the raw token string.

        ``expires_in_days=0`` mints a non-expiring token.
        """
        body = await self.post(
            "/api/me/tokens",
            json={"label": label, "expires_in_days": expires_in_days},
        )
        return str(body["token"])

    # ── Presence ──────────────────────────────────────────────────────────

    async def post_location(
        self,
        username: str,
        latitude: float | None,
        longitude: float | None,
        accuracy_m: float | None,
        zone_name: str | None,
    ) -> None:
        """POST ``/api/presence/location``.

        Called by the HA integration from the ``person`` state-changed
        handler. Server-side truncates lat/lon to 4 decimal places.
        """
        await self.post(
            "/api/presence/location",
            json={
                "username": username,
                "latitude": latitude,
                "longitude": longitude,
                "accuracy_m": accuracy_m,
                "zone_name": zone_name,
            },
        )

    # ── Shopping list ────────────────────────────────────────────────────

    async def get_shopping_list(self) -> list[ShoppingItem]:
        body = await self.get("/api/shopping-list")
        return [ShoppingItem.from_api(row) for row in body.get("items", [])]

    async def add_shopping_item(self, name: str) -> ShoppingItem:
        body = await self.post("/api/shopping-list/items", json={"name": name})
        return ShoppingItem.from_api(body)

    async def update_shopping_item(
        self,
        item_id: str,
        *,
        name: str | None = None,
        checked: bool | None = None,
    ) -> ShoppingItem:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if checked is not None:
            payload["checked"] = checked
        body = await self.patch(f"/api/shopping-list/items/{item_id}", json=payload)
        return ShoppingItem.from_api(body)

    async def delete_shopping_item(self, item_id: str) -> None:
        await self.delete(f"/api/shopping-list/items/{item_id}")

    async def clear_shopping_list(self) -> None:
        await self.post("/api/shopping-list/clear")

    # ── Calendars ────────────────────────────────────────────────────────

    async def get_visible_calendars(self) -> list[Calendar]:
        body = await self.get("/api/calendars/visible")
        return [Calendar.from_api(row) for row in body.get("calendars", [])]

    async def get_calendar_events(
        self, calendar_id: str, start: str, end: str
    ) -> list[CalendarEvent]:
        body = await self.get(
            f"/api/calendars/{calendar_id}/events",
            params={"start": start, "end": end},
        )
        return [CalendarEvent.from_api(row) for row in body.get("events", [])]

    async def create_calendar_event(
        self,
        calendar_id: str,
        summary: str,
        start: str,
        end: str,
        all_day: bool = False,
        description: str | None = None,
    ) -> CalendarEvent:
        payload: dict[str, Any] = {
            "summary": summary,
            "start_at": start,
            "end_at": end,
            "all_day": all_day,
        }
        if description is not None:
            payload["description"] = description
        body = await self.post(f"/api/calendars/{calendar_id}/events", json=payload)
        return CalendarEvent.from_api(body)

    async def update_calendar_event(
        self,
        calendar_id: str,
        event_id: str,
        **changes: Any,
    ) -> CalendarEvent:
        body = await self.patch(
            f"/api/calendars/{calendar_id}/events/{event_id}",
            json=dict(changes),
        )
        return CalendarEvent.from_api(body)

    async def delete_calendar_event(self, calendar_id: str, event_id: str) -> None:
        await self.delete(f"/api/calendars/{calendar_id}/events/{event_id}")

    # ── Notify bridge ────────────────────────────────────────────────────

    async def notify_space(self, space_id: str, title: str | None, message: str) -> None:
        await self.post(
            f"/api/notify-bridge/spaces/{space_id}",
            json={"title": title, "message": message},
        )

    async def notify_conversation(
        self, conversation_id: str, title: str | None, message: str
    ) -> None:
        await self.post(
            f"/api/notify-bridge/conversations/{conversation_id}",
            json={"title": title, "message": message},
        )

    # ── Discovery (for notify service list) ──────────────────────────────

    async def get_spaces(self) -> list[Space]:
        body = await self.get("/api/spaces")
        return [Space.from_api(row) for row in body.get("spaces", [])]

    async def get_conversations(self) -> list[Conversation]:
        body = await self.get("/api/conversations")
        return [Conversation.from_api(row) for row in body.get("conversations", [])]

    # ── Sensor ───────────────────────────────────────────────────────────

    async def get_unread_summary(self) -> UnreadSummary:
        """GET ``/api/me/unread-summary``. Polled every 60 s by the coordinator."""
        return UnreadSummary.from_api(await self.get("/api/me/unread-summary"))

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def token(self) -> str:
        return self._token


def _error_message(body: Any) -> str | None:
    """Pull a human-readable message out of a standard error envelope.

    The HFS returns ``{"ok": false, "error": {"code": "...", "message": "..."}}``
    on domain errors; extract the message if present so upstream
    callers see a useful string instead of a stringified status code.
    """
    if not isinstance(body, dict):
        return None
    err = body.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str):
            return msg
    msg = body.get("message")
    return msg if isinstance(msg, str) else None
