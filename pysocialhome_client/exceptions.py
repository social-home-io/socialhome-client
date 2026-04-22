"""Typed exceptions raised by :class:`SocialHomeClient`.

All errors raised from the HTTP helpers descend from
:class:`SHClientError`, so integration code can catch the base and
handle specifics via ``isinstance`` — or re-raise directly.
"""

from __future__ import annotations


class SHClientError(Exception):
    """Base class for all client-raised errors.

    ``status`` is the HTTP status code when the failure originated
    from an HTTP response, or ``None`` for transport-level errors
    (DNS failure, connection reset, WebSocket handshake failure).
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class SHAuthError(SHClientError):
    """The server returned 401 Unauthorized.

    Raised on token rejection — either missing, malformed, or
    revoked. The HA integration maps this to ``ConfigEntryAuthFailed``
    to trigger the re-auth flow.
    """

    def __init__(self, message: str = "authentication failed") -> None:
        super().__init__(message, status=401)


class SHNotFoundError(SHClientError):
    """The server returned 404 Not Found."""

    def __init__(self, message: str = "not found") -> None:
        super().__init__(message, status=404)
