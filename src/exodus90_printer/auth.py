"""Passwordless OTP login flow for the Exodus 90 app."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from exodus90_printer.client import ExodusClient
from exodus90_printer.exceptions import AuthError, SessionExpiredError

_LOGIN_TEXT_FIELDS = ("email", "phone", "phone_formatted")
_CODE_INPUT_TYPES = ("text", "tel", "email", "number", "password")


@dataclass(frozen=True)
class CodeForm:
    """The OTP entry form returned after submitting the email address."""

    action: str
    fields: dict[str, str]
    code_field: str


def _parse_form(form: Tag) -> tuple[str, dict[str, str], list[str]]:
    hidden: dict[str, str] = {}
    text_fields: list[str] = []
    for inp in form.find_all("input", attrs={"name": True}):
        name = str(inp["name"])
        itype = str(inp.get("type") or "text").lower()
        if itype == "hidden":
            hidden[name] = str(inp.get("value", ""))
        elif itype in _CODE_INPUT_TYPES and name not in text_fields:
            text_fields.append(name)
    return str(form.get("action") or ""), hidden, text_fields


def _find_login_form(page: str) -> tuple[str, dict[str, str]]:
    soup = BeautifulSoup(page, "lxml")
    for form in soup.find_all("form"):
        action, hidden, text_fields = _parse_form(form)
        if "email" in text_fields:
            return action, hidden
    raise AuthError("Could not find the login form. The app layout may have changed.")


def _find_code_form(page: str) -> CodeForm:
    soup = BeautifulSoup(page, "lxml")
    for form in soup.find_all("form"):
        action, hidden, text_fields = _parse_form(form)
        code_fields = [field for field in text_fields if field not in _LOGIN_TEXT_FIELDS]
        if code_fields:
            return CodeForm(action=action, fields=hidden, code_field=code_fields[0])
    raise AuthError("Could not find the verification code form. The app layout may have changed.")


def request_otp(client: ExodusClient, email: str) -> CodeForm:
    """Submit the email address and return the OTP entry form."""
    page = client.get("/auth/login")
    action, hidden = _find_login_form(page.text)
    data = dict(hidden)
    data["email"] = email
    data["mode"] = "email"
    data.pop("phone", None)
    data.pop("phone_formatted", None)
    try:
        response = client.post(action, data=data)
        if response.status_code in (301, 302, 303) and response.headers.get("location"):
            response = client.get(response.headers["location"])
    except SessionExpiredError as exc:
        raise AuthError("Could not complete login. Check the email address and try again.") from exc
    return _find_code_form(response.text)


def verify_otp(client: ExodusClient, code_form: CodeForm, code: str) -> None:
    """Submit the 6-digit code and persist the resulting session."""
    digits = re.sub(r"\D", "", code)
    if len(digits) != 6:
        raise AuthError("The verification code must be 6 digits.")
    data = dict(code_form.fields)
    data[code_form.code_field] = f"{digits[:3]}-{digits[3:]}"
    try:
        client.post(code_form.action, data=data)
    except SessionExpiredError as exc:
        raise AuthError("Verification failed. Check the code and try again.") from exc
    if not client.is_authenticated():
        raise AuthError("Verification failed. Check the code and try again.")
