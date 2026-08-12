"""Tests for network printer discovery."""

from __future__ import annotations

from typing import Any

import pytest

from exodus90_printer.discovery import DiscoveredPrinter, discover_printer_uri, discover_printers
from exodus90_printer.exceptions import ExodusError

AVAHI_OUT = (
    "+;eth0;IPv4;Printer;Internet Printer;local\n"
    '=;eth0;IPv4;Printer;Internet Printer;local;HOST.local;192.168.1.50;631;"rp=ipp/print"\n'
)


class _Result:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def _which(programs: dict[str, str | None]) -> Any:
    def which(name: str) -> str | None:
        return programs.get(name)

    return which


def test_discover_printers_parses_ippfind_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", _which({"ippfind": "/usr/bin/ippfind"}))
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_args, **_kwargs: _Result(
            "ipp://Brother.local:631/ipp/print\nipp://192.168.1.50/ipp/print\n"
        ),
    )
    found = discover_printers()
    assert found == [
        DiscoveredPrinter("ipp://Brother.local:631/ipp/print"),
        DiscoveredPrinter("ipp://192.168.1.50/ipp/print"),
    ]
    assert found[0].host == "Brother.local"


def test_discover_printers_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", _which({"ippfind": "/usr/bin/ippfind"}))
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: _Result("", 1))
    assert discover_printers() == []


def test_discover_printers_missing_ippfind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", _which({}))
    with pytest.raises(ExodusError, match="ippfind"):
        discover_printers()


def test_discover_printer_uri_via_avahi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", _which({"avahi-browse": "/usr/bin/avahi-browse"}))
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: _Result(AVAHI_OUT))
    assert discover_printer_uri() == "ipp://192.168.1.50:631/ipp/print"


def test_discover_printer_uri_prefers_ipv4(monkeypatch: pytest.MonkeyPatch) -> None:
    out = (
        '=;eth0;IPv6;Printer;Internet Printer;local;HOST.local;fe80::1;631;"rp=ipp/print"\n'
        '=;eth0;IPv4;Printer;Internet Printer;local;HOST.local;192.168.1.50;631;"rp=ipp/print"\n'
    )
    monkeypatch.setattr("shutil.which", _which({"avahi-browse": "/usr/bin/avahi-browse"}))
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: _Result(out))
    assert discover_printer_uri() == "ipp://192.168.1.50:631/ipp/print"


def test_discover_printer_uri_avahi_defaults_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    out = '=;eth0;IPv4;Printer;Internet Printer;local;HOST.local;192.168.1.50;631;""\n'
    monkeypatch.setattr("shutil.which", _which({"avahi-browse": "/usr/bin/avahi-browse"}))
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: _Result(out))
    assert discover_printer_uri() == "ipp://192.168.1.50:631/ipp/print"


def test_discover_printer_uri_fallback_resolves_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_run(command: list[str], **_kwargs: Any) -> _Result:
        calls.append(command[0])
        if command[0].endswith("ippfind"):
            return _Result("ipp://HOST.local:631/ipp/print\n")
        if command[0].endswith("avahi-resolve-host-name"):
            return _Result("HOST.local 192.168.1.246\n")
        return _Result(AVAHI_OUT)

    monkeypatch.setattr(
        "shutil.which",
        _which(
            {
                "avahi-browse": None,
                "ippfind": "/usr/bin/ippfind",
                "avahi-resolve-host-name": "/usr/bin/avahi-resolve-host-name",
            }
        ),
    )
    monkeypatch.setattr("subprocess.run", fake_run)
    assert discover_printer_uri() == "ipp://192.168.1.246:631/ipp/print"
    assert "ippfind" in calls[0] or calls[0].endswith("ippfind")


def test_discover_printer_uri_none_when_no_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", _which({"avahi-browse": "/usr/bin/avahi-browse"}))
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: _Result("+\n"))
    assert discover_printer_uri() is None
