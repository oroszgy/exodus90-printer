"""Tests for the scraper using real saved pages as fixtures."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from exodus90_printer.exceptions import NoReadingForDateError
from exodus90_printer.models import Day
from exodus90_printer.scraper import (
    fetch_days,
    fetch_reading,
    fetch_reading_for_date,
    find_day,
)

FIXTURES = Path(__file__).parent / "fixtures"


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def get(self, path: str, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(self.pages[path])


@pytest.fixture()
def program_client() -> _FakeClient:
    return _FakeClient(
        {
            "/programs/208": (FIXTURES / "program_page.html").read_text(),
            "/readings/program_day_3320": (FIXTURES / "reading_page.html").read_text(),
        }
    )


def test_fetch_days_maps_date_to_day(program_client: _FakeClient) -> None:
    days = fetch_days(program_client, 208)  # type: ignore[arg-type]
    by_date = {d.date: d for d in days}
    assert by_date[date(2026, 8, 1)].day_id == "program_day_3320"
    assert by_date[date(2026, 8, 1)].title == "Isten harcol érted"
    assert by_date[date(2026, 8, 1)].scripture == "Kiv 14,10-20"
    assert by_date[date(2026, 8, 10)].day_id == "program_day_3321"
    assert by_date[date(2026, 8, 10)].title == "Ragaszkodj ahhoz, amit kaptál"


def test_fetch_days_returns_all_days(program_client: _FakeClient) -> None:
    days = fetch_days(program_client, 208)  # type: ignore[arg-type]
    assert len(days) == 11


def test_fetch_days_rejects_date(program_client: _FakeClient) -> None:
    days = fetch_days(program_client, 208)  # type: ignore[arg-type]
    with pytest.raises(NoReadingForDateError):
        find_day(days, date(2026, 1, 1))


def test_fetch_reading_extracts_markdown(program_client: _FakeClient) -> None:
    days = fetch_days(program_client, 208)  # type: ignore[arg-type]
    day = find_day(days, date(2026, 8, 1))
    reading = fetch_reading(program_client, day, 208)  # type: ignore[arg-type]
    assert reading.day == day
    assert reading.program_id == 208
    assert reading.body.startswith("# Üdvözlünk az Exodus 90-ben")


def test_fetch_reading_for_date(program_client: _FakeClient) -> None:
    reading = fetch_reading_for_date(program_client, 208, date(2026, 8, 1))  # type: ignore[arg-type]
    assert isinstance(reading.day, Day)
    assert reading.body
