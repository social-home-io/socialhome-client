"""Shared test fixtures for pysocialhome-client."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from pysocialhome_client import SocialHomeClient


@pytest.fixture
async def client() -> AsyncIterator[SocialHomeClient]:
    """A client bound to a dummy base URL + token.

    HTTP calls are expected to be intercepted by ``aioresponses``.
    """
    c = SocialHomeClient("http://sh.test", token="tok")
    try:
        yield c
    finally:
        await c.close()
