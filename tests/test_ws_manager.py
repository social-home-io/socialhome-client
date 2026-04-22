"""Tests for :mod:`pysocialhome_client.ws_manager`.

We fake :class:`aiohttp.ClientWebSocketResponse` with an in-memory
queue. That keeps the tests deterministic and free of network I/O
while still exercising the reconnect loop, backoff schedule, and
handler-dispatch logic.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any
from unittest.mock import patch

import aiohttp
import pytest

from pysocialhome_client import SocialHomeClient, SocialHomeWsManager
from pysocialhome_client import ws_manager as ws_mod


class _FakeWSMsg:
    def __init__(self, msg_type: aiohttp.WSMsgType, data: Any = None) -> None:
        self.type = msg_type
        self.data = data


class _FakeWS:
    """Stand-in for :class:`aiohttp.ClientWebSocketResponse`.

    Yields a pre-scripted sequence of ``(type, data)`` pairs, then
    blocks until :meth:`close` is called so the receive loop exits
    naturally.
    """

    def __init__(self, frames: Iterable[_FakeWSMsg]) -> None:
        self._frames = list(frames)
        self._cursor = 0
        self._closed = asyncio.Event()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def exception(self) -> BaseException | None:
        return None

    def __aiter__(self) -> _FakeWS:
        return self

    async def __anext__(self) -> _FakeWSMsg:
        if self._cursor < len(self._frames):
            msg = self._frames[self._cursor]
            self._cursor += 1
            return msg
        # After the scripted frames are drained, park until closed.
        await self._closed.wait()
        raise StopAsyncIteration

    async def close(self) -> None:
        self._closed.set()


class _FakeWSContext:
    def __init__(self, ws: _FakeWS) -> None:
        self._ws = ws

    async def __aenter__(self) -> _FakeWS:
        return self._ws

    async def __aexit__(self, *_: Any) -> None:
        await self._ws.close()


def _text(data: dict[str, Any]) -> _FakeWSMsg:
    return _FakeWSMsg(aiohttp.WSMsgType.TEXT, json.dumps(data))


async def test_register_dispatches_to_handlers():
    client = SocialHomeClient("http://sh.test", token="t")
    mgr = SocialHomeWsManager(client)
    fake_ws = _FakeWS([_text({"type": "post_created", "id": "p1"})])
    received: list[dict[str, Any]] = []

    async def on_post(frame: dict[str, Any]) -> None:
        received.append(frame)

    mgr.register(["post_created"], on_post)

    with patch.object(aiohttp.ClientSession, "ws_connect", return_value=_FakeWSContext(fake_ws)):
        await mgr.connect()
        # Give the receive loop a tick to drain the frame.
        for _ in range(10):
            if received:
                break
            await asyncio.sleep(0.01)
        await mgr.disconnect()

    assert received == [{"type": "post_created", "id": "p1"}]
    await client.close()


async def test_unregister_removes_handler():
    client = SocialHomeClient("http://sh.test", token="t")
    mgr = SocialHomeWsManager(client)
    calls: list[dict[str, Any]] = []

    async def cb(frame: dict[str, Any]) -> None:
        calls.append(frame)

    unsubscribe = mgr.register(["x"], cb)
    assert "x" in mgr._handlers
    unsubscribe()
    assert "x" not in mgr._handlers
    await client.close()


async def test_malformed_json_dropped_silently():
    client = SocialHomeClient("http://sh.test", token="t")
    mgr = SocialHomeWsManager(client)
    fake_ws = _FakeWS(
        [
            _FakeWSMsg(aiohttp.WSMsgType.TEXT, "not json"),
            _FakeWSMsg(aiohttp.WSMsgType.TEXT, "42"),  # valid JSON but not an object
            _text({"type": "good", "n": 1}),
        ]
    )
    received: list[dict[str, Any]] = []

    async def on_good(frame: dict[str, Any]) -> None:
        received.append(frame)

    mgr.register(["good"], on_good)

    with patch.object(aiohttp.ClientSession, "ws_connect", return_value=_FakeWSContext(fake_ws)):
        await mgr.connect()
        for _ in range(20):
            if received:
                break
            await asyncio.sleep(0.01)
        await mgr.disconnect()

    assert len(received) == 1
    await client.close()


async def test_pong_frames_are_ignored():
    client = SocialHomeClient("http://sh.test", token="t")
    mgr = SocialHomeWsManager(client)
    fake_ws = _FakeWS([_FakeWSMsg(aiohttp.WSMsgType.TEXT, "pong")])

    async def cb(_: dict[str, Any]) -> None:
        pytest.fail("pong should not dispatch")

    mgr.register(["pong"], cb)

    with patch.object(aiohttp.ClientSession, "ws_connect", return_value=_FakeWSContext(fake_ws)):
        await mgr.connect()
        await asyncio.sleep(0.05)
        await mgr.disconnect()
    await client.close()


async def test_reconnect_after_failure(monkeypatch: pytest.MonkeyPatch):
    """First connect attempt fails; manager applies backoff, second succeeds."""
    # Shrink the schedule so the test finishes in milliseconds. The
    # module-level tuple is consulted on each loop iteration.
    monkeypatch.setattr(ws_mod, "_BACKOFF_SCHEDULE_S", (0.01, 0.01, 0.01, 0.01))

    client = SocialHomeClient("http://sh.test", token="t")
    mgr = SocialHomeWsManager(client)

    fake_ws = _FakeWS([_text({"type": "hello"})])
    attempts = {"n": 0}

    class _FailingCtx:
        async def __aenter__(self) -> Any:
            raise aiohttp.ClientError("refused")

        async def __aexit__(self, *exc: Any) -> None:
            return None

    def _ws_connect(self: Any, *a: Any, **kw: Any) -> Any:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return _FailingCtx()
        return _FakeWSContext(fake_ws)

    got_hello = asyncio.Event()

    async def cb(_: dict[str, Any]) -> None:
        got_hello.set()

    mgr.register(["hello"], cb)

    with patch.object(aiohttp.ClientSession, "ws_connect", new=_ws_connect):
        await mgr.connect()
        try:
            await asyncio.wait_for(got_hello.wait(), timeout=1.0)
        finally:
            await mgr.disconnect()

    assert attempts["n"] >= 2
    await client.close()


async def test_disconnect_idempotent_before_connect():
    client = SocialHomeClient("http://sh.test", token="t")
    mgr = SocialHomeWsManager(client)
    # Should be a no-op; must not raise.
    await mgr.disconnect()
    await client.close()


async def test_connect_noop_when_already_running():
    client = SocialHomeClient("http://sh.test", token="t")
    mgr = SocialHomeWsManager(client)
    fake_ws = _FakeWS([])

    calls = {"n": 0}

    def _ws_connect(self: Any, *a: Any, **kw: Any) -> Any:
        calls["n"] += 1
        return _FakeWSContext(fake_ws)

    with patch.object(aiohttp.ClientSession, "ws_connect", new=_ws_connect):
        await mgr.connect()
        first = calls["n"]
        # Second call returns immediately without spawning a new task.
        await mgr.connect()
        assert calls["n"] == first
        await mgr.disconnect()

    await client.close()
