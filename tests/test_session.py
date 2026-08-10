"""Tests for cookie-jar persistence."""

from __future__ import annotations

from pathlib import Path

import httpx

from exodus90_printer.session import CookieStore


def _cookies() -> httpx.Cookies:
    cookies = httpx.Cookies()
    cookies.set("_backend_session", "abc123", domain="app.exodus90.com", path="/")
    cookies.set("user_id", "xyz", domain="app.exodus90.com", path="/")
    return cookies


def test_cookie_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "cookies.json"
    store = CookieStore(path)
    store.save(_cookies())
    assert path.exists()

    loaded = store.load()
    assert loaded.get("_backend_session") == "abc123"
    assert loaded.get("user_id") == "xyz"
    assert loaded.get("missing") is None


def test_cookie_store_missing_file(tmp_path: Path) -> None:
    store = CookieStore(tmp_path / "does-not-exist.json")
    assert len(store.load().jar) == 0
