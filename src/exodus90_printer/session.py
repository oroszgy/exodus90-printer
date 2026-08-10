"""Persistence of the HTTP cookie jar (the session)."""

from __future__ import annotations

import json
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from typing import Any

import httpx


def _cookie_to_dict(cookie: Cookie) -> dict[str, Any]:
    return {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path,
        "secure": cookie.secure,
        "expires": cookie.expires,
    }


def _dict_to_cookie(entry: dict[str, Any]) -> Cookie:
    return Cookie(
        version=0,
        name=str(entry["name"]),
        value=str(entry["value"]),
        port=None,
        port_specified=False,
        domain=str(entry["domain"]),
        domain_specified=True,
        domain_initial_dot=False,
        path=str(entry["path"]),
        path_specified=True,
        secure=bool(entry.get("secure", False)),
        expires=int(entry["expires"]) if entry.get("expires") is not None else None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


class CookieStore:
    """Loads and saves an :class:`httpx.Cookies` jar to a JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> httpx.Cookies:
        if not self.path.exists():
            return httpx.Cookies()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        jar = CookieJar()
        for entry in data:
            jar.set_cookie(_dict_to_cookie(entry))
        return httpx.Cookies(jar)

    def save(self, cookies: httpx.Cookies) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [_cookie_to_dict(c) for c in cookies.jar]
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
