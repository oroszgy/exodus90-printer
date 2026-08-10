"""Rendering dispatcher: markdown / pdf / print, as configured."""

from __future__ import annotations

from pathlib import Path

from exodus90_printer.config import OutputFormat, Settings
from exodus90_printer.models import Reading
from exodus90_printer.render import markdown as markdown_renderer
from exodus90_printer.render import pdf as pdf_renderer
from exodus90_printer.render import printer as printer_renderer


def render(
    reading: Reading, settings: Settings, formats: list[OutputFormat] | None = None
) -> dict[OutputFormat, Path]:
    """Render a reading to every requested output format.

    Returns a mapping of format name to the path of the file produced
    (for ``print`` this is the underlying PDF that was sent to the printer).
    """
    formats = list(formats or settings.formats)
    outputs: dict[OutputFormat, Path] = {}

    if "markdown" in formats:
        outputs["markdown"] = markdown_renderer.write_markdown(reading, settings.output_dir)

    needs_pdf = "pdf" in formats or "print" in formats
    pdf_path: Path | None = None
    if needs_pdf:
        pdf_path = pdf_renderer.write_pdf(reading, settings)
        if "pdf" in formats:
            outputs["pdf"] = pdf_path

    if "print" in formats:
        if pdf_path is None:
            raise ValueError("internal error: print requested without a PDF")
        printer_renderer.print_pdf(pdf_path, settings.printer)
        outputs["print"] = pdf_path

    return outputs
