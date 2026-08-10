"""Data models describing program days and readings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Day:
    """One day of a program, as listed on the program page."""

    day_id: str
    """DOM/URL id of the day, e.g. ``program_day_3321``."""

    date: date
    """The date the reading belongs to."""

    title: str
    """Short title of the day's reading."""

    scripture: str | None
    """Scripture reference (e.g. ``Kiv 14,10-20``), if the day has one."""


@dataclass(frozen=True)
class Reading:
    """A full reading: day metadata plus the markdown body."""

    day: Day
    program_id: int
    body: str
    """The reading body as served by the app (markdown)."""
