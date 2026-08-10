"""Tests for settings loading and precedence."""

from __future__ import annotations

from pathlib import Path

import pytest

from exodus90_printer.config import Settings, load_settings


def _write_toml(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_defaults() -> None:
    settings = Settings()
    assert settings.base_url == "https://app.exodus90.com"
    assert settings.program_id == 208
    assert settings.formats == ["pdf", "print"]


def test_load_settings_reads_toml(tmp_path: Path) -> None:
    cfg = _write_toml(
        tmp_path / "config.toml",
        'base_url = "https://example.com"\nprogram_id = 999\nformats = ["markdown"]\n',
    )
    settings = load_settings(cfg)
    assert settings.base_url == "https://example.com"
    assert settings.program_id == 999
    assert settings.formats == ["markdown"]


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_toml(tmp_path / "config.toml", "program_id = 999\n")
    monkeypatch.setenv("EXODUS90_PROGRAM_ID", "42")
    settings = load_settings(cfg)
    assert settings.program_id == 42


def test_env_sets_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXODUS90_BASE_URL", "https://example.com")
    settings = load_settings(tmp_path / "missing.toml")
    assert settings.base_url == "https://example.com"
