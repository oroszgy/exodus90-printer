"""Markdown output."""

from __future__ import annotations

from pathlib import Path

from exodus90_printer.models import Reading
from exodus90_printer.render.util import output_stem


def render_markdown(reading: Reading) -> str:
    header = reading.day.date.isoformat()
    if reading.day.scripture:
        header = f"{header} · {reading.day.scripture}"
    return "\n\n".join(
        [
            f"# {reading.day.title}",
            f"**{header}**",
            reading.body.strip(),
            "",
        ]
    )


def write_markdown(reading: Reading, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{output_stem(reading)}.md"
    path.write_text(render_markdown(reading), encoding="utf-8")
    return path
