"""Network printer discovery via DNS-SD (avahi / ``ippfind``)."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from urllib.parse import urlparse

from exodus90_printer.exceptions import ExodusError


@dataclass(frozen=True)
class DiscoveredPrinter:
    """A printer found via mDNS/DNS-SD advertising IPP support."""

    uri: str

    @property
    def host(self) -> str:
        netloc = urlparse(self.uri).netloc
        return netloc.split(":")[0]


def discover_printers() -> list[DiscoveredPrinter]:
    """Return IPP-capable network printers advertised on the LAN.

    Requires ``ippfind`` (ships with CUPS) and a running mDNS responder such as
    avahi-daemon. Raises :class:`ExodusError` when ``ippfind`` is unavailable.
    """
    ippfind = shutil.which("ippfind")
    if ippfind is None:
        raise ExodusError("`ippfind` not found (install CUPS). Printer discovery is unavailable.")
    try:
        result = subprocess.run([ippfind], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired as exc:
        raise ExodusError("Printer discovery timed out.") from exc
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [DiscoveredPrinter(line) for line in lines]


def _resolve_host(host: str) -> str | None:
    """Resolve an mDNS hostname (e.g. ``foo.local``) to an IP address."""
    resolver = shutil.which("avahi-resolve-host-name")
    if resolver is None:
        return None
    try:
        result = subprocess.run([resolver, host], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            return parts[1]
    return None


def discover_printer_uri() -> str | None:
    """Return a ready-to-use IPP URI (IP-based) for one discovered printer.

    Prefers ``avahi-browse`` parseable output (address + port + resource path,
    no ``.local`` resolution needed) and falls back to ``ippfind`` with
    ``avahi-resolve-host-name`` when the mDNS hostname must be resolved.
    """
    avahi = shutil.which("avahi-browse")
    if avahi is not None:
        uri = _discover_from_avahi(avahi)
        if uri is not None:
            return uri
    try:
        found = discover_printers()
    except ExodusError:
        return None
    for printer in found:
        host = printer.host
        uri = printer.uri
        if host.endswith(".local"):
            resolved = _resolve_host(host)
            if resolved:
                uri = uri.replace(host, resolved)
        return uri
    return None


def _discover_from_avahi(avahi: str) -> str | None:
    """Parse ``avahi-browse -prt _ipp._tcp`` and build an IP-based IPP URI."""
    try:
        result = subprocess.run(
            [avahi, "-prt", "_ipp._tcp"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return None
    records: list[tuple[str, str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split(";")
        if fields[0] != "=" or len(fields) < 10:
            continue
        address, port, txt = fields[7], fields[8], fields[9]
        if not address:
            continue
        rpc_match = re.search(r"rp=([^\s\"]+)", txt)
        rpc = rpc_match.group(1) if rpc_match else "ipp/print"
        records.append((address, port, rpc))
    if not records:
        return None
    ipv4 = next((r for r in records if "." in r[0] and ":" not in r[0]), None)
    address, port, rpc = ipv4 or records[0]
    return f"ipp://{address}:{port}/{rpc}"
