"""Tests for the renderers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from exodus90_printer.config import Settings
from exodus90_printer.exceptions import ExodusError
from exodus90_printer.models import Day, Reading
from exodus90_printer.render import render
from exodus90_printer.render.markdown import render_markdown
from exodus90_printer.render.pdf import render_pdf
from exodus90_printer.render.printer import print_pdf


@pytest.fixture()
def reading() -> Reading:
    day = Day(
        day_id="program_day_3321",
        date=date(2026, 8, 10),
        title="Ragaszkodj ahhoz, amit kaptál",
        scripture="Kiv 14,10-20",
    )
    return Reading(
        day=day,
        program_id=208,
        body="# Cím\n\nBekezdés szövege ő és ű betűkkel.\n\n"
        "## Alfejezet\n\n*Dőlt* és **félkövér**.",
    )


def test_render_markdown(reading: Reading) -> None:
    md = render_markdown(reading)
    assert md.startswith("# Ragaszkodj ahhoz, amit kaptál")
    assert "**2026-08-10 · Kiv 14,10-20**" in md
    assert "## Alfejezet" in md


def test_render_pdf_contains_hungarian_glyphs(
    reading: Reading, make_settings: Callable[..., Settings]
) -> None:
    settings = make_settings()
    if not any(settings.pdf_font_dir.glob("*-Regular.ttf")):
        pytest.skip("No serif fonts available for the PDF test.")
    data = render_pdf(reading, settings)
    assert data.startswith(b"%PDF")
    assert b"Ragaszkodj ahhoz" in data


def test_render_pdf_missing_font_raises(
    tmp_path: Path, reading: Reading, make_settings: Callable[..., Settings]
) -> None:
    settings = make_settings(
        pdf_font_dir=tmp_path,
        pdf_font_family="DoesNotExist",
    )
    with pytest.raises(ExodusError, match="PDF font file missing"):
        render_pdf(reading, settings)


def test_render_writes_markdown(
    tmp_path: Path, reading: Reading, make_settings: Callable[..., Settings]
) -> None:
    settings = make_settings(output_dir=tmp_path, formats=["markdown"])
    outputs = render(reading, settings)
    assert "markdown" in outputs
    assert outputs["markdown"].read_text().startswith("# ")


def test_render_writes_pdf(
    tmp_path: Path, reading: Reading, make_settings: Callable[..., Settings]
) -> None:
    settings = make_settings(output_dir=tmp_path, formats=["pdf"])
    if not any(settings.pdf_font_dir.glob("*-Regular.ttf")):
        pytest.skip("No serif fonts available for the PDF test.")
    outputs = render(reading, settings)
    assert "pdf" in outputs
    assert outputs["pdf"].read_bytes().startswith(b"%PDF")


def test_print_pdf_with_fake_lp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sent_to: list[str] = []

    class _Result:
        returncode = 0
        stderr = ""

    def fake_run(command: list[str], **_kwargs: object) -> _Result:
        sent_to.extend(command)
        return _Result()

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/lp" if name == "lp" else None)
    pdf = tmp_path / "reading.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    monkeypatch.setattr("subprocess.run", fake_run)
    print_pdf(pdf, "Brother-3000")
    assert "/usr/bin/lp" in sent_to
    assert sent_to[sent_to.index("/usr/bin/lp") + 1] == "-d"
    assert sent_to[-1] == str(pdf)


def test_print_pdf_no_lp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    pdf = tmp_path / "reading.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(ExodusError, match="lp"):
        print_pdf(pdf, None)
