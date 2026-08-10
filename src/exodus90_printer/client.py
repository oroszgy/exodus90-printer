"""HTTP client with session handling and auth detection."""

from __future__ import annotations

from typing import Any

import httpx

from exodus90_printer.config import Settings
from exodus90_printer.exceptions import FetchError, SessionExpiredError
from exodus90_printer.session import CookieStore

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

LOGIN_PATH = "/auth/login"


class ExodusClient:
    """Wraps an :class:`httpx.Client` bound to a persisted cookie jar."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = CookieStore(settings.session_path)
        self.client = httpx.Client(
            base_url=settings.base_url,
            cookies=self.store.load(),
            follow_redirects=False,
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": USER_AGENT},
        )

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """GET ``path``, raising :class:`SessionExpiredError` if unauthenticated."""
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._request("POST", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise FetchError(f"Request to {self.settings.base_url}{path} failed: {exc}") from exc

        location = response.headers.get("location", "")
        if response.status_code in (301, 302, 303) and LOGIN_PATH in location:
            raise SessionExpiredError(
                "The Exodus 90 session has expired. Run `exodus90 login` to re-authenticate."
            )
        if response.status_code >= 400:
            raise FetchError(
                f"Request to {self.settings.base_url}{path} returned HTTP {response.status_code}"
            )
        return response

    def is_authenticated(self) -> bool:
        try:
            self.get("/today")
        except SessionExpiredError:
            return False
        return True

    def save_session(self) -> None:
        self.store.save(self.client.cookies)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> ExodusClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
