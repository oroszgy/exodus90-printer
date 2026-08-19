"""Sending a PDF to a CUPS printer via ``lp``."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from exodus90_printer.exceptions import ExodusError


def _verify_queue(printer: str) -> None:
    lpoptions = shutil.which("lpoptions")
    if lpoptions is None:
        return
    result = subprocess.run([lpoptions, "-p", printer, "-l"], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise ExodusError(
            f"Printer queue '{printer}' has no PPD (raw/broken queue); "
            "fix the printer URI and recreate the queue before printing."
        )


def print_pdf(pdf_path: Path, printer: str | None, double_sided: bool = True) -> None:
    lp = shutil.which("lp")
    if lp is None:
        raise ExodusError("CUPS `lp` command not found; cannot print.")
    if printer is not None:
        _verify_queue(printer)
    command = [lp]
    if printer:
        command += ["-d", printer]
    sides = "two-sided-long-edge" if double_sided else "one-sided"
    command += ["-o", f"sides={sides}"]
    command.append(str(pdf_path))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise ExodusError(f"`lp` failed: {stderr or f'exit code {result.returncode}'}")
