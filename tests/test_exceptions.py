"""Tests for :mod:`pysocialhome_client.exceptions`."""

from __future__ import annotations

from pysocialhome_client import SHAuthError, SHClientError, SHNotFoundError


def test_sh_client_error_carries_status():
    exc = SHClientError("boom", status=500)
    assert str(exc) == "boom"
    assert exc.status == 500


def test_sh_client_error_status_optional():
    exc = SHClientError("transport failure")
    assert exc.status is None


def test_auth_error_defaults_status_to_401():
    exc = SHAuthError()
    assert exc.status == 401
    assert isinstance(exc, SHClientError)


def test_not_found_defaults_status_to_404():
    exc = SHNotFoundError()
    assert exc.status == 404
    assert isinstance(exc, SHClientError)


def test_not_found_accepts_custom_message():
    exc = SHNotFoundError("no such calendar")
    assert str(exc) == "no such calendar"
