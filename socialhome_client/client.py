"""Async HTTP client for the Social Home REST API.

Spec §6.1. The library is intentionally thin: one method per endpoint
the HA integration needs, plus typed low-level helpers for anything
we haven't wrapped yet. All methods are ``async``, raise typed
exceptions, and return typed dataclasses from :mod:`.models`.

Feature-grouped surface: :class:`SocialHomeClient` exposes the HTTP
primitives (``get`` / ``post`` / ``patch`` / ``put`` / ``delete``) plus
a small set of resource attributes — ``c.me``, ``c.presence``,
``c.space``, ``c.conversation``, ``c.shopping``, ``c.calendar``,
``c.bot``, ``c.federation`` — each of which groups the typed wrappers
for one REST resource. Callers write ``c.shopping.add("milk")`` or
``c.bot.create(...)`` instead of carrying a flat list of methods on a
single object.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any, Literal, Self

import aiohttp

from .exceptions import SHAuthError, SHClientError, SHNotFoundError
from .models import (
    Calendar,
    CalendarEvent,
    Conversation,
    FederationBaseUpdate,
    FederationRelayResult,
    ShoppingItem,
    Space,
    SpaceBot,
    SpaceBotWithToken,
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

        # Resource sub-clients. Plain attribute access; each resource
        # keeps a back-reference to this client so the low-level
        # helpers (and their error mapping) stay centralised here.
        self.me = _MeResource(self)
        self.presence = _PresenceResource(self)
        self.space = _SpaceResource(self)
        self.conversation = _ConversationResource(self)
        self.shopping = _ShoppingResource(self)
        self.calendar = _CalendarResource(self)
        self.bot = _BotResource(self)
        self.federation = _FederationResource(self)

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
                return await _handle_response(resp, method, path)
        except aiohttp.ClientError as exc:
            raise SHClientError(f"{method} {path} failed: {exc}") from exc

    async def _request_with_bearer(
        self,
        method: str,
        path: str,
        bearer: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Make a one-shot request with an explicit Bearer token.

        Used for the bot-bridge space-post endpoint where the caller
        authenticates with a per-bot token (from
        :meth:`_BotResource.create`) that is *different* from this
        client's own ``self._token``. Reuses the owned session — the
        ``Authorization`` header is overridden for this single call, so
        the session's default header (set from ``self._token``) is not
        disturbed for other traffic.
        """
        session = await self._session_once()
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {bearer}"}
        try:
            async with session.request(method, url, json=json, headers=headers) as resp:
                return await _handle_response(resp, method, path)
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

    async def put(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        """PUT ``{base_url}{path}`` with an optional JSON body.

        Used for idempotent upserts — currently the HA integration's
        federation-base endpoint is the only caller.
        """
        return await self._request("PUT", path, json=json)

    async def delete(self, path: str) -> None:
        """DELETE ``{base_url}{path}``. Returns ``None`` on success."""
        await self._request("DELETE", path)

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def token(self) -> str:
        return self._token


# ──────────────────────────────────────────────────────────────────────────
# Resource sub-clients
#
# Each resource is a thin grouping of methods that share a URL prefix or
# feature area. They hold a back-reference to the owning
# :class:`SocialHomeClient` and use its HTTP helpers — so auth, error
# mapping, and session lifecycle stay in one place.
# ──────────────────────────────────────────────────────────────────────────


class _MeResource:
    """Identity + own-token + unread-summary reads."""

    __slots__ = ("_c",)

    def __init__(self, client: SocialHomeClient) -> None:
        self._c = client

    async def get(self) -> User:
        """GET ``/api/me`` — validate token + fetch current user.

        Used in the HA integration's config flow to confirm the
        entered URL + token before completing setup.
        """
        return User.from_api(await self._c.get("/api/me"))

    async def create_token(self, label: str, expires_in_days: int = 0) -> str:
        """POST ``/api/me/tokens`` — returns the raw token string.

        ``expires_in_days=0`` mints a non-expiring token.
        """
        body = await self._c.post(
            "/api/me/tokens",
            json={"label": label, "expires_in_days": expires_in_days},
        )
        return str(body["token"])

    async def unread_summary(self) -> UnreadSummary:
        """GET ``/api/me/unread-summary``. Polled every 60 s by the coordinator."""
        return UnreadSummary.from_api(await self._c.get("/api/me/unread-summary"))


class _PresenceResource:
    """Location + presence pushes."""

    __slots__ = ("_c",)

    def __init__(self, client: SocialHomeClient) -> None:
        self._c = client

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
        await self._c.post(
            "/api/presence/location",
            json={
                "username": username,
                "latitude": latitude,
                "longitude": longitude,
                "accuracy_m": accuracy_m,
                "zone_name": zone_name,
            },
        )


class _SpaceResource:
    """Space discovery + admin toggles.

    The HA integration only listens for / toggles a small slice of
    space state — most editing happens in the web UI. This resource
    stays narrow on purpose.
    """

    __slots__ = ("_c",)

    def __init__(self, client: SocialHomeClient) -> None:
        self._c = client

    async def list(self) -> list[Space]:
        """GET ``/api/spaces`` — spaces the caller is a member of."""
        body = await self._c.get("/api/spaces")
        return [Space.from_api(row) for row in body.get("spaces", [])]

    async def update(
        self,
        space_id: str,
        *,
        bot_enabled: bool | None = None,
    ) -> Space:
        """PATCH ``/api/spaces/{space_id}``.

        Only the fields the HA integration needs are wired. Admin
        endpoint; non-admins get a 403 from the backend.
        """
        payload: dict[str, Any] = {}
        if bot_enabled is not None:
            payload["bot_enabled"] = bool(bot_enabled)
        body = await self._c.patch(f"/api/spaces/{space_id}", json=payload)
        return Space.from_api(body)


class _ConversationResource:
    """Conversation discovery.

    The full DM read path lives in the HA integration; this resource
    only exposes what the notify-service discovery code needs.
    """

    __slots__ = ("_c",)

    def __init__(self, client: SocialHomeClient) -> None:
        self._c = client

    async def list(self) -> list[Conversation]:
        """GET ``/api/conversations``."""
        body = await self._c.get("/api/conversations")
        return [Conversation.from_api(row) for row in body.get("conversations", [])]


class _ShoppingResource:
    """Shopping-list CRUD."""

    __slots__ = ("_c",)

    def __init__(self, client: SocialHomeClient) -> None:
        self._c = client

    async def list(self) -> list[ShoppingItem]:
        body = await self._c.get("/api/shopping-list")
        return [ShoppingItem.from_api(row) for row in body.get("items", [])]

    async def add(self, name: str) -> ShoppingItem:
        body = await self._c.post("/api/shopping-list/items", json={"name": name})
        return ShoppingItem.from_api(body)

    async def update(
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
        body = await self._c.patch(f"/api/shopping-list/items/{item_id}", json=payload)
        return ShoppingItem.from_api(body)

    async def delete(self, item_id: str) -> None:
        await self._c.delete(f"/api/shopping-list/items/{item_id}")

    async def clear(self) -> None:
        await self._c.post("/api/shopping-list/clear")


class _CalendarResource:
    """Calendar discovery + event CRUD."""

    __slots__ = ("_c",)

    def __init__(self, client: SocialHomeClient) -> None:
        self._c = client

    async def list_visible(self) -> list[Calendar]:
        body = await self._c.get("/api/calendars/visible")
        return [Calendar.from_api(row) for row in body.get("calendars", [])]

    async def list_events(self, calendar_id: str, start: str, end: str) -> list[CalendarEvent]:
        body = await self._c.get(
            f"/api/calendars/{calendar_id}/events",
            params={"start": start, "end": end},
        )
        return [CalendarEvent.from_api(row) for row in body.get("events", [])]

    async def create_event(
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
        body = await self._c.post(f"/api/calendars/{calendar_id}/events", json=payload)
        return CalendarEvent.from_api(body)

    async def update_event(
        self,
        calendar_id: str,
        event_id: str,
        **changes: Any,
    ) -> CalendarEvent:
        body = await self._c.patch(
            f"/api/calendars/{calendar_id}/events/{event_id}",
            json=dict(changes),
        )
        return CalendarEvent.from_api(body)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        await self._c.delete(f"/api/calendars/{calendar_id}/events/{event_id}")


class _BotResource:
    """Bot-bridge: CRUD for space bots + the inbound post endpoints.

    Space-bot posts authenticate with a *per-bot* Bearer token returned
    from :meth:`create` (or :meth:`rotate_token`) — not the user's API
    token. This lets a leaked token be revoked by rotating just that
    bot without invalidating the user's whole session. Conversation
    posts still use the user token because DMs have no named bots.
    """

    __slots__ = ("_c",)

    def __init__(self, client: SocialHomeClient) -> None:
        self._c = client

    # ── CRUD (user API token) ────────────────────────────────────────────

    async def list(self, space_id: str) -> list[SpaceBot]:
        """GET ``/api/spaces/{space_id}/bots``."""
        body = await self._c.get(f"/api/spaces/{space_id}/bots")
        return [SpaceBot.from_api(row) for row in body]

    async def create(
        self,
        space_id: str,
        *,
        scope: Literal["space", "member"],
        slug: str,
        name: str,
        icon: str,
    ) -> SpaceBotWithToken:
        """POST ``/api/spaces/{space_id}/bots``.

        ``scope="space"`` requires the caller to be owner/admin of the
        space; ``scope="member"`` is available to any space member and
        produces posts rendered with per-member attribution.

        The returned :class:`SpaceBotWithToken.token` is the plaintext
        Bearer token. Persist it immediately — the backend stores only
        a sha256 hash and will not hand it over a second time.
        """
        body = await self._c.post(
            f"/api/spaces/{space_id}/bots",
            json={"scope": scope, "slug": slug, "name": name, "icon": icon},
        )
        return SpaceBotWithToken.from_api(body)

    async def update(
        self,
        space_id: str,
        bot_id: str,
        *,
        name: str | None = None,
        icon: str | None = None,
    ) -> SpaceBot:
        """PATCH ``/api/spaces/{space_id}/bots/{bot_id}``.

        Only ``name`` and ``icon`` are mutable — ``slug`` and ``scope``
        are immutable by design so HA automations targeting the bot
        don't silently break on rename.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if icon is not None:
            payload["icon"] = icon
        body = await self._c.patch(f"/api/spaces/{space_id}/bots/{bot_id}", json=payload)
        return SpaceBot.from_api(body)

    async def delete(self, space_id: str, bot_id: str) -> None:
        """DELETE ``/api/spaces/{space_id}/bots/{bot_id}``.

        Historical posts keep rendering as generic "Home Assistant"
        system posts — the server drops the bot_id on the post rows
        via ``ON DELETE SET NULL`` rather than cascading.
        """
        await self._c.delete(f"/api/spaces/{space_id}/bots/{bot_id}")

    async def rotate_token(self, space_id: str, bot_id: str) -> SpaceBotWithToken:
        """POST ``/api/spaces/{space_id}/bots/{bot_id}/token``.

        Invalidates the previous token and returns a fresh one — any
        HA automation using the old token will start getting 401s
        until reconfigured.
        """
        body = await self._c.post(f"/api/spaces/{space_id}/bots/{bot_id}/token")
        return SpaceBotWithToken.from_api(body)

    # ── Inbound posts (per-bot token for spaces, user token for DMs) ─────

    async def post(
        self,
        space_id: str,
        bot_token: str,
        *,
        title: str | None,
        message: str,
    ) -> None:
        """POST ``/api/bot-bridge/spaces/{space_id}``.

        Authenticates with ``bot_token`` (issued by :meth:`create` or
        :meth:`rotate_token`) — *not* this client's user token. One-
        shot request; does not mutate the session's default auth
        header, so subsequent calls via other resources continue using
        the user token as expected.
        """
        await self._c._request_with_bearer(
            "POST",
            f"/api/bot-bridge/spaces/{space_id}",
            bot_token,
            json={"title": title, "message": message},
        )

    async def post_conversation(
        self,
        conversation_id: str,
        *,
        title: str | None,
        message: str,
    ) -> None:
        """POST ``/api/bot-bridge/conversations/{conversation_id}``.

        Uses this client's user API token — DMs have no named bots, so
        the post surfaces as a system message from "Home Assistant".
        """
        await self._c.post(
            f"/api/bot-bridge/conversations/{conversation_id}",
            json={"title": title, "message": message},
        )


class _FederationResource:
    """Federation-layer glue used by the HA integration.

    Two responsibilities:

    1. **Outward URL advertisement** — push the HA-resolved external
       URL to the server so pairing QRs carry the right address and
       already-paired peers get ``URL_UPDATED`` on change.
    2. **Inbound envelope relay** — forward raw federation envelopes
       from the HA integration's public inbox endpoint into the
       server's internal ``/federation/inbox/{inbox_id}``. The server
       runs the full §24.11 validation pipeline; the relay is a pure
       HTTP passthrough — no body parsing, no error mapping.

    Spec §7.10 / §11.
    """

    __slots__ = ("_c",)

    def __init__(self, client: SocialHomeClient) -> None:
        self._c = client

    async def get_base(self) -> str | None:
        """GET ``/api/ha/integration/federation-base``.

        Returns the currently-configured base URL, or ``None`` if the
        integration has never pushed one. Used on re-bind to decide
        whether a push is necessary.
        """
        body = await self._c.get("/api/ha/integration/federation-base")
        raw = body.get("base")
        return str(raw) if raw else None

    async def set_base(self, base: str) -> FederationBaseUpdate:
        """PUT ``/api/ha/integration/federation-base`` with ``{"base": …}``.

        Idempotent — pushing an unchanged value is a cheap no-op on
        the server (no fan-out). When the value changes, the server
        notifies every confirmed peer with ``URL_UPDATED``; the
        returned :class:`FederationBaseUpdate` reports how many
        peers were notified.
        """
        body = await self._c.put("/api/ha/integration/federation-base", json={"base": base})
        return FederationBaseUpdate.from_api(body)

    async def forward_inbox_envelope(
        self,
        inbox_id: str,
        body: bytes,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> FederationRelayResult:
        """POST a raw federation envelope to ``/federation/inbox/{inbox_id}``.

        Used by the HA integration's public inbox endpoint to proxy
        envelopes coming in from remote instances. The server path
        is **unauthenticated** — the Ed25519 signature inside the
        envelope is the auth — but we reuse the client's session
        (and its bearer header) so a single :class:`aiohttp.ClientSession`
        serves every federation call.

        This method deliberately bypasses the usual JSON-parse +
        raise-on-non-2xx plumbing: the caller is an HTTP relay, so it
        needs the raw status, content type, and body bytes to mirror
        back to the remote peer unchanged.

        Raises :class:`SHClientError` only on transport-level
        failures (DNS, connection reset). Any HTTP status — 2xx,
        4xx, 5xx — comes back as :class:`FederationRelayResult`.
        """
        session = await self._c._session_once()
        url = f"{self._c.base_url}/federation/inbox/{inbox_id}"
        headers: dict[str, str] = {"Content-Type": "application/octet-stream"}
        if extra_headers:
            headers.update(extra_headers)
        try:
            async with session.post(url, data=body, headers=headers) as resp:
                payload = await resp.read()
                return FederationRelayResult(
                    status=resp.status,
                    body=payload,
                    content_type=resp.headers.get("Content-Type", "application/octet-stream"),
                )
        except aiohttp.ClientError as exc:
            raise SHClientError(f"POST /federation/inbox/{inbox_id} failed: {exc}") from exc


# ──────────────────────────────────────────────────────────────────────────
# Response + error plumbing — shared by _request and _request_with_bearer.
# ──────────────────────────────────────────────────────────────────────────


async def _handle_response(resp: aiohttp.ClientResponse, method: str, path: str) -> Any:
    """Common status → exception / JSON body handling.

    Centralised so ``_request`` and ``_request_with_bearer`` map
    errors identically — callers see the same exception hierarchy
    regardless of which auth path they took.
    """
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
