"""Reconnecting WebSocket subscription manager.

Spec §6.2. Optional realtime channel for consumers that want
sub-poll-interval updates (shopping-list edits, calendar changes,
unread-count changes). The HA integration v1 sticks to the REST
coordinator and does not instantiate this — a future version may.

Design:

* One manager per :class:`SocialHomeClient`.
* Callers register handlers with :meth:`register`, keyed by event
  type (JSON ``type`` field). Unknown event types are dropped.
* The connection is kept alive by a background receive loop.
  Reconnect uses an exponential backoff (5 s → 15 s → 30 s → 60 s
  cap) until :meth:`disconnect` is called.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from .client import SocialHomeClient

log = logging.getLogger(__name__)

#: Path on the HFS where the WebSocket lives. Authenticated via the
#: bearer token — passed as a query parameter because browsers can't
#: set Authorization headers on WS upgrade requests. On this client we
#: use the query-param form too so the auth mechanism matches the
#: route's canonical form.
_WS_PATH: str = "/api/ws"

#: Reconnect backoff schedule in seconds. Capped at the final value.
_BACKOFF_SCHEDULE_S: tuple[float, ...] = (5.0, 15.0, 30.0, 60.0)

#: Heartbeat interval sent to keep the connection alive through NAT
#: and proxy idle timeouts.
_HEARTBEAT_S: float = 30.0

#: Maximum duration we wait for the initial open before considering
#: the connect attempt failed and applying backoff.
_CONNECT_TIMEOUT_S: float = 15.0

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class SocialHomeWsManager:
    """Long-lived reconnecting WebSocket for one :class:`SocialHomeClient`."""

    def __init__(self, client: SocialHomeClient) -> None:
        self._client = client
        self._handlers: dict[str, list[EventHandler]] = {}
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._connected = asyncio.Event()

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Start the background receive loop.

        Returns after the first successful connection + auth handshake
        completes, so the caller can start dispatching work that
        assumes the socket is live. Subsequent reconnects happen in
        the background.
        """
        if self._task is not None:
            return
        self._stop.clear()
        self._connected.clear()
        self._task = asyncio.create_task(self._run(), name="sh-ws-manager")
        # Wait for first successful connection (or failure / stop).
        first_connect = asyncio.create_task(self._connected.wait())
        stopped = asyncio.create_task(self._stop.wait())
        _done, pending = await asyncio.wait(
            {first_connect, stopped},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for p in pending:
            p.cancel()

    async def disconnect(self) -> None:
        """Close the connection and stop reconnecting."""
        self._stop.set()
        if self._ws is not None and not self._ws.closed:
            with contextlib.suppress(Exception):
                await self._ws.close()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    # ── Registration ────────────────────────────────────────────────────

    def register(
        self,
        event_types: list[str],
        callback: EventHandler,
    ) -> Callable[[], None]:
        """Subscribe ``callback`` to ``event_types``.

        Returns a zero-arg callable that unsubscribes. Call it from
        ``async_on_unload`` in the HA platform that registered.
        """
        for etype in event_types:
            self._handlers.setdefault(etype, []).append(callback)

        def _unsubscribe() -> None:
            for etype in event_types:
                callbacks = self._handlers.get(etype)
                if callbacks is None:
                    continue
                with contextlib.suppress(ValueError):
                    callbacks.remove(callback)
                if not callbacks:
                    self._handlers.pop(etype, None)

        return _unsubscribe

    # ── Internal loop ────────────────────────────────────────────────────

    def _ws_url(self) -> str:
        scheme = "wss" if self._client.base_url.startswith("https") else "ws"
        host = self._client.base_url.split("://", 1)[1]
        return f"{scheme}://{host}{_WS_PATH}?token={self._client.token}"

    async def _run(self) -> None:
        backoff_idx = 0
        while not self._stop.is_set():
            try:
                await self._connect_once()
                backoff_idx = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Social Home WS connection failed: %s", exc)
            if self._stop.is_set():
                break
            delay = _BACKOFF_SCHEDULE_S[min(backoff_idx, len(_BACKOFF_SCHEDULE_S) - 1)]
            backoff_idx += 1
            log.info("Social Home WS reconnect in %.0fs", delay)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=delay)

    async def _connect_once(self) -> None:
        session = await self._client._session_once()
        ws_ctx = session.ws_connect(
            self._ws_url(),
            heartbeat=_HEARTBEAT_S,
            timeout=aiohttp.ClientWSTimeout(ws_close=_CONNECT_TIMEOUT_S),
        )
        async with ws_ctx as ws:
            self._ws = ws
            self._connected.set()
            log.info("Social Home WS connected")
            try:
                await self._receive_loop(ws)
            finally:
                self._ws = None
                log.info("Social Home WS disconnected")

    async def _receive_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if self._stop.is_set():
                break
            if msg.type is aiohttp.WSMsgType.TEXT:
                await self._dispatch(msg.data)
            elif msg.type is aiohttp.WSMsgType.ERROR:
                log.warning("Social Home WS error: %s", ws.exception())
                break

    async def _dispatch(self, raw: str) -> None:
        if raw == "pong":
            return
        try:
            frame = _parse_json(raw)
        except ValueError as exc:
            log.debug("Dropping malformed WS frame: %s", exc)
            return
        etype = frame.get("type")
        if not isinstance(etype, str):
            return
        handlers = self._handlers.get(etype)
        if not handlers:
            return
        for cb in list(handlers):
            try:
                await cb(frame)
            except Exception:
                log.exception("WS handler for %r raised", etype)


def _parse_json(raw: str) -> dict[str, Any]:
    """Parse a WS text frame as a JSON object.

    Raises :class:`ValueError` for non-object JSON or malformed input
    — callers log at debug and continue.
    """
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object, got {type(data).__name__}")
    return data
