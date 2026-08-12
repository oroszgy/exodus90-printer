"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from exodus90_printer.config import Settings


@pytest.fixture()
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    """Build a fully-populated :class:`Settings` with test defaults."""

    def _make(**kwargs: Any) -> Settings:
        defaults: dict[str, Any] = {
            "program_id": 208,
            "output_dir": tmp_path / "out",
            "formats": ["pdf"],
        }
        defaults.update(kwargs)
        return Settings(**defaults)

    return _make
