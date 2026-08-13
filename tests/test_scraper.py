"""Tests for the scraper using real saved pages as fixtures."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from exodus90_printer.exceptions import FetchError, NoReadingForDateError
from exodus90_printer.models import Day
from exodus90_printer.scraper import (
    discover_program_id,
    fetch_days,
    fetch_night_vigil,
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
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, headers: dict[str, str] | None = None, **_: object) -> _FakeResponse:
        self.requests.append((path, headers or {}))
        return _FakeResponse(self.pages[path])


@pytest.fixture()
def program_client() -> _FakeClient:
    return _FakeClient(
        {
            "/programs/208/days": (FIXTURES / "days_page.html").read_text(),
            "/readings/program_day_3320": (FIXTURES / "reading_page.html").read_text(),
        }
    )


@pytest.fixture()
def today_client() -> _FakeClient:
    return _FakeClient({"/today": (FIXTURES / "today_page.html").read_text()})


def test_discover_program_id_returns_current_program(today_client: _FakeClient) -> None:
    assert discover_program_id(today_client) == 198  # type: ignore[arg-type]


def test_discover_program_id_requests_today_page(today_client: _FakeClient) -> None:
    discover_program_id(today_client)  # type: ignore[arg-type]
    path, headers = today_client.requests[0]
    assert path == "/today"


def test_discover_program_id_missing_card_raises() -> None:
    client = _FakeClient({"/today": "<html><body>no program card</body></html>"})
    with pytest.raises(FetchError):
        discover_program_id(client)  # type: ignore[arg-type]


def test_fetch_days_maps_date_to_day(program_client: _FakeClient) -> None:
    days = fetch_days(program_client, 208)  # type: ignore[arg-type]
    by_date = {d.date: d for d in days}
    assert by_date[date(2026, 8, 1)].day_id == "program_day_3320"
    assert by_date[date(2026, 8, 1)].title == "Isten harcol érted"
    assert by_date[date(2026, 8, 1)].scripture == "Kiv 14,10-20"
    assert by_date[date(2026, 8, 10)].day_id == "program_day_3321"
    assert by_date[date(2026, 8, 10)].title == "Ragaszkodj ahhoz, amit kaptál"
    assert by_date[date(2026, 8, 10)].scripture == "2Tessz 2,13-3,5"


def test_fetch_days_requests_days_frame(program_client: _FakeClient) -> None:
    fetch_days(program_client, 208)  # type: ignore[arg-type]
    path, headers = program_client.requests[0]
    assert path == "/programs/208/days"
    assert headers.get("Turbo-Frame") == "program_days_frame"


def test_fetch_days_returns_all_days(program_client: _FakeClient) -> None:
    days = fetch_days(program_client, 208)  # type: ignore[arg-type]
    assert len(days) == 11


def test_fetch_days_rejects_date(program_client: _FakeClient) -> None:
    days = fetch_days(program_client, 208)  # type: ignore[arg-type]
    with pytest.raises(NoReadingForDateError):
        find_day(days, date(2026, 1, 1))


def test_fetch_days_missing_data_modal_raises(program_client: _FakeClient) -> None:
    html = program_client.pages["/programs/208/days"].replace('data-modal="program_day_3320"', "")
    program_client.pages["/programs/208/days"] = html
    with pytest.raises(FetchError):
        fetch_days(program_client, 208)  # type: ignore[arg-type]


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


def test_fetch_night_vigil_extracts_body(today_client: _FakeClient) -> None:
    reading = fetch_night_vigil(today_client, date(2026, 8, 13))  # type: ignore[arg-type]
    assert reading is not None
    assert reading.day.day_id == "daily_gospel_meditation_9095"
    assert reading.day.date == date(2026, 8, 13)
    assert reading.day.title == "Making a Night Vigil"
    assert reading.day.scripture == "2 a.m. Friday Morning (That’s Tonight!)"
    assert reading.body.startswith("# Night Vigil")


def test_fetch_night_vigil_requests_today_page(today_client: _FakeClient) -> None:
    fetch_night_vigil(today_client, date(2026, 8, 13))  # type: ignore[arg-type]
    path, headers = today_client.requests[0]
    assert path == "/today"
    assert headers == {}


def test_fetch_night_vigil_returns_none_off_thursday(today_client: _FakeClient) -> None:
    reading = fetch_night_vigil(today_client, date(2026, 8, 12))  # type: ignore[arg-type]
    assert reading is None
    assert today_client.requests == []


def test_fetch_night_vigil_returns_none_without_reader(today_client: _FakeClient) -> None:
    html = today_client.pages["/today"].replace("daily_gospel_meditation_9095", "daily")
    today_client.pages["/today"] = html
    reading = fetch_night_vigil(today_client, date(2026, 8, 13))  # type: ignore[arg-type]
    assert reading is None


def test_fetch_night_vigil_missing_body_raises(today_client: _FakeClient) -> None:
    html = today_client.pages["/today"].replace(
        'data-reader-target="body"', 'data-reader-target="none"'
    )
    today_client.pages["/today"] = html
    with pytest.raises(FetchError):
        fetch_night_vigil(today_client, date(2026, 8, 13))  # type: ignore[arg-type]
