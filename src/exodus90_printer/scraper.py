"""Scraping of the Exodus 90 program and reading pages."""

from __future__ import annotations

from datetime import date

from bs4 import BeautifulSoup, Tag

from exodus90_printer.client import ExodusClient
from exodus90_printer.exceptions import FetchError, NoReadingForDateError
from exodus90_printer.models import Day, Reading


def fetch_days(client: ExodusClient, program_id: int) -> list[Day]:
    """Fetch the list of days for a program from its days Turbo frame."""
    response = client.get(
        f"/programs/{program_id}/days",
        headers={"Turbo-Frame": "program_days_frame"},
    )
    soup = BeautifulSoup(response.text, "lxml")
    days: list[Day] = []
    for button in soup.select("button[data-reading-date]"):
        day_id = str(button.get("data-modal") or "")
        if not day_id:
            raise FetchError("Could not parse the day list; the app layout may have changed.")
        try:
            reading_date = date.fromisoformat(str(button["data-reading-date"]))
        except (ValueError, KeyError) as exc:
            raise FetchError(
                "Could not parse the day list; the app layout may have changed."
            ) from exc
        title_element = button.select_one("p.text-left.grow")
        title = _element_text(title_element) if title_element is not None else ""
        days.append(
            Day(
                day_id=day_id,
                date=reading_date,
                title=title,
                scripture=_scripture_reference(soup, day_id),
            )
        )
    if not days:
        raise FetchError("No days found; the program page layout may have changed.")
    return days


def _element_text(element: Tag) -> str:
    """Extract visible text, working around a lxml quirk where get_text can be empty."""
    text = element.get_text(strip=True)
    if text:
        return text
    string = element.string
    return string.strip() if string else ""


def _scripture_reference(soup: BeautifulSoup, day_id: str) -> str | None:
    heading = soup.select_one(f"#{day_id} h2")
    if heading is None:
        return None
    text = _element_text(heading)
    return text or None


def find_day(days: list[Day], target_date: date) -> Day:
    for day in days:
        if day.date == target_date:
            return day
    raise NoReadingForDateError(f"The program has no reading for {target_date.isoformat()}.")


def fetch_reading(client: ExodusClient, day: Day, program_id: int) -> Reading:
    """Fetch the markdown body for a single day."""
    response = client.get(
        f"/readings/{day.day_id}",
        headers={"Turbo-Frame": f"{day.day_id}_frame"},
    )
    soup = BeautifulSoup(response.text, "lxml")
    body = soup.select_one("div[data-reader-target=body]")
    content = None
    if body is not None and "data-content" in body.attrs:
        content = str(body["data-content"])
    if content is None:
        raise FetchError(
            f"No reading body found for {day.day_id}; the app layout may have changed."
        )
    return Reading(day=day, program_id=program_id, body=content)


def fetch_reading_for_date(client: ExodusClient, program_id: int, target_date: date) -> Reading:
    """Convenience wrapper: program page -> day -> reading body."""
    days = fetch_days(client, program_id)
    day = find_day(days, target_date)
    return fetch_reading(client, day, program_id)
