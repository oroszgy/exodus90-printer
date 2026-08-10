"""Shared exceptions for the exodus90-printer package."""

from __future__ import annotations


class ExodusError(Exception):
    """Base error for everything this package raises."""


class SessionExpiredError(ExodusError):
    """The persisted session is no longer valid; the user must log in again."""


class AuthError(ExodusError):
    """Something went wrong during login / OTP verification."""


class NoReadingForDateError(ExodusError):
    """The configured program has no reading for the requested date."""


class FetchError(ExodusError):
    """An HTTP request to the Exodus 90 app failed."""
