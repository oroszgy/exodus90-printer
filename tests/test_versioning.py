"""Assert the package version is consistent across metadata sources."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import exodus90_printer

_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    with (_ROOT / "pyproject.toml").open("rb") as fh:
        version = tomllib.load(fh)["project"]["version"]
    return str(version)


def _addon_version() -> str:
    match = re.search(
        r'^version:\s*"([^"]+)"',
        (_ROOT / "addon" / "config.yaml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None
    return match.group(1)


def test_versions_agree() -> None:
    assert exodus90_printer.__version__ == _pyproject_version() == _addon_version()
