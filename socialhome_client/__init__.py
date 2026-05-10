"""Async HTTP + WebSocket client for Social Home.

Public surface — the HA integration imports only these names:

- :class:`SocialHomeClient` — HTTP client (spec §6.1).
- :class:`SocialHomeWsManager` — reconnecting WebSocket (spec §6.2).
- Model dataclasses — :class:`User`, :class:`ShoppingItem`,
  :class:`Calendar`, :class:`CalendarEvent`, :class:`Space`,
  :class:`Conversation`, :class:`SpaceBot`, :class:`SpaceBotWithToken`,
  :class:`UnreadSummary` (spec §6.3).
- Exception hierarchy — :class:`SHClientError`, :class:`SHAuthError`,
  :class:`SHNotFoundError`.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .client import SocialHomeClient
from .exceptions import SHAuthError, SHClientError, SHNotFoundError
from .models import (
    Calendar,
    CalendarEvent,
    Conversation,
    FederationBaseUpdate,
    FederationRelayResult,
    IceServer,
    IceServersUpdate,
    ShoppingItem,
    Space,
    SpaceBot,
    SpaceBotWithToken,
    UnreadSummary,
    User,
)
from .ws_manager import SocialHomeWsManager

try:
    __version__ = version("socialhome-client")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "Calendar",
    "CalendarEvent",
    "Conversation",
    "FederationBaseUpdate",
    "FederationRelayResult",
    "IceServer",
    "IceServersUpdate",
    "SHAuthError",
    "SHClientError",
    "SHNotFoundError",
    "ShoppingItem",
    "SocialHomeClient",
    "SocialHomeWsManager",
    "Space",
    "SpaceBot",
    "SpaceBotWithToken",
    "UnreadSummary",
    "User",
    "__version__",
]
