"""exodus90-printer: fetch and print daily readings from the Exodus 90 app."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("exodus90-printer")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
