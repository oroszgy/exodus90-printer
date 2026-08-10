"""Rendering helpers."""

from __future__ import annotations

import re
import unicodedata

from exodus90_printer.models import Reading


def slugify(text: str) -> str:
    """ASCII slug of a title, safe for use in file names."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or "reading"


def output_stem(reading: Reading) -> str:
    return f"{reading.day.date.isoformat()}-{slugify(reading.day.title)}"
