"""PDF output via xhtml2pdf with a Unicode-capable serif font."""

from __future__ import annotations

import io
from html import escape
from pathlib import Path

from markdown import markdown as markdown_to_html  # type: ignore[import-untyped]
from xhtml2pdf import pisa  # type: ignore[import-untyped]

from exodus90_printer.config import Settings
from exodus90_printer.exceptions import ExodusError
from exodus90_printer.models import Reading
from exodus90_printer.render.util import output_stem


def _font_paths(settings: Settings) -> dict[str, Path]:
    directory = settings.pdf_font_dir
    family = settings.pdf_font_family
    return {
        "regular": directory / f"{family}-Regular.ttf",
        "bold": directory / f"{family}-Bold.ttf",
        "italic": directory / f"{family}-Italic.ttf",
        "bold_italic": directory / f"{family}-BoldItalic.ttf",
    }


def _font_face(path: Path, weight: str, style: str) -> str:
    return (
        '@font-face { font-family: "Reader"; '
        f'src: url("{path}"); font-weight: {weight}; font-style: {style}; }}'
    )


def render_pdf(reading: Reading, settings: Settings) -> bytes:
    fonts = _font_paths(settings)
    for _name, path in fonts.items():
        if not path.is_file():
            raise ExodusError(
                f"PDF font file missing: {path}. Install the font or set "
                "`pdf_font_dir`/`pdf_font_family` in the config."
            )

    header = reading.day.date.isoformat()
    if reading.day.scripture:
        header = f"{header} · {reading.day.scripture}"

    font_faces = "\n".join(
        _font_face(fonts[kind], weight, style)
        for kind, weight, style in (
            ("regular", "normal", "normal"),
            ("bold", "bold", "normal"),
            ("italic", "normal", "italic"),
            ("bold_italic", "bold", "italic"),
        )
    )
    css = f"""
    {font_faces}
    body {{ font-family: Reader; font-size: 11pt; line-height: 1.5; text-align: justify; }}
    h1.title {{ font-size: 20pt; margin-bottom: 0.2em; }}
    p.meta {{ font-size: 12pt; margin-top: 0; }}
    .reader h1 {{ font-size: 14pt; margin-top: 1.2em; }}
    .reader h2 {{ font-size: 12.5pt; margin-top: 1.1em; }}
    .reader blockquote {{ margin-left: 1.2em; color: #333; }}
    """

    body_html = markdown_to_html(reading.body, extensions=["extra"])
    html = f"""<html><head><meta charset="utf-8"><style>{css}</style></head>
    <body>
      <h1 class="title">{escape(reading.day.title)}</h1>
      <p class="meta">{escape(header)}</p>
      <div class="reader">
        {body_html}
      </div>
    </body></html>"""

    result = io.BytesIO()
    pdf = pisa.CreatePDF(io.BytesIO(html.encode("utf-8")), dest=result, encoding="utf-8")
    if pdf.err:
        raise ExodusError(f"PDF generation failed with {pdf.err} error(s).")
    return result.getvalue()


def write_pdf(reading: Reading, settings: Settings) -> Path:
    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{output_stem(reading)}.pdf"
    path.write_bytes(render_pdf(reading, settings))
    return path
