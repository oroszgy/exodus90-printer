"""Sending a PDF to a CUPS printer via ``lp``."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from exodus90_printer.exceptions import ExodusError


def print_pdf(pdf_path: Path, printer: str | None) -> None:
    lp = shutil.which("lp")
    if lp is None:
        raise ExodusError("CUPS `lp` command not found; cannot print.")
    command = [lp]
    if printer:
        command += ["-d", printer]
    command.append(str(pdf_path))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise ExodusError(f"`lp` failed: {stderr or f'exit code {result.returncode}'}")
